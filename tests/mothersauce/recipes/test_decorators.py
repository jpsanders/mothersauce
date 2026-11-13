import json
import logging
import random
import warnings
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import StrEnum

import pytest

from mothersauce.recipes import decorators
from mothersauce.recipes.decorators import (
    CALLS,
    Menu,
    counted,
    demo,
    load_menu,
    parse_price,
    retry,
    station_for,
    to_json_value,
)


class Flaky:
    """Fails a set number of times, then answers."""

    def __init__(self, failures: int, error: Exception) -> None:
        self.failures = failures
        self.error = error
        self.calls = 0

    def __call__(self, value: int) -> int:
        self.calls += 1
        if self.calls <= self.failures:
            raise self.error
        return value * 2


def test_counted_keeps_name_and_counts() -> None:
    @counted
    def _add(a: int, b: int) -> int:
        """Add two numbers."""
        return a + b

    before = CALLS[_add.__qualname__]
    assert _add(1, 2) == 3 and _add(a=2, b=2) == 4
    assert CALLS[_add.__qualname__] - before == 2
    assert _add.__name__ == "_add" and _add.__doc__ == "Add two numbers."


def test_retry_recovers_from_transient_errors(caplog: pytest.LogCaptureFixture) -> None:
    waits: list[float] = []
    flaky = Flaky(2, TimeoutError("slow"))
    wrapped = retry(attempts=3, sleep=waits.append, rng=random.Random(1))(flaky)  # nosec B311
    with caplog.at_level(logging.WARNING):
        assert wrapped(21) == 42
    assert flaky.calls == 3 and len(waits) == 2
    assert "retry 1" in caplog.text


def test_retry_backoff_grows_and_is_capped() -> None:
    waits: list[float] = []
    flaky = Flaky(9, ConnectionError("down"))
    wrapped = retry(attempts=6, base_delay=1.0, max_delay=3.0, sleep=waits.append)(flaky)
    with pytest.raises(ConnectionError) as caught:
        wrapped(1)
    assert flaky.calls == 6 and len(waits) == 5
    assert all(0 <= w <= 3.0 for w in waits)
    assert caught.value.__notes__ == ["gave up after 6 attempts"]


def test_retry_does_not_retry_other_errors() -> None:
    flaky = Flaky(1, ValueError("bad input"))
    wrapped = retry(attempts=5, sleep=lambda s: None)(flaky)
    with pytest.raises(ValueError):
        wrapped(1)
    assert flaky.calls == 1


def test_retry_needs_one_attempt() -> None:
    with pytest.raises(ValueError, match="at least 1"):
        retry(attempts=0)


def test_cache_and_lru_cache() -> None:
    assert station_for("tarte tatin") == "pastry" and station_for("steak") == "grill"
    parse_price.cache_clear()
    assert parse_price(" €4,50 ") == Decimal("4.50")
    parse_price(" €4,50 ")
    assert parse_price.cache_info().hits == 1


def test_cached_property_builds_once() -> None:
    menu = Menu(["b2", "a1", "b1"])
    assert menu.by_initial == {"a": ["a1"], "b": ["b1", "b2"]}
    menu.by_initial
    assert menu.builds == 1


class Colour(StrEnum):
    RED = "red"


def test_singledispatch_converts_by_type() -> None:
    value = {
        "price": Decimal("1.10"),
        "day": date(2026, 1, 2),
        "at": datetime(2026, 1, 2, 3, 4, tzinfo=UTC),
        "colour": Colour.RED,
        "tags": {"b", "a"},
        "pair": (1, None),
        "nested": {1: [True, 2.5]},
    }
    converted = to_json_value(value)
    assert converted == {
        "price": "1.10",
        "day": "2026-01-02",
        "at": "2026-01-02T03:04:00+00:00",
        "colour": "red",
        "tags": ["a", "b"],
        "pair": [1, None],
        "nested": {"1": [True, 2.5]},
    }
    json.dumps(converted)


def test_singledispatch_refuses_unknown_types() -> None:
    with pytest.raises(TypeError, match="no JSON conversion registered for object"):
        to_json_value(object())


def test_deprecated_warns_and_still_works() -> None:
    with pytest.warns(DeprecationWarning, match="replaced by load_menu"):
        assert decorators.read_menu("a\n\nb") == ["a", "", "b"]  # type: ignore[deprecated]
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        assert load_menu("a\n\n b ") == ["a", "b"]


def test_demo_runs(capsys: pytest.CaptureFixture[str]) -> None:
    demo()
    out = capsys.readouterr().out
    assert "supplier answered '42 lemons' after 3 calls" in out
    assert "'price': '31.50'" in out
