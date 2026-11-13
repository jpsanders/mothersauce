import io
import json
import logging
import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest

from mothersauce.recipes.config import Settings
from mothersauce.recipes.logs import configure
from mothersauce.recipes.pipeline import FeedLine, demo, run, sample_path
from mothersauce.recipes.quality import Override

STAFF_MEAL = Override("T-1005-1", "price_not_zero", "head chef", "family meal")


@pytest.fixture
def conn() -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(":memory:", autocommit=True)
    yield connection
    connection.close()


@pytest.fixture
def url() -> str:
    return sample_path().as_uri().replace("file:", "csv:", 1)


def count(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT count(*) FROM ticket_lines").fetchone()[0])


def test_sample_ships_with_the_package() -> None:
    assert sample_path().read_text(encoding="utf-8").startswith("line_id,ticket_id")


def test_first_run_loads_the_good_rows(conn: sqlite3.Connection, url: str) -> None:
    summary = run(url, conn, overrides=[STAFF_MEAL], run_id="r1")
    assert (summary.read, summary.loaded, summary.quarantined, summary.invalid) == (16, 12, 3, 1)
    assert summary.findings == {"large_quantity": 1, "known_station": 1, "quantity_positive": 1, "unique_key": 1}
    assert summary.problems == ("RecordError: line 16, opened_at: input should have timezone info",)
    assert count(conn) == 12
    assert summary.watermark is not None and summary.watermark.ticket_id == "T-1010-1"
    assert str(summary).startswith("r1: read 16, loaded 12")


def test_second_run_loads_nothing_new(conn: sqlite3.Connection, url: str) -> None:
    run(url, conn, overrides=[STAFF_MEAL])
    again = run(url, conn, overrides=[STAFF_MEAL])
    assert (again.loaded, again.skipped) == (0, 12)
    assert count(conn) == 12


def test_new_rows_after_the_watermark_are_loaded(conn: sqlite3.Connection, url: str, tmp_path: Path) -> None:
    run(url, conn, overrides=[STAFF_MEAL])
    later = tmp_path / "later.csv"
    later.write_text(
        sample_path().read_text(encoding="utf-8") + "T-1011-1,T-1011,4,2026-11-12T21:00:00+00:00,sole,grill,1,31.50\n",
        encoding="utf-8",
    )
    summary = run(f"csv://{later}", conn, overrides=[STAFF_MEAL])
    assert summary.loaded == 13  # a new source starts from no watermark of its own
    assert count(conn) == 13


def test_without_the_override_the_staff_meal_is_quarantined(conn: sqlite3.Connection, url: str) -> None:
    summary = run(url, conn)
    assert summary.quarantined == 4 and summary.findings["price_not_zero"] == 1
    assert count(conn) == 11


def test_small_batches_end_in_the_same_table(conn: sqlite3.Connection, url: str) -> None:
    summary = run(url, conn, overrides=[STAFF_MEAL], settings=Settings(batch_size=4))
    assert summary.read == 16
    assert count(conn) == 12  # a duplicate split across batches is caught by the idempotent upsert


def test_rows_are_typed_in_the_table(conn: sqlite3.Connection, url: str) -> None:
    run(url, conn, overrides=[STAFF_MEAL])
    row = conn.execute("SELECT quantity, unit_price, opened_at FROM ticket_lines WHERE line_id = 'T-1001-1'").fetchone()
    assert row == (2, 31.5, "2026-11-12T12:05:00+00:00")


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
    assert "run-1: read 16, loaded 12, skipped 0, quarantined 3, invalid 1" in out
    assert "run-2: read 16, loaded 0, skipped 12" in out
