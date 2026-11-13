import json
import logging

import pytest

from mothersauce.recipes.enums import (
    Allergen,
    Severity,
    Station,
    TicketStatus,
    allergens_from,
    demo,
    prep_minutes,
)


def test_str_enum_members_are_plain_strings() -> None:
    assert json.dumps(Station.GRILL) == '"grill"' and f"{Station.GRILL}" == "grill"
    assert json.dumps({"station": Station.FRY}) == '{"station": "fry"}'


@pytest.mark.parametrize("text", ["grill", "GRILL", "  Grill\t"])
def test_parse_tolerates_case_and_spaces(text: str) -> None:
    assert Station.parse(text) is Station.GRILL


def test_parse_lists_the_choices_on_a_typo() -> None:
    with pytest.raises(ValueError, match="expected one of grill, fry, sauce, pastry, cold"):
        Station.parse("bar")


def test_hot_stations() -> None:
    assert {s for s in Station if s.is_hot} == {Station.GRILL, Station.FRY, Station.SAUCE}


def test_every_station_has_a_prep_time() -> None:
    assert all(prep_minutes(s) > 0 for s in Station)


def test_severity_orders_and_logs_at_its_level(caplog: pytest.LogCaptureFixture) -> None:
    assert Severity.ERROR > Severity.WARNING > Severity.INFO
    with caplog.at_level(logging.INFO):
        logging.getLogger("t").log(Severity.WARNING, "check")
    assert caplog.records[0].levelname == "WARNING"


@pytest.mark.parametrize(
    ("old", "new", "allowed"),
    [
        (TicketStatus.OPEN, TicketStatus.FIRED, True),
        (TicketStatus.OPEN, TicketStatus.VOID, True),
        (TicketStatus.OPEN, TicketStatus.PAID, False),
        (TicketStatus.FIRED, TicketStatus.SERVED, True),
        (TicketStatus.SERVED, TicketStatus.PAID, True),
        (TicketStatus.PAID, TicketStatus.OPEN, False),
        (TicketStatus.VOID, TicketStatus.FIRED, False),
    ],
)
def test_ticket_status_state_machine(old: TicketStatus, new: TicketStatus, allowed: bool) -> None:
    assert old.can_become(new) is allowed


def test_allergen_flags_combine() -> None:
    flags = allergens_from("Gluten, dairy ,")
    assert flags == Allergen.GLUTEN | Allergen.DAIRY
    assert Allergen.DAIRY in flags and Allergen.NUTS not in flags
    assert list(flags) == [Allergen.GLUTEN, Allergen.DAIRY]


def test_no_allergens() -> None:
    assert allergens_from("") is Allergen.NONE


def test_unknown_allergen() -> None:
    with pytest.raises(ValueError, match="unknown allergen 'celery'"):
        allergens_from("gluten, celery")


def test_demo_runs(capsys: pytest.CaptureFixture[str]) -> None:
    demo()
    out = capsys.readouterr().out
    assert "fired -> paid: refused" in out
    assert "GLUTEN|DAIRY|EGG" in out
