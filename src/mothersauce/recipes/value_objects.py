"""
Dataclasses: small, honest value objects.

A dataclass turns a class that is mostly data into a few lines. The constructor, ``repr`` and ``==`` are written for
you, and the decorator's options say what kind of value it is:

- ``frozen=True`` makes instances immutable, so they can be shared between threads, hashed and used as keys.
- ``slots=True`` drops the per instance ``__dict__``: less memory, and a typo like ``ticket.tabel = 3`` fails.
- ``kw_only=True`` makes call sites read like a sentence and stops field order from becoming part of your API.
- ``order=True`` adds ``<`` and friends, comparing fields in order, which is exactly right for a watermark.

Validate in ``__post_init__`` so an invalid value can never exist, derive fields with ``field(init=False)``, hide
secrets with ``field(repr=False)``, and "change" a frozen value by building a new one with :func:`copy.replace`.
"""

import copy
from collections import Counter
from dataclasses import FrozenInstanceError, InitVar, asdict, dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, ClassVar

__all__ = ["BatchStats", "Credentials", "Money", "Ticket", "TicketLine", "Watermark", "demo"]

CENT = Decimal("0.01")


@dataclass(frozen=True, slots=True)
class Money:
    """
    An amount in one currency. Decimal, never float, so cents never drift.

    >>> Money(Decimal("4.5")) + Money(Decimal("0.25"))
    Money(amount=Decimal('4.75'), currency='EUR')

    :param amount: The amount; stored rounded to cents
    :param currency: ISO 4217 code, three capital letters
    :raises TypeError: When the amount is a float
    :raises ValueError: When the currency code is not three capital letters
    """

    amount: Decimal
    currency: str = "EUR"

    def __post_init__(self) -> None:
        if isinstance(self.amount, float):
            raise TypeError("pass money as Decimal or str, never float: 0.1 + 0.2 is not 0.3 in binary")
        if len(self.currency) != 3 or not self.currency.isalpha() or not self.currency.isupper():
            raise ValueError(f"currency must be three capital letters, got {self.currency!r}")
        # Frozen instances refuse normal assignment; object.__setattr__ is the sanctioned escape inside __post_init__.
        object.__setattr__(self, "amount", Decimal(self.amount).quantize(CENT))

    def __add__(self, other: Money) -> Money:
        """
        Add two amounts in the same currency.

        :param other: The amount to add
        :returns: The sum
        :raises ValueError: When the currencies differ
        """
        if other.currency != self.currency:
            raise ValueError(f"cannot add {other.currency} to {self.currency}")
        return Money(self.amount + other.amount, self.currency)

    def times(self, quantity: int) -> Money:
        """
        Multiply by a whole quantity.

        :param quantity: How many
        :returns: The amount times the quantity
        """
        return Money(self.amount * quantity, self.currency)


@dataclass(frozen=True, slots=True, kw_only=True)
class TicketLine:
    """
    One dish on a ticket. ``total`` is derived, so it can never disagree with the price and the quantity.

    :param dish: What was ordered
    :param quantity: How many, at least one
    :param unit_price: The price of one
    :raises ValueError: When the quantity is below one or the dish is blank
    """

    dish: str
    quantity: int
    unit_price: Money
    total: Money = field(init=False)

    def __post_init__(self) -> None:
        if self.quantity < 1:
            raise ValueError(f"quantity must be at least 1, got {self.quantity}")
        if not self.dish.strip():
            raise ValueError("dish must not be blank")
        object.__setattr__(self, "total", self.unit_price.times(self.quantity))


@dataclass(frozen=True, slots=True, kw_only=True)
class Ticket:
    """
    A table's order. Immutable: adding a line returns a new ticket and leaves the old one untouched.

    :param ticket_id: The id the till printed
    :param table: The table number
    :param opened_at: When the ticket was opened, timezone aware
    :param lines: The dishes, as a tuple so the ticket stays hashable
    :raises ValueError: When ``opened_at`` has no timezone
    """

    MAX_TABLE: ClassVar[int] = 99  # a class constant, not a field: dataclasses skip ClassVar annotations

    ticket_id: str
    table: int
    opened_at: datetime
    lines: tuple[TicketLine, ...] = ()

    def __post_init__(self) -> None:
        if self.opened_at.tzinfo is None:
            raise ValueError("opened_at must be timezone aware; naive datetimes are a bug waiting for summer time")
        if not 1 <= self.table <= self.MAX_TABLE:
            raise ValueError(f"table must be 1 to {self.MAX_TABLE}, got {self.table}")

    @property
    def total(self) -> Money:
        """
        The sum of every line.

        :returns: The ticket total, in the lines' currency; zero euros for an empty ticket
        """
        currency = self.lines[0].unit_price.currency if self.lines else "EUR"
        return sum((line.total for line in self.lines), start=Money(Decimal(0), currency))

    def with_line(self, line: TicketLine) -> Ticket:
        """
        Return a copy of the ticket with one more line.

        :param line: The line to add
        :returns: A new ticket; this one is unchanged
        """
        return copy.replace(self, lines=(*self.lines, line))

    def as_record(self) -> dict[str, Any]:
        """
        Flatten to plain dicts and tuples. Nested dataclasses become dicts; Decimals and datetimes stay as they are.

        :returns: The ticket as a dict
        """
        return asdict(self)


