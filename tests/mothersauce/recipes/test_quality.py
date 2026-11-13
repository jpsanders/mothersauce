from collections.abc import Iterator, Mapping
from datetime import date

import pytest

from mothersauce.recipes.enums import Severity
from mothersauce.recipes.quality import RULES, Override, Rule, check_batch, demo, rule

TODAY = date(2026, 11, 12)


def line(line_id: str = "L1", **changes: str) -> dict[str, str]:
    good = {"line_id": line_id, "dish": "sole", "station": "grill", "quantity": "2", "unit_price": "31.50"}
    return {**good, **changes}


@pytest.fixture
def restore_rules() -> Iterator[None]:
    saved = dict(RULES)
    yield
    RULES.clear()
    RULES.update(saved)


def test_clean_batch_is_all_accepted() -> None:
    report = check_batch([line("L1"), line("L2")], today=TODAY)
    assert len(report.accepted) == 2 and report.quarantined == [] and report.findings == []


@pytest.mark.parametrize(
    ("changes", "rule_name"),
    [
        ({"dish": " "}, "dish_present"),
        ({"quantity": "0"}, "quantity_positive"),
        ({"quantity": "two"}, "quantity_positive"),
        ({"unit_price": "-1"}, "price_not_negative"),
        ({"unit_price": "0"}, "price_not_zero"),
        ({"station": "bar"}, "known_station"),
    ],
)
def test_errors_quarantine(changes: dict[str, str], rule_name: str) -> None:
    report = check_batch([line(**changes)], today=TODAY)
    assert report.accepted == [] and len(report.quarantined) == 1
    assert rule_name in report.by_rule()


def test_a_crashing_check_counts_as_failed() -> None:
    record = line()
    del record["unit_price"]
    report = check_batch([record], today=TODAY)
    assert {"price_not_negative", "price_not_zero"} <= set(report.by_rule())


def test_warnings_are_reported_but_let_through() -> None:
    report = check_batch([line(quantity="21")], today=TODAY)
    assert len(report.accepted) == 1
    assert [(f.rule, f.severity) for f in report.findings] == [("large_quantity", Severity.WARNING)]


def test_duplicates_after_the_first_are_quarantined() -> None:
    report = check_batch([line("L1"), line("L2"), line("L1")], today=TODAY)
    assert [r["line_id"] for r in report.accepted] == ["L1", "L2"]
    assert report.by_rule() == {"unique_key": 1}


def test_override_waives_one_rule_for_one_record() -> None:
    meal = Override("L5", "price_not_zero", "head chef", "staff meal")
    report = check_batch([line("L5", unit_price="0"), line("L6", unit_price="0")], overrides=[meal], today=TODAY)
    assert [r["line_id"] for r in report.accepted] == ["L5"]
    assert [f.record_id for f in report.waived()] == ["L5"]
    assert report.by_rule() == {"price_not_zero": 1}


def test_override_waives_only_its_rule() -> None:
    meal = Override("L5", "price_not_zero", "head chef", "staff meal")
    report = check_batch([line("L5", unit_price="0", station="bar")], overrides=[meal], today=TODAY)
    assert report.quarantined and report.by_rule() == {"known_station": 1}


def test_expired_override_no_longer_applies() -> None:
    old = Override("L5", "price_not_zero", "head chef", "launch week", expires=date(2026, 11, 1))
    assert not old.active(TODAY) and old.active(date(2026, 11, 1))
    report = check_batch([line("L5", unit_price="0")], overrides=[old], today=TODAY)
    assert report.quarantined and report.waived() == []


@pytest.mark.usefixtures("restore_rules")
def test_rules_are_registered_by_decorator() -> None:
    @rule("no_soup_on_mondays", Severity.WARNING, "soup is a weekend dish")
    def no_soup(record: Mapping[str, str]) -> bool:
        return record.get("dish") != "soup"

    assert isinstance(RULES["no_soup_on_mondays"], Rule)
    assert check_batch([line(dish="soup")], today=TODAY).by_rule() == {"no_soup_on_mondays": 1}
    with pytest.raises(ValueError, match="already registered"):
        rule("no_soup_on_mondays", Severity.ERROR, "again")(no_soup)


def test_custom_rule_set_and_key() -> None:
    only = {"known_station": RULES["known_station"]}
    report = check_batch([{"id": "x", "station": "bar"}], rules=only, key="id", today=TODAY)
    assert report.findings[0].record_id == "x"


def test_demo_runs(capsys: pytest.CaptureFixture[str]) -> None:
    demo()
    out = capsys.readouterr().out
    assert "accepted ['L1', 'L2', 'L5'], quarantined ['L3', 'L4', 'L1']" in out
    assert "waived: L5 price_not_zero, by head chef" in out


@pytest.mark.usefixtures("restore_rules")
def test_a_crashing_rule_fails_its_check_without_stopping_the_run() -> None:
    @rule("divides_by_zero", Severity.ERROR, "a buggy rule")
    def buggy(record: Mapping[str, str]) -> bool:
        return 1 / 0 > 0

    report = check_batch([line("L1"), line("L2")], today=TODAY)
    assert len(report.quarantined) == 2 and report.by_rule() == {"divides_by_zero": 2}


def test_by_rule_lists_the_most_frequent_first() -> None:
    batch = [line("L1", station="bar"), line("L2", quantity="0"), line("L3", quantity="0")]
    assert list(check_batch(batch, today=TODAY).by_rule()) == ["quantity_positive", "known_station"]
