from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from mothersauce.recipes.value_objects import BatchStats, Credentials, Money, Ticket, TicketLine, Watermark, demo

OPENED = datetime(2026, 11, 12, 19, 30, tzinfo=UTC)


def line(dish: str = "bearnaise", quantity: int = 2, price: str = "4.50") -> TicketLine:
    return TicketLine(dish=dish, quantity=quantity, unit_price=Money(Decimal(price)))


def test_money_rounds_to_cents_and_adds() -> None:
    assert Money(Decimal("1.005")).amount == Decimal("1.00")  # banker's rounding, the Decimal default
    assert (Money(Decimal("4.5")) + Money(Decimal("0.25"))).amount == Decimal("4.75")


@pytest.mark.parametrize("currency", ["eur", "EURO", "E1R", ""])
def test_money_rejects_bad_currency(currency: str) -> None:
    with pytest.raises(ValueError, match="three capital letters"):
        Money(Decimal(1), currency)


def test_money_rejects_float() -> None:
    with pytest.raises(TypeError, match="never float"):
        Money(0.1)  # type: ignore[arg-type]


def test_money_refuses_mixed_currencies() -> None:
    with pytest.raises(ValueError, match="cannot add USD to EUR"):
        Money(Decimal(1)) + Money(Decimal(1), "USD")


def test_line_total_is_derived() -> None:
    assert line(quantity=3, price="2").total == Money(Decimal(6))


@pytest.mark.parametrize(("dish", "quantity", "message"), [("x", 0, "at least 1"), ("  ", 1, "blank")])
def test_line_validates(dish: str, quantity: int, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        line(dish=dish, quantity=quantity)


def test_ticket_is_immutable_and_with_line_copies() -> None:
    empty = Ticket(ticket_id="T-1", table=4, opened_at=OPENED)
    full = empty.with_line(line()).with_line(line("frites", 1, "5"))
    assert empty.lines == ()
    assert full.total == Money(Decimal("14.00"))
    with pytest.raises(FrozenInstanceError):
        full.table = 5  # type: ignore[misc]


def test_slots_reject_unknown_attributes() -> None:
    ticket = Ticket(ticket_id="T-1", table=4, opened_at=OPENED)
    with pytest.raises((AttributeError, TypeError)):
        ticket.tabel = 5  # type: ignore[attr-defined]


def test_ticket_validates() -> None:
    with pytest.raises(ValueError, match="timezone aware"):
        Ticket(ticket_id="T-1", table=4, opened_at=datetime(2026, 1, 1))
    with pytest.raises(ValueError, match="table must be 1 to 99"):
        Ticket(ticket_id="T-1", table=100, opened_at=OPENED)


def test_empty_ticket_totals_zero() -> None:
    assert Ticket(ticket_id="T-1", table=1, opened_at=OPENED).total == Money(Decimal(0))


def test_as_record_flattens_nested_values() -> None:
    record = Ticket(ticket_id="T-1", table=4, opened_at=OPENED, lines=(line(),)).as_record()
    assert record["lines"][0]["total"] == {"amount": Decimal("9.00"), "currency": "EUR"}


def test_equal_values_hash_alike() -> None:
    assert {line(), line(price="4.5")} == {line()}


def test_watermark_orders_by_time_then_id() -> None:
    later = datetime(2026, 11, 12, 20, 0, tzinfo=UTC)
    marks = [Watermark(OPENED, "T-9"), Watermark(later, "T-1"), Watermark(later, "T-2")]
    assert max(marks) == Watermark(later, "T-2")


def test_batch_stats_have_their_own_counters() -> None:
    first, second = BatchStats(), BatchStats()
    first.record(Ticket(ticket_id="T-1", table=1, opened_at=OPENED, lines=(line(),)))
    second.reject()
    assert first.by_dish == {"bearnaise": 2} and second.by_dish == {}
    assert (second.seen, second.rejected) == (1, 1)


def test_credentials_hide_the_secret() -> None:
    creds = Credentials("loader", "hunter2")
    assert "hunter2" not in repr(creds)
    assert creds.secret() == "hunter2"


def test_demo_runs(capsys: pytest.CaptureFixture[str]) -> None:
    demo()
    out = capsys.readouterr().out
    assert "total 33.00 EUR" in out and "newest watermark: T-1003" in out
