"""
The pipeline: the base recipes plated together as one small, real ETL.

Every earlier recipe has a job here:

- a URL picks the reader (factories), behind the abstract source (abstractions);
- rows stream in batches and are never all held at once (generators);
- quality rules quarantine bad rows, and an override lets a staff meal through (quality, enums);
- pydantic parses each good row at the edge into a typed record (pydantic);
- batches are upserted with schema evolution inside transactions (sql, context managers);
- a watermark makes the next run load only what is new (dataclasses);
- the run logs JSON with its run id, and failures are collected, never fatal one by one (logging, errors);
- the batch size comes from layered settings (config), and the result is a frozen summary.

``mothersauce run pipeline`` loads the sample feed that ships with the package into a temporary SQLite database,
twice, to show that the second run finds nothing new.
"""

import io
import logging
import sqlite3
import tempfile
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from importlib import resources
from itertools import batched
from pathlib import Path
from uuid import uuid4

from pydantic import AwareDatetime, Field, ValidationError

from mothersauce.recipes.config import Settings
from mothersauce.recipes.context_managers import Transaction, timed
from mothersauce.recipes.errors import RecordError, leaf_messages
from mothersauce.recipes.factories import make_source
from mothersauce.recipes.logs import configure, log_context
from mothersauce.recipes.models import Price, Quantity, Record, Station, TicketId
from mothersauce.recipes.quality import Override, check_batch
from mothersauce.recipes.sql import ensure_table, upsert
from mothersauce.recipes.value_objects import Watermark

__all__ = ["FeedLine", "Summary", "demo", "run", "sample_path"]

logger = logging.getLogger(__name__)
TABLE = "ticket_lines"
WATERMARKS = "watermarks"


class FeedLine(Record):
    """
    One line of the ticket feed, parsed. Built from the reusable constraints in the pydantic recipe.

    :param line_id: The line's own id, such as ``T-1001-2``
    :param ticket_id: The ticket it belongs to
    :param table: The table
    :param opened_at: When the ticket was opened, with a timezone
    :param dish: The dish
    :param station: The station that cooks it
    :param quantity: How many
    :param unit_price: The price of one
    """

    line_id: str = Field(pattern=r"^T-\d{4,}-\d+$")
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
    What one run did. Frozen: a report of the past should not change.

    :param run_id: The run's id, also on every log line
    :param read: Rows read from the source
    :param loaded: Rows written
    :param quarantined: Rows held back by an error rule
    :param invalid: Rows that passed the rules but failed parsing
    :param skipped: Rows at or before the watermark, loaded by an earlier run
    :param watermark: Where the next run starts
    :param seconds: How long it took
    :param findings: Unwaived findings per rule
    :param problems: One line per invalid row
    """

    run_id: str
    read: int
    loaded: int
    quarantined: int
    invalid: int
    skipped: int
    watermark: Watermark | None
    seconds: float
    findings: dict[str, int] = field(default_factory=dict)
    problems: tuple[str, ...] = ()

    def __str__(self) -> str:
        return (
            f"{self.run_id}: read {self.read}, loaded {self.loaded}, skipped {self.skipped}, "
            f"quarantined {self.quarantined}, invalid {self.invalid} in {self.seconds * 1000:.0f} ms"
        )


def sample_path() -> Path:
    """
    Find the sample feed that ships inside the package.

    :returns: The path to ``tickets.csv``
    """
    return Path(str(resources.files("mothersauce") / "data" / "samples" / "tickets.csv"))


def _read_watermark(conn: sqlite3.Connection, source: str) -> Watermark | None:
    ensure_table(conn, WATERMARKS, {"source": "", "opened_at": "", "line_id": ""}, key="source")
    row = conn.execute("SELECT opened_at, line_id FROM watermarks WHERE source = ?", (source,)).fetchone()
    return Watermark(datetime.fromisoformat(row[0]), row[1]) if row else None


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
    Load a feed into the database: check, parse, upsert in batches, move the watermark.

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
    read = loaded = quarantined = skipped = 0
    findings: Counter[str] = Counter()
    problems: list[RecordError] = []
    with log_context(run=run_id, src=url), timed("pipeline") as timer:
        start = _read_watermark(conn, url)
        newest = start
        for batch in batched(make_source(url).read(), settings.batch_size):
            read += len(batch)
            first_line = read - len(batch) + 2  # line 1 of the file is the header
            line_numbers = {id(row): first_line + n for n, row in enumerate(batch)}
            report = check_batch(batch, overrides=overrides, today=today)
            quarantined += len(report.quarantined)
            findings.update(report.by_rule())
            fresh = []
            for row in report.accepted:
                try:
                    line = FeedLine.model_validate(row)
                except ValidationError as error:
                    first = error.errors()[0]
                    problems.append(RecordError(line_numbers[id(row)], str(first["loc"][0]), first["msg"].lower()))
                    continue
                mark = Watermark(line.opened_at, line.line_id)  # the line id breaks ties within one second
                if start is not None and mark <= start:
                    skipped += 1
                    continue
                newest = max(newest, mark) if newest else mark
                fresh.append(line.model_dump())
            loaded += upsert(conn, TABLE, fresh, key="line_id")
            logger.info("batch done", extra={"rows": len(batch), "loaded": len(fresh)})
        if newest is not None and newest != start:
            with Transaction(conn) as cur:
                cur.execute(
                    "INSERT INTO watermarks VALUES (?, ?, ?) ON CONFLICT (source) DO UPDATE SET "
                    "opened_at = excluded.opened_at, line_id = excluded.line_id",
                    (url, newest.opened_at.isoformat(), newest.ticket_id),
                )
        logger.info("run done", extra={"read": read, "loaded": loaded, "quarantined": quarantined})
    return Summary(
        run_id,
        read,
        loaded,
        quarantined,
        len(problems),
        skipped,
        newest,
        timer.seconds,
        dict(findings),
        tuple(message for error in problems for message in leaf_messages(error)),
    )


def demo() -> None:
    """Load the sample feed twice into a temporary database, with JSON logs kept in memory."""
    logs = io.StringIO()
    configure(stream=logs, logger=__name__)
    staff_meal = Override("T-1005-1", "price_not_zero", "head chef", "family meal before service")
    url = sample_path().as_uri().replace("file:", "csv:", 1)
    with tempfile.TemporaryDirectory() as folder:
        conn = sqlite3.connect(Path(folder) / "kitchen.db", autocommit=True)
        first, second = (run(url, conn, overrides=[staff_meal], run_id=f"run-{n}") for n in (1, 2))
        print(first)
        print(second)
        print(f"findings on the first run: {first.findings}")
        print(f"invalid: {list(first.problems)}")
        stations = conn.execute("SELECT station, sum(quantity) FROM ticket_lines GROUP BY station ORDER BY 2 DESC")
        print(f"dishes by station: {dict(stations.fetchall())}")
        if first.watermark:
            print(f"the next run starts after {first.watermark.opened_at:%H:%M}, line {first.watermark.ticket_id}")
        conn.close()
    print(f"{len(logs.getvalue().splitlines())} JSON log lines, each carrying its run id")
    logging.getLogger(__name__).handlers.clear()
