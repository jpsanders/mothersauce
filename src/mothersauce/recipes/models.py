"""
Pydantic: parse, don't validate, at the edges of the system.

Data from outside, a CSV row, a JSON request, a message from a queue, is untrusted. A pydantic model turns it into
typed, validated objects in one step and reports every bad field at once. Inside the system you pass the parsed
objects around and never check the same thing twice.

Production defaults worth copying:

- ``extra="forbid"``, so a misspelt field fails loudly instead of vanishing.
- ``frozen=True`` for values, so a parsed record cannot be edited behind your back.
- ``str_strip_whitespace=True``, because spreadsheets pad cells.
- Constraints written once as ``Annotated`` types and reused by every model.
- A discriminated union to route mixed event types without a chain of ``if`` statements.
- ``TypeAdapter`` to validate a whole batch in one call, and ``model_json_schema`` to publish the contract.

Lax mode, the default, turns ``"2"`` into ``2``, which is what you want for CSV. For internal APIs between your own
services, ``strict=True`` refuses the conversion instead.
"""

from decimal import Decimal
from typing import Annotated, Any, Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    TypeAdapter,
    ValidationError,
    computed_field,
    field_validator,
    model_validator,
)

__all__ = [
    "Event",
    "LineIn",
    "Price",
    "Quantity",
    "Record",
    "Station",
    "TicketId",
    "TicketIn",
    "TicketOpened",
    "TicketPaid",
    "TicketVoided",
    "demo",
    "explain",
    "parse_events",
]

# Reusable constraints: one definition, every model that needs a ticket id or a quantity gets the same rules.
TicketId = Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^T-[0-9]{4,}$")]  # [0-9], not \d
Quantity = Annotated[int, Field(ge=1, le=50)]
Price = Annotated[Decimal, Field(ge=0, max_digits=8, decimal_places=2)]
Station = Literal["grill", "fry", "sauce", "pastry", "cold"]

MAX_ITEMS_PER_TICKET = 60


class Record(BaseModel):
    """The base for every incoming record: one place for the production defaults."""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)


class LineIn(Record):
    """
    One dish as the till sends it.

    :param dish: The dish name; normalised to lower case with single spaces
    :param quantity: 1 to 50
    :param unit_price: The price of one, at most two decimal places
    :param station: The kitchen station that cooks it
    """

    dish: str = Field(min_length=1, max_length=80)
    quantity: Quantity
    unit_price: Price
    station: Station

    @field_validator("dish")
    @classmethod
    def normalise_dish(cls, value: str) -> str:
        """
        Lower case the dish and collapse inner spaces, so "Steak  Frites" and "steak frites" are one dish.

        :param value: The dish as sent
        :returns: The normalised dish
        """
        return " ".join(value.lower().split())


class TicketIn(Record):
    """
    A whole ticket. The total is computed, never sent, so it cannot disagree with the lines.

    :param ticket_id: Shaped like ``T-1001``
    :param table: 1 to 99
    :param opened_at: When it was opened; must carry a timezone
    :param lines: At least one line
    """

    ticket_id: TicketId
    table: int = Field(ge=1, le=99)
    opened_at: AwareDatetime
    lines: tuple[LineIn, ...] = Field(min_length=1)

    @computed_field  # type: ignore[prop-decorator]  # pydantic's documented pattern; mypy dislikes the stacking
    @property
    def total(self) -> Decimal:
        """
        The ticket total, included when the model is dumped.

        :returns: The sum of quantity times price over every line
        """
        return sum((line.unit_price * line.quantity for line in self.lines), start=Decimal(0))

    @model_validator(mode="after")
    def within_capacity(self) -> TicketIn:
        """
        Reject tickets the kitchen could never cook in one go. Runs after the fields are valid, so it can use them.

        :returns: The ticket
        :raises ValueError: When the ticket holds more than 60 items
        """
        items = sum(line.quantity for line in self.lines)
        if items > MAX_ITEMS_PER_TICKET:
            raise ValueError(f"{items} items on one ticket; the kitchen takes at most {MAX_ITEMS_PER_TICKET}")
        return self


class TicketOpened(Record):
    """
    A new ticket arrived.

    :param kind: Always ``opened``; the union routes on it
    :param ticket: The ticket
    """

    kind: Literal["opened"]
    ticket: TicketIn


class TicketVoided(Record):
    """
    A ticket was cancelled.

    :param kind: Always ``voided``
    :param ticket_id: Which ticket
    :param reason: Why, for the audit trail
    """

    kind: Literal["voided"]
    ticket_id: TicketId
    reason: str = Field(min_length=3)


class TicketPaid(Record):
    """
    A ticket was paid.

    :param kind: Always ``paid``
    :param ticket_id: Which ticket
    :param amount: What was paid
    """

    kind: Literal["paid"]
    ticket_id: TicketId
    amount: Price


# The discriminator tells pydantic to read ``kind`` first and validate against that one model only: faster, and the
# errors name the right model instead of listing every way the record failed to be each of them.
Event = Annotated[TicketOpened | TicketVoided | TicketPaid, Field(discriminator="kind")]
_EVENTS: TypeAdapter[list[Event]] = TypeAdapter(list[Event])


def parse_events(raw: str | bytes) -> list[Event]:
    """
    Validate a JSON array of events in one call.

    Pydantic parses the JSON itself, faster than ``json.loads`` followed by ``validate_python``.

    :param raw: The JSON text
    :returns: Typed events, each one the right model for its ``kind``
    """
    return _EVENTS.validate_json(raw)


def explain(error: ValidationError) -> list[str]:
    """
    Turn a validation error into one readable line per problem, with the path to the bad field.

    :param error: What pydantic raised
    :returns: Lines such as ``0.opened.ticket.lines.0.quantity: Input should be greater than or equal to 1``
    """
    return [".".join(str(part) for part in item["loc"]) + f": {item['msg']}" for item in error.errors()]


def _sample() -> list[dict[str, Any]]:
    line = {"dish": "  Steak  Frites ", "quantity": 2, "unit_price": "24.00", "station": "grill"}
    ticket = {"ticket_id": "T-1001", "table": 7, "opened_at": "2026-11-12T19:30:00+00:00", "lines": [line]}
    return [
        {"kind": "opened", "ticket": ticket},
        {"kind": "paid", "ticket_id": "T-1001", "amount": "48.00"},
        {"kind": "voided", "ticket_id": "T-1002", "reason": "table walked out"},
    ]


def demo() -> None:
    """Parse a batch of mixed events, then show what a bad record's errors look like."""
    events = parse_events(TypeAdapter(list[dict[str, Any]]).dump_json(_sample()))
    for event in events:
        match event:
            case TicketOpened(ticket=ticket):
                first = ticket.lines[0]
                print(f"opened {ticket.ticket_id}: {first.dish!r} x{first.quantity}, total {ticket.total}")
            case TicketPaid(ticket_id=ticket_id, amount=amount):
                print(f"paid   {ticket_id}: {amount}")
            case TicketVoided(ticket_id=ticket_id, reason=reason):
                print(f"voided {ticket_id}: {reason}")
    bad = {"ticket_id": "1001", "table": 0, "opened_at": "2026-11-12T19:30:00", "lines": [], "tip": 5}
    try:
        TicketIn.model_validate(bad)
    except ValidationError as error:
        print(f"one bad ticket, {error.error_count()} problems, all reported at once:")
        for line in explain(error):
            print(f"  {line}")
    print("the contract, for anyone sending tickets:", ", ".join(TicketIn.model_json_schema()["properties"]))
