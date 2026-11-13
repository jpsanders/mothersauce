"""
The pipeline: most of the base recipes plated together as one small, real ETL.

Each of these recipes has a job here:

- a URL picks the reader (factories), behind the abstract source (abstractions);
- rows stream in batches and are never all held at once (generators);
- quality rules quarantine bad rows, and an override lets a staff meal through (data quality, enums);
- pydantic parses each good row at the edge into a typed record (pydantic);
- batches are upserted with schema evolution inside transactions (sql, context managers);
- the run logs JSON with its run id, and failures are collected, never fatal one by one (logging, errors);
- the batch size comes from layered settings (config), and the result is a frozen summary (dataclasses).

Loading is exactly once by key. Every line has a primary key and every write is an upsert, so a second run changes
nothing and a line that arrives late, or a corrected line, still lands. A timestamp watermark would be cheaper to
query, and is the right tool for extracting from a table (the sql recipe has one), but for loading it can silently
skip a line that arrives after a later one: a key cannot.

``mothersauce run pipeline`` loads the sample feed that ships with the package into a temporary SQLite database,
twice, to show that the second run finds nothing new.
"""

import io
import logging
import sqlite3
import tempfile
from collections import Counter
from collections.abc import Generator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date
from importlib import resources
from itertools import batched
from pathlib import Path
from uuid import uuid4

from pydantic import AwareDatetime, Field, ValidationError

from mothersauce.recipes.config import Settings
from mothersauce.recipes.context_managers import timed
from mothersauce.recipes.errors import RecordError, leaf_messages
from mothersauce.recipes.factories import make_source
from mothersauce.recipes.logs import configure, log_context
from mothersauce.recipes.models import Price, Quantity, Record, Station, TicketId
from mothersauce.recipes.quality import Override, check_batch
from mothersauce.recipes.sql import sql, upsert

__all__ = ["FeedLine", "Summary", "demo", "run", "sample_feed"]

logger = logging.getLogger(__name__)
TABLE = "ticket_lines"
KEY = "line_id"


class FeedLine(Record):
    """
    One line of the ticket feed, parsed. Built from the reusable constraints in the pydantic recipe.

    :param line_id: The line's own id, such as ``T-1001-2``; the primary key
    :param ticket_id: The ticket it belongs to
    :param table: The table
    :param opened_at: When the ticket was opened, with a timezone
    :param dish: The dish
    :param station: The station that cooks it
    :param quantity: How many
    :param unit_price: The price of one
    """

    line_id: str = Field(pattern=r"^T-[0-9]{4,}-[0-9]+$")
    ticket_id: TicketId
    table: int = Field(ge=1, le=99)
    opened_at: AwareDatetime
    dish: str = Field(min_length=1)
    station: Station
    quantity: Quantity
    unit_price: Price


@dataclass(frozen=True, slots=True)
class Summary:
    """
    What one run did. Frozen, its findings included: a report of the past should not change.

    :param run_id: The run's id, also on every log line
    :param read: Rows read from the source
    :param loaded: New lines written
    :param already_loaded: Lines whose key was already in the table; upserted again, so a corrected line updates
    :param quarantined: Rows held back by an error rule
    :param invalid: Rows that passed the rules but failed parsing
    :param seconds: How long it took
    :param findings: Unwaived findings per rule
    :param problems: One line per invalid row
    """

    run_id: str
    read: int
    loaded: int
    already_loaded: int
    quarantined: int
    invalid: int
    seconds: float
    findings: frozendict[str, int] = field(default_factory=frozendict)
    problems: tuple[str, ...] = ()

    def __str__(self) -> str:
        return (
            f"{self.run_id}: read {self.read}, loaded {self.loaded}, already loaded {self.already_loaded}, "
            f"quarantined {self.quarantined}, invalid {self.invalid} in {self.seconds * 1000:.0f} ms"
        )


@contextmanager
def sample_feed() -> Generator[str]:
    """
    Give the URL of the sample feed that ships inside the package, as a real file even from a zipped install.

    :yields: A ``csv://`` URL for :func:`run`
    """
    with resources.as_file(resources.files("mothersauce") / "data" / "samples" / "tickets.csv") as path:
        yield path.as_uri().replace("file:", "csv:", 1)


