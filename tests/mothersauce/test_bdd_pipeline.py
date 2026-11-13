import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from mothersauce.recipes.pipeline import Summary, run, sample_feed
from mothersauce.recipes.quality import Override

scenarios("pipeline.feature")


@pytest.fixture
def overrides() -> list[Override]:
    """
    Start every scenario with no approvals; a Given step replaces this through target_fixture.

    :returns: An empty list
    """
    return []


@given("the sample ticket feed", target_fixture="feed")
def sample(tmp_path: Path) -> str:
    with sample_feed() as url:
        copy = tmp_path / "tickets.csv"
        copy.write_text(Path(url.removeprefix("csv://")).read_text(encoding="utf-8"), encoding="utf-8")
    return f"csv://{copy}"


@given("an empty database", target_fixture="database")
def empty_database() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(":memory:", autocommit=True)
    yield conn
    conn.close()


@given("the staff meal is approved by the head chef", target_fixture="overrides")
def staff_meal_approved() -> list[Override]:
    return [Override("T-1005-1", "price_not_zero", "head chef", "family meal before service")]


@when("the pipeline runs", target_fixture="summary")
@when("the pipeline runs again", target_fixture="summary")
def pipeline_runs(feed: str, database: sqlite3.Connection, overrides: list[Override]) -> Summary:
    return run(feed, database, overrides=overrides)


@when("a second dish is added to the first ticket")
def late_line(feed: str) -> None:
    with Path(feed.removeprefix("csv://")).open("a", encoding="utf-8") as handle:
        handle.write("T-1001-3,T-1001,4,2026-11-12T12:05:00+00:00,sole,grill,1,31.50\n")


@then(parsers.re(r"(?P<count>\d+) lines? (?:is|are) loaded"), converters={"count": int})
def lines_loaded(summary: Summary, count: int) -> None:
    assert summary.loaded == count


@then(parsers.re(r"(?P<count>\d+) lines? (?:is|are) quarantined"), converters={"count": int})
def lines_quarantined(summary: Summary, count: int) -> None:
    assert summary.quarantined == count


@then(parsers.re(r"(?P<count>\d+) lines? (?:is|are) invalid"), converters={"count": int})
def lines_invalid(summary: Summary, count: int) -> None:
    assert summary.invalid == count


@then(parsers.parse("{count:d} lines were already loaded"))
def already_loaded(summary: Summary, count: int) -> None:
    assert summary.already_loaded == count
