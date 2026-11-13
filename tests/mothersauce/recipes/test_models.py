import json
from decimal import Decimal
from typing import Any

import pytest
from pydantic import ValidationError

from mothersauce.recipes.models import (
    LineIn,
    TicketIn,
    TicketOpened,
    TicketPaid,
    TicketVoided,
    demo,
    explain,
    parse_events,
)


def a_line(**changes: Any) -> dict[str, Any]:
    return {"dish": "steak frites", "quantity": 1, "unit_price": "24.00", "station": "grill", **changes}


def a_ticket(**changes: Any) -> dict[str, Any]:
    return {"ticket_id": "T-1001", "table": 7, "opened_at": "2026-11-12T19:30:00Z", "lines": [a_line()], **changes}


def test_parses_and_coerces_csv_style_strings() -> None:
    ticket = TicketIn.model_validate(a_ticket(table="7", lines=[a_line(quantity="2", unit_price="4.5")]))
    assert ticket.table == 7
    assert ticket.lines[0].quantity == 2
    assert ticket.total == Decimal("9.0")


def test_strips_and_normalises_text() -> None:
    line = LineIn.model_validate(a_line(dish="  Steak   FRITES  "))
    assert line.dish == "steak frites"


def test_forbids_unknown_fields() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        LineIn.model_validate(a_line(colour="red"))


def test_models_are_frozen() -> None:
    line = LineIn.model_validate(a_line())
    with pytest.raises(ValidationError, match="frozen"):
        line.quantity = 3  # type: ignore[misc]


@pytest.mark.parametrize(
    ("changes", "where"),
    [
        ({"ticket_id": "1001"}, "ticket_id"),
        ({"table": 0}, "table"),
        ({"opened_at": "2026-11-12T19:30:00"}, "opened_at"),
        ({"lines": []}, "lines"),
        ({"lines": [a_line(quantity=0)]}, "lines.0.quantity"),
        ({"lines": [a_line(unit_price="1.234")]}, "lines.0.unit_price"),
        ({"lines": [a_line(station="bar")]}, "lines.0.station"),
    ],
)
def test_reports_the_path_to_each_bad_field(changes: dict[str, Any], where: str) -> None:
    with pytest.raises(ValidationError) as caught:
        TicketIn.model_validate(a_ticket(**changes))
    assert any(line.startswith(f"{where}:") for line in explain(caught.value))


def test_reports_every_problem_at_once() -> None:
    with pytest.raises(ValidationError) as caught:
        TicketIn.model_validate(a_ticket(ticket_id="x", table=0, extra=1))
    assert caught.value.error_count() == 3


def test_model_validator_checks_across_fields() -> None:
    lines = [a_line(quantity=50), a_line(dish="frites", quantity=11, station="fry")]
    with pytest.raises(ValidationError, match="61 items on one ticket"):
        TicketIn.model_validate(a_ticket(lines=lines))


def test_dump_includes_the_computed_total_as_json_safe_text() -> None:
    ticket = TicketIn.model_validate(a_ticket(lines=[a_line(quantity=2)]))
    dumped = ticket.model_dump(mode="json")
    assert dumped["total"] == "48.00"
    assert TicketIn.model_validate_json(json.dumps({k: v for k, v in dumped.items() if k != "total"})) == ticket


def test_discriminated_union_routes_each_event_to_its_model() -> None:
    raw = json.dumps(
        [
            {"kind": "opened", "ticket": a_ticket()},
            {"kind": "voided", "ticket_id": "T-1002", "reason": "walked out"},
            {"kind": "paid", "ticket_id": "T-1001", "amount": "24.00"},
        ]
    )
    events = parse_events(raw)
    assert [type(e) for e in events] == [TicketOpened, TicketVoided, TicketPaid]


def test_unknown_event_kind_names_the_discriminator() -> None:
    with pytest.raises(ValidationError, match="does not match any of the expected tags"):
        parse_events(json.dumps([{"kind": "refunded", "ticket_id": "T-1001"}]))


def test_schema_publishes_the_contract() -> None:
    schema = TicketIn.model_json_schema()
    assert set(schema["required"]) == {"ticket_id", "table", "opened_at", "lines"}
    assert schema["properties"]["table"]["maximum"] == 99


def test_demo_runs(capsys: pytest.CaptureFixture[str]) -> None:
    demo()
    out = capsys.readouterr().out
    assert "opened T-1001: 'steak frites' x2, total 48.00" in out
    assert "5 problems" in out
