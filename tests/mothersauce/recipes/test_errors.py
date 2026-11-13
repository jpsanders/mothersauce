from decimal import Decimal, InvalidOperation
from tomllib import TOMLDecodeError

import pytest

from mothersauce.recipes.errors import (
    ConfigError,
    KitchenError,
    Order,
    RecordError,
    SourceError,
    TransientError,
    demo,
    leaf_messages,
    load_config,
    parse_batch,
    parse_order,
    run_service,
    to_int_or_none,
)

GOOD = {"dish": "sole", "quantity": "2", "price": "31.50"}


def test_one_base_catches_everything_from_the_package() -> None:
    for error in (ConfigError("x"), TransientError("x"), SourceError("s", "x"), RecordError(1, "f", "x")):
        assert isinstance(error, KitchenError)


def test_record_error_is_also_a_value_error() -> None:
    with pytest.raises(ValueError, match="line 3, dish: missing"):
        parse_order(3, {"quantity": "1", "price": "1"})


def test_load_config_keeps_the_cause() -> None:
    with pytest.raises(ConfigError, match="not valid TOML") as caught:
        load_config("[kitchen")
    assert isinstance(caught.value.__cause__, TOMLDecodeError)


def test_load_config_needs_the_kitchen_table() -> None:
    assert load_config("[kitchen]\nname = 'Pass'\n") == {"kitchen": {"name": "Pass"}}
    with pytest.raises(ConfigError, match=r"no \[kitchen\] table"):
        load_config("[bar]\n")


@pytest.mark.parametrize(("value", "expected"), [("7", 7), (" 7 ", 7), ("seven", None), (None, None), (7.9, 7)])
def test_to_int_or_none(value: object, expected: int | None) -> None:
    assert to_int_or_none(value) == expected


def test_parse_order() -> None:
    assert parse_order(1, GOOD) == Order("sole", 2, Decimal("31.50"))


@pytest.mark.parametrize(
    ("row", "field"),
    [
        ({**GOOD, "dish": " "}, "dish"),
        ({**GOOD, "quantity": "0"}, "quantity"),
        ({**GOOD, "quantity": "lots"}, "quantity"),
        ({**GOOD, "price": "free"}, "price"),
    ],
)
def test_parse_order_names_the_field(row: dict[str, str], field: str) -> None:
    with pytest.raises(RecordError) as caught:
        parse_order(9, row)
    assert (caught.value.line, caught.value.field) == (9, field)


def test_bad_price_keeps_the_decimal_error_as_cause() -> None:
    with pytest.raises(RecordError) as caught:
        parse_order(1, {**GOOD, "price": "six"})
    assert isinstance(caught.value.__cause__, InvalidOperation)


def test_parse_batch_reports_every_bad_row() -> None:
    rows = [GOOD, {**GOOD, "dish": ""}, GOOD, {**GOOD, "price": "x"}]
    with pytest.raises(ExceptionGroup) as caught:
        parse_batch(rows, "lunch.csv")
    group = caught.value
    assert group.message == "lunch.csv: 2 of 4 rows failed"
    assert [e.line for e in group.exceptions if isinstance(e, RecordError)] == [2, 4]
    assert all(e.__notes__ == ["from lunch.csv"] for e in group.exceptions)


def test_parse_batch_returns_orders_when_all_rows_are_valid() -> None:
    assert len(parse_batch([GOOD, GOOD])) == 2
    assert parse_batch([]) == []


def test_except_star_splits_a_service_failure_by_kind() -> None:
    handled: dict[str, int] = {}
    try:
        run_service({"a.csv": [{**GOOD, "dish": ""}], "b.csv": None, "c.csv": [GOOD]})
    except* RecordError as records:
        handled["records"] = len(leaf_messages(records))
    except* SourceError as sources:
        handled["sources"] = len(sources.exceptions)
    assert handled == {"records": 1, "sources": 1}


def test_run_service_returns_orders_when_nothing_failed() -> None:
    assert run_service({"a.csv": [GOOD], "b.csv": [GOOD]}) == [Order("sole", 2, Decimal("31.50"))] * 2


def test_leaf_messages_flattens_nested_groups_with_notes() -> None:
    inner = RecordError(1, "dish", "missing")
    inner.add_note("from a.csv")
    nested = ExceptionGroup("outer", [ExceptionGroup("inner", [inner]), SourceError("b.csv", "gone")])
    assert leaf_messages(nested) == [
        "RecordError: line 1, dish: missing (from a.csv)",
        "SourceError: b.csv: gone",
    ]


def test_demo_runs(capsys: pytest.CaptureFixture[str]) -> None:
    demo()
    out = capsys.readouterr().out
    assert "3 bad records, every one reported" in out
    assert "handled separately: ['SourceError: dinner.csv: file not found']" in out
