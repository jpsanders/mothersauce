from datetime import datetime
from decimal import Decimal

import pytest

from mothersauce.recipes.data_structures import (
    MENU,
    LRUCache,
    Reading,
    TicketJson,
    demo,
    group_by,
    layered,
    merge_by_time,
    prep_order,
    prep_waves,
    price_band,
    top,
)


def test_group_by_keeps_input_order() -> None:
    assert group_by([3, 1, 4, 1, 5], lambda n: n % 2) == {1: [3, 1, 1, 5], 0: [4]}
    assert group_by([], len) == {}


def test_top_counts_and_ranks() -> None:
    assert top(["a", "b", "a", "c", "b", "a"], 2) == [("a", 3), ("b", 2)]


def test_merge_by_time_is_lazy_and_sorted() -> None:
    def at(hour: int, fridge: str) -> Reading:
        return Reading(datetime(2026, 1, 1, hour), fridge, 4.0)

    merged = merge_by_time([at(1, "a"), at(5, "a")], [at(2, "b"), at(3, "b")], [])
    assert [(r.at.hour, r.fridge) for r in merged] == [(1, "a"), (2, "b"), (3, "b"), (5, "a")]


@pytest.mark.parametrize(
    ("price", "band"), [("0", "snack"), ("9.99", "snack"), ("10", "starter"), ("25", "main"), ("30", "special")]
)
def test_price_band_boundaries(price: str, band: str) -> None:
    assert price_band(Decimal(price)) == band


def test_lru_cache_evicts_the_least_recently_used() -> None:
    cache = LRUCache[str, int](2)
    cache.put("a", 1)
    cache.put("b", 2)
    assert cache.get("a") == 1
    cache.put("c", 3)
    assert cache.keys() == ["a", "c"]
    assert cache.get("b") is None


def test_lru_cache_update_refreshes_the_key() -> None:
    cache = LRUCache[str, int](2)
    cache.put("a", 1)
    cache.put("b", 2)
    cache.put("a", 9)
    cache.put("c", 3)
    assert cache.keys() == ["a", "c"] and cache.get("a") == 9


def test_lru_cache_needs_capacity() -> None:
    with pytest.raises(ValueError, match="at least 1"):
        LRUCache[str, int](0)


def test_layered_reads_through_without_copying() -> None:
    defaults = {"timeout": "30", "retries": "3"}
    settings = layered({"timeout": "5"}, defaults)
    assert (settings["timeout"], settings["retries"]) == ("5", "3")
    defaults["retries"] = "9"
    assert settings["retries"] == "9"


def test_frozen_menu() -> None:
    with pytest.raises(TypeError):
        MENU["new"] = Decimal(1)  # type: ignore[index]
    assert hash(MENU) == hash(frozendict(MENU))


def test_named_tuple_and_typed_dict() -> None:
    reading = Reading(datetime(2026, 1, 1), "walk in", 3.5)
    at, fridge, celsius = reading
    assert fridge == "walk in" and reading.celsius == celsius
    ticket: TicketJson = {"ticket_id": "T-1", "dishes": ["sole"]}
    assert ticket["dishes"] == ["sole"]


def test_prep_order_respects_dependencies() -> None:
    order = prep_order({"sauce": {"stock"}, "plate": {"sauce", "herbs"}, "stock": set(), "herbs": set()})
    assert order.index("stock") < order.index("sauce") < order.index("plate")
    assert order.index("herbs") < order.index("plate")


def test_prep_order_names_the_cycle() -> None:
    with pytest.raises(ValueError, match="circular dependency: .*sauce.*stock|circular dependency: .*stock.*sauce"):
        prep_order({"sauce": {"stock"}, "stock": {"sauce"}})


def test_prep_waves_group_parallel_work() -> None:
    waves = prep_waves({"c": {"a", "b"}, "d": {"c"}, "a": set(), "b": set()})
    assert waves == [["a", "b"], ["c"], ["d"]]


def test_demo_runs(capsys: pytest.CaptureFixture[str]) -> None:
    demo()
    out = capsys.readouterr().out
    assert "prep in parallel waves: [['garnish', 'roux', 'stock'], ['veloute'], ['plate']]" in out
    assert "LRU kept ['a', 'c']" in out
