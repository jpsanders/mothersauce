import io
import json
import logging
import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from mothersauce.recipes.config import Settings
from mothersauce.recipes.logs import configure
from mothersauce.recipes.pipeline import FeedLine, demo, run, sample_feed
from mothersauce.recipes.quality import Override

STAFF_MEAL = Override("T-1005-1", "price_not_zero", "head chef", "family meal")


@pytest.fixture
def conn() -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(":memory:", autocommit=True)
    yield connection
    connection.close()


@pytest.fixture
def url() -> Iterator[str]:
    with sample_feed() as feed:
        yield feed


def count(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT count(*) FROM ticket_lines").fetchone()[0])


def test_sample_ships_with_the_package(url: str) -> None:
    assert url.startswith("csv://") and url.endswith("/tickets.csv")


def test_first_run_loads_the_good_rows(conn: sqlite3.Connection, url: str) -> None:
    summary = run(url, conn, overrides=[STAFF_MEAL], run_id="r1")
    assert (summary.read, summary.loaded, summary.quarantined, summary.invalid) == (16, 12, 3, 1)
    assert summary.findings == {"large_quantity": 1, "known_station": 1, "quantity_positive": 1, "unique_key": 1}
    assert summary.problems == ("RecordError: line 16, opened_at: input should have timezone info",)
    assert count(conn) == 12
    assert str(summary).startswith("r1: read 16, loaded 12, already loaded 0")


def test_summary_is_frozen_all_the_way_down(conn: sqlite3.Connection, url: str) -> None:
    summary = run(url, conn, overrides=[STAFF_MEAL])
    with pytest.raises(TypeError):
        summary.findings["unique_key"] = 0  # type: ignore[index]
    assert hash(summary)


def test_second_run_loads_nothing_new(conn: sqlite3.Connection, url: str) -> None:
    run(url, conn, overrides=[STAFF_MEAL])
    again = run(url, conn, overrides=[STAFF_MEAL])
    assert (again.loaded, again.already_loaded) == (0, 12)
    assert count(conn) == 12


def test_a_late_line_for_an_earlier_ticket_still_loads(conn: sqlite3.Connection, url: str, tmp_path: Path) -> None:
    run(url, conn, overrides=[STAFF_MEAL])
    later = tmp_path / "later.csv"
    with sample_feed() as feed:
        text = Path(feed.removeprefix("csv://")).read_text(encoding="utf-8")
    later.write_text(text + "T-1001-3,T-1001,4,2026-11-12T12:05:00+00:00,sole,grill,1,31.50\n", encoding="utf-8")
    summary = run(f"csv://{later}", conn, overrides=[STAFF_MEAL])
    assert (summary.loaded, summary.already_loaded) == (1, 12)
    assert count(conn) == 13


def test_a_corrected_line_updates_in_place(conn: sqlite3.Connection, url: str, tmp_path: Path) -> None:
    run(url, conn, overrides=[STAFF_MEAL])
    fixed = tmp_path / "fixed.csv"
    fixed.write_text(
        "line_id,ticket_id,table,opened_at,dish,station,quantity,unit_price\n"
        "T-1001-1,T-1001,4,2026-11-12T12:05:00+00:00,sole meuniere,grill,3,31.50\n",
        encoding="utf-8",
    )
    summary = run(f"csv://{fixed}", conn)
    assert (summary.loaded, summary.already_loaded) == (0, 1)
    assert conn.execute("SELECT quantity FROM ticket_lines WHERE line_id = 'T-1001-1'").fetchone() == (3,)


def test_without_the_override_the_staff_meal_is_quarantined(conn: sqlite3.Connection, url: str) -> None:
    summary = run(url, conn)
    assert summary.quarantined == 4 and summary.findings["price_not_zero"] == 1
    assert count(conn) == 11


def test_small_batches_end_in_the_same_table(conn: sqlite3.Connection, url: str) -> None:
    summary = run(url, conn, overrides=[STAFF_MEAL], settings=Settings(batch_size=4))
    assert summary.read == 16
    assert count(conn) == 12  # a duplicate split across batches is caught by the key


def test_money_keeps_its_cents(conn: sqlite3.Connection, url: str) -> None:
    run(url, conn, overrides=[STAFF_MEAL])
    row = conn.execute("SELECT quantity, unit_price, opened_at FROM ticket_lines WHERE line_id = 'T-1001-1'").fetchone()
    assert row == (2, "31.50", "2026-11-12T12:05:00+00:00")
    assert Decimal(row[1]) == Decimal("31.50")


def test_logs_carry_the_run_id(conn: sqlite3.Connection, url: str) -> None:
    stream = io.StringIO()
    configure(stream=stream, logger="mothersauce.recipes.pipeline")
    try:
        run(url, conn, overrides=[STAFF_MEAL], run_id="r42")
    finally:
        logging.getLogger("mothersauce.recipes.pipeline").handlers.clear()
    events = [json.loads(line) for line in stream.getvalue().splitlines()]
    assert {e["run_id"] for e in events} == {"r42"}
    assert events[-1]["msg"] == "run done" and events[-1]["loaded"] == 12


def test_feed_line_model() -> None:
    line = FeedLine.model_validate(
        {
            "line_id": "T-1001-1",
            "ticket_id": "T-1001",
            "table": "4",
            "opened_at": "2026-11-12T12:05:00+00:00",
            "dish": "sole",
            "station": "grill",
            "quantity": "2",
            "unit_price": "31.50",
        }
    )
    assert line.opened_at == datetime(2026, 11, 12, 12, 5, tzinfo=UTC) and line.quantity == 2


def test_demo_runs(capsys: pytest.CaptureFixture[str]) -> None:
    demo()
    out = capsys.readouterr().out
    assert "run-1: read 16, loaded 12, already loaded 0, quarantined 3, invalid 1" in out
    assert "run-2: read 16, loaded 0, already loaded 12" in out
    assert "prices keep their cents: '31.50'" in out
