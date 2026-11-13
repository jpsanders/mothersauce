"""
Enums: a closed set of names the type checker can see.

A bare string such as ``"grill"`` can be misspelt anywhere and nothing notices until production. An enum turns the set
of valid values into a type: mypy rejects a typo, the editor completes the names, and ``match`` can prove that every
case is handled.

- ``StrEnum`` members are real strings: they go into JSON, SQL and log lines without ``.value``.
- ``auto()`` on a ``StrEnum`` gives each member its lower case name.
- ``IntEnum`` suits values that have an order, such as severities.
- ``Flag`` combines members with ``|``, for sets such as the allergens in a dish.
- Methods and properties keep behaviour next to the values it depends on.
- A transition table turns an enum into a small state machine.
- ``assert_never`` in the last ``case`` makes a forgotten member a type error instead of a silent fall through.
"""

from enum import Flag, IntEnum, StrEnum, auto, unique
from typing import assert_never

__all__ = ["Allergen", "Severity", "Station", "TicketStatus", "allergens_from", "demo", "prep_minutes"]


@unique
class Station(StrEnum):
    """A kitchen station. ``@unique`` refuses two names for one value, which is almost always a copy paste slip."""

    GRILL = auto()
    FRY = auto()
    SAUCE = auto()
    PASTRY = auto()
    COLD = auto()

    @property
    def is_hot(self) -> bool:
        """
        Whether the station cooks with heat, so its tickets are fired first.

        :returns: True for grill, fry and sauce
        """
        return self in {Station.GRILL, Station.FRY, Station.SAUCE}

    @classmethod
    def parse(cls, text: str) -> Station:
        """
        Read a station from loose input: case and surrounding spaces do not matter.

        >>> Station.parse(" Grill ")
        <Station.GRILL: 'grill'>

        :param text: The station as typed
        :returns: The station
        :raises ValueError: Naming the valid stations when there is no match
        """
        try:
            return cls(text.strip().lower())
        except ValueError:
            raise ValueError(f"unknown station {text!r}; expected one of {', '.join(cls)}") from None


class Severity(IntEnum):
    """How bad a finding is. The values match the logging levels, so ``logger.log(severity, ...)`` just works."""

    INFO = 20
    WARNING = 30
    ERROR = 40


class TicketStatus(StrEnum):
    """Where a ticket is in service. :meth:`can_become` makes the enum a state machine."""

    OPEN = auto()
    FIRED = auto()
    SERVED = auto()
    PAID = auto()
    VOID = auto()

    def can_become(self, new: TicketStatus) -> bool:
        """
        Whether a ticket may move from this status to another.

        :param new: The status it would move to
        :returns: True when the move is allowed
        """
        return new in _TRANSITIONS[self]


# Outside the class, because every name assigned inside an Enum body becomes a member. frozendict, new in Python
# 3.15, keeps the table immutable: no code path can quietly allow a new transition at run time.
_TRANSITIONS: frozendict[TicketStatus, frozenset[TicketStatus]] = frozendict(
    {
        TicketStatus.OPEN: frozenset({TicketStatus.FIRED, TicketStatus.VOID}),
        TicketStatus.FIRED: frozenset({TicketStatus.SERVED, TicketStatus.VOID}),
        TicketStatus.SERVED: frozenset({TicketStatus.PAID}),
        TicketStatus.PAID: frozenset(),
        TicketStatus.VOID: frozenset(),
    }
)


class Allergen(Flag):
    """The allergens in a dish. Members combine with ``|`` and test with ``in``."""

    NONE = 0
    GLUTEN = auto()
    DAIRY = auto()
    EGG = auto()
    NUTS = auto()
    SHELLFISH = auto()


def allergens_from(text: str) -> Allergen:
    """
    Read a comma separated allergen list into one flag value.

    >>> allergens_from("gluten, dairy")
    <Allergen.GLUTEN|DAIRY: 3>

    :param text: Names such as ``"gluten, dairy"``; an empty string means none
    :returns: The combined flags
    :raises ValueError: When a name is not an allergen
    """
    combined = Allergen.NONE
    for name in filter(None, (part.strip().upper() for part in text.split(","))):
        try:
            combined |= Allergen[name]
        except KeyError:
            raise ValueError(f"unknown allergen {name.lower()!r}") from None
    return combined


def prep_minutes(station: Station) -> int:
    """
    How long a station takes per dish. Exhaustive: add a station and mypy flags this function until it is handled.

    :param station: The station
    :returns: Minutes per dish
    """
    match station:
        case Station.GRILL:
            return 12
        case Station.FRY:
            return 6
        case Station.SAUCE:
            return 4
        case Station.PASTRY:
            return 15
        case Station.COLD:
            return 3
        case _:
            assert_never(station)


def demo() -> None:
    """Parse loose input, run a ticket through the state machine and combine allergens."""
    station = Station.parse("  GRILL ")
    print(f"{station!r} is a str: {isinstance(station, str)}, json ready as {f'{station}'!r}, hot: {station.is_hot}")
    print("prep minutes:", ", ".join(f"{s} {prep_minutes(s)}" for s in Station))
    print(f"severities sort by value: {sorted([Severity.ERROR, Severity.INFO, Severity.WARNING])}")
    status = TicketStatus.OPEN
    for new in (TicketStatus.FIRED, TicketStatus.PAID, TicketStatus.SERVED, TicketStatus.PAID):
        allowed = status.can_become(new)
        print(f"{status} -> {new}: {'ok' if allowed else 'refused'}")
        status = new if allowed else status
    dish = allergens_from("gluten, dairy, egg")
    print(f"bearnaise allergens: {dish.name}; dairy: {Allergen.DAIRY in dish}; nut free: {Allergen.NUTS not in dish}")
    try:
        Station.parse("bar")
    except ValueError as error:
        print(f"a typo is caught with the choices: {error}")
