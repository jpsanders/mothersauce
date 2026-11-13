from datetime import date

import pytest

from mothersauce.recipes.generics import (
    Err,
    Ok,
    Page,
    Repository,
    Result,
    concat,
    defer,
    demo,
    first,
    is_row,
    parse_quantity,
    partition,
    top,
    try_parse,
)


def test_repository_keeps_both_types_and_chains() -> None:
    repo = Repository[int, str]().add(1, "one").add(2, "two")
    assert repo.get(2) == "two" and repo.get(3) is None
    assert list(repo) == ["one", "two"] and len(repo) == 2
    assert repo.find(lambda v: v.startswith("t")) == ["two"]


def test_repository_refuses_silent_overwrites() -> None:
    repo = Repository[str, int]().add("a", 1)
    with pytest.raises(KeyError, match="already stored"):
        repo.add("a", 2)


def test_require_raises_lookup_error() -> None:
    assert Repository[str, int]().add("a", 1).require("a") == 1
    with pytest.raises(LookupError, match="no item 'b'"):
        Repository[str, int]().require("b")


def test_add_returns_the_subclass() -> None:
    class Audited(Repository[str, int]):
        pass

    assert type(Audited().add("a", 1)) is Audited


def test_first() -> None:
    assert first(x for x in [3, 4]) == 3
    assert first([]) is None


def test_top_works_for_any_comparable() -> None:
    assert top([3, 9, 1, 7], 2) == [9, 7]
    assert top(["b", "a", "c"], 1) == ["c"]
    assert top([date(2026, 1, 2), date(2025, 1, 1)], 1) == [date(2026, 1, 2)]


def test_concat_keeps_the_type() -> None:
    assert concat("a", "b") == "ab"
    assert concat(b"a", b"b") == b"ab"


def test_page_default_type_parameter() -> None:
    page = Page[int](items=(1, 2))
    assert page.is_last and page.items == (1, 2)
    assert not Page[int, int](items=(), cursor=40).is_last


def test_defer_binds_now_and_calls_later() -> None:
    calls: list[int] = []

    def record(value: int, *, times: int = 1) -> int:
        calls.append(value)
        return value * times

    later = defer(record, 3, times=2)
    assert calls == []
    assert later() == 6 and calls == [3]


@pytest.mark.parametrize(
    ("value", "expected"),
    [({"a": "b"}, True), ({}, True), ({"a": 1}, False), ({1: "a"}, False), (["a"], False), ("a", False)],
)
def test_is_row(value: object, expected: bool) -> None:
    assert is_row(value) is expected


def test_parse_quantity_overloads() -> None:
    assert parse_quantity(" 12 ") == 12
    assert parse_quantity(None) is None
    with pytest.raises(ValueError):
        parse_quantity("a dozen")


def test_try_parse_and_partition() -> None:
    results: list[Result[int]] = [try_parse(int, t) for t in ["1", "x", "3"]]
    assert results[0] == Ok(1) and isinstance(results[1], Err)
    values, errors = partition(results)
    assert values == [1, 3]
    assert errors == ["'x': invalid literal for int() with base 10: 'x'"]


def test_result_error_type_can_be_anything() -> None:
    results: list[Result[str, int]] = [Ok("fine"), Err(404)]
    assert partition(results) == (["fine"], [404])


def test_demo_runs(capsys: pytest.CaptureFixture[str]) -> None:
    demo()
    out = capsys.readouterr().out
    assert "top two by covers: ['steak frites', 'tarte']" in out
    assert "parsed [2, 5]; 2 errors" in out