def _known_keys(conn: sqlite3.Connection, keys: list[str]) -> set[str]:
    """
    Find which of these keys the table already holds; none when the table does not exist yet.

    :param conn: The connection
    :param keys: Line ids
    :returns: The ones already loaded
    """
    if not keys or not conn.execute(*sql(t"PRAGMA table_info({TABLE:id})")).fetchone():
        return set()
    found = conn.execute(*sql(t"SELECT {KEY:id} FROM {TABLE:id} WHERE {KEY:id} IN ({keys:params})"))
    return {row[0] for row in found}


def run(
    url: str,
    conn: sqlite3.Connection,
    *,
    settings: Settings | None = None,
    overrides: Sequence[Override] = (),
    run_id: str | None = None,
    today: date | None = None,
) -> Summary:
    """
    Load a feed into the database: check, parse, and upsert in batches, exactly once by key.

    :param url: The source, such as ``csv:///data/tickets.csv``
    :param conn: A connection in autocommit mode
    :param settings: Batch size and the rest; the defaults when omitted
    :param overrides: Approved exceptions to the quality rules
    :param run_id: An id for the logs; a new one when omitted
    :param today: The day overrides are checked against
    :returns: What the run did
    """
    settings = settings or Settings()
    run_id = run_id or f"run-{uuid4().hex[:8]}"
    read = loaded = already = quarantined = 0
    findings: Counter[str] = Counter()
    problems: list[RecordError] = []
    with log_context(run=run_id, src=url), timed("pipeline") as timer:
        for batch in batched(make_source(url).read(), settings.batch_size):
            first_line = read + 2  # line 1 of the file is the header
            line_numbers = {id(row): first_line + n for n, row in enumerate(batch)}
            read += len(batch)
            report = check_batch(batch, overrides=overrides, today=today)
            quarantined += len(report.quarantined)
            findings.update(report.by_rule())
            good = []
            for row in report.accepted:
                try:
                    good.append(FeedLine.model_validate(row).model_dump())
                except ValidationError as error:
                    first = error.errors()[0]
                    problems.append(RecordError(line_numbers[id(row)], str(first["loc"][0]), first["msg"].lower()))
            known = _known_keys(conn, [line[KEY] for line in good])
            upsert(conn, TABLE, good, key=KEY)
            loaded += sum(1 for line in good if line[KEY] not in known)
            already += sum(1 for line in good if line[KEY] in known)
            logger.info("batch done", extra={"rows": len(batch), "good": len(good)})
        logger.info("run done", extra={"read": read, "loaded": loaded, "quarantined": quarantined})
    return Summary(
        run_id,
        read,
        loaded,
        already,
        quarantined,
        len(problems),
        timer.seconds,
        frozendict(findings),
        tuple(message for error in problems for message in leaf_messages(error)),
    )


def demo() -> None:
    """Load the sample feed twice into a temporary database, with JSON logs kept in memory."""
    logs = io.StringIO()
    configure(stream=logs, logger=__name__)
    staff_meal = Override("T-1005-1", "price_not_zero", "head chef", "family meal before service")
    with sample_feed() as url, tempfile.TemporaryDirectory() as folder:
        conn = sqlite3.connect(Path(folder) / "kitchen.db", autocommit=True)
        first, second = (run(url, conn, overrides=[staff_meal], run_id=f"run-{n}") for n in (1, 2))
        print(first)
        print(second)
        print(f"findings on the first run: {dict(first.findings)}")
        print(f"invalid: {list(first.problems)}")
        stations = conn.execute("SELECT station, sum(quantity) FROM ticket_lines GROUP BY station ORDER BY 2 DESC")
        print(f"dishes by station: {dict(stations.fetchall())}")
        price = conn.execute("SELECT unit_price FROM ticket_lines WHERE line_id = 'T-1001-1'").fetchone()[0]
        print(f"prices keep their cents: {price!r}")
        conn.close()
    print(f"{len(logs.getvalue().splitlines())} JSON log lines, each carrying its run id")
    logging.getLogger(__name__).handlers.clear()
