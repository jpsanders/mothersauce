import sqlite3
from collections.abc import Iterator
from typing import Any

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from mothersauce.recipes.pipeline import Summary, run, sample_path
from mothersauce.recipes.quality import Override

scenarios("pipeline.feature")


@pytest.fixture
def kitchen() -> dict[str, Any]:
    """
    Hold what the steps share: the feed, the approvals and the last run's summary.

    :returns: A dict the steps fill in
    """
    return {"overrides": []}


@given("the sample ticket feed")
def sample_feed(kitchen: dict[str, Any]) -> None:
    kitchen["url"] = sample_path().as_uri().replace("file:", "csv:", 1)


@given("an empty database", target_fixture="database")
def empty_database() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(":memory:", autocommit=True)
    yield conn
    conn.close()


@given("the staff meal is approved by the head chef")
def staff_meal_approved(kitchen: dict[str, Any]) -> None:
    kitchen["overrides"].append(Override("T-1005-1", "price_not_zero", "head chef", "family meal before service"))


@when("the pipeline runs")
@when("the pipeline runs again")
def pipeline_runs(kitchen: dict[str, Any], database: sqlite3.Connection) -> None:
    kitchen["summary"] = run(kitchen["url"], database, overrides=kitchen["overrides"])


def summary(kitchen: dict[str, Any]) -> Summary:
    result: Summary = kitchen["summary"]
    return result


@then(parsers.re(r"(?P<count>\d+) lines? (?:is|are) loaded"), converters={"count": int})
def lines_loaded(kitchen: dict[str, Any], count: int) -> None:
    assert summary(kitchen).loaded == count


@then(parsers.re(r"(?P<count>\d+) lines? (?:is|are) quarantined"), converters={"count": int})
def lines_quarantined(kitchen: dict[str, Any], count: int) -> None:
    assert summary(kitchen).quarantined == count


@then(parsers.re(r"(?P<count>\d+) lines? (?:is|are) invalid"), converters={"count": int})
def lines_invalid(kitchen: dict[str, Any], count: int) -> None:
    assert summary(kitchen).invalid == count


@then(parsers.parse("{count:d} lines are skipped as already loaded"))
def lines_skipped(kitchen: dict[str, Any], count: int) -> None:
    assert summary(kitchen).skipped == count