@dataclass(frozen=True, slots=True, order=True)
class Watermark:
    """
    How far an incremental load has read. ``order=True`` compares fields in order, so ``max()`` finds the newest.

    The ticket id breaks ties between tickets opened in the same second. It must sort in load order, so ids need
    a fixed width (``T-01001``) or a numeric comparison; ``'T-10' < 'T-9'`` as text.

    :param opened_at: The newest timestamp loaded
    :param ticket_id: The newest ticket id at that timestamp
    """

    opened_at: datetime
    ticket_id: str


@dataclass(slots=True)
class BatchStats:
    """
    A mutable accumulator. ``default_factory`` gives each instance its own counter instead of one shared default.

    :param seen: Records read
    :param rejected: Records that failed validation
    :param by_dish: Accepted lines per dish
    """

    seen: int = 0
    rejected: int = 0
    by_dish: Counter[str] = field(default_factory=Counter)

    def record(self, ticket: Ticket) -> None:
        """
        Count an accepted ticket.

        :param ticket: The ticket
        """
        self.seen += 1
        for line in ticket.lines:
            self.by_dish[line.dish] += line.quantity

    def reject(self) -> None:
        """Count a rejected record."""
        self.seen += 1
        self.rejected += 1


@dataclass(frozen=True, slots=True)
class Credentials:
    """
    Connection details whose password never reaches a log line.

    ``InitVar`` takes the raw password at construction without storing it as a field; ``repr=False`` keeps the stored
    secret out of ``repr`` and therefore out of tracebacks and log messages.

    :param user: The user name
    :param password: The password, consumed at construction
    """

    user: str
    password: InitVar[str]
    _secret: str = field(init=False, repr=False)

    def __post_init__(self, password: str) -> None:
        object.__setattr__(self, "_secret", password)

    def secret(self) -> str:
        """
        Return the password, explicitly, for the one place that needs it.

        :returns: The password
        """
        return self._secret


def demo() -> None:
    """Build a ticket, show what frozen buys you, and find the newest watermark."""
    opened = datetime(2026, 11, 12, 19, 30, tzinfo=UTC)
    sauce = TicketLine(dish="bearnaise", quantity=2, unit_price=Money(Decimal("4.50")))
    steak = TicketLine(dish="steak frites", quantity=1, unit_price=Money(Decimal("24")))
    empty = Ticket(ticket_id="T-1001", table=7, opened_at=opened)
    ticket = empty.with_line(sauce).with_line(steak)
    print(f"{ticket.ticket_id}: {len(ticket.lines)} lines, total {ticket.total.amount} {ticket.total.currency}")
    print(f"the original is untouched: {len(empty.lines)} lines")
    try:
        ticket.table = 8  # type: ignore[misc]  # mypy knows too; the runtime check is the demonstration
    except FrozenInstanceError:
        print("frozen: reassigning table raises FrozenInstanceError")
    same = TicketLine(dish="bearnaise", quantity=2, unit_price=Money(Decimal("4.5")))
    print(f"equal values are equal and hash alike: {same == sauce and hash(same) == hash(sauce)}")
    marks = [Watermark(opened, "T-1001"), Watermark(opened, "T-1003"), Watermark(opened, "T-1002")]
    print(f"newest watermark: {max(marks).ticket_id}")
    stats = BatchStats()
    stats.record(ticket)
    stats.reject()
    print(f"stats: seen {stats.seen}, rejected {stats.rejected}, top dish {stats.by_dish.most_common(1)[0][0]}")
    print(f"secrets stay out of repr: {Credentials('loader', 'hunter2')}")
