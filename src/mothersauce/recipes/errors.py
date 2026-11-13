"""
Errors: a hierarchy you can catch, chains you can follow, and batches that report every failure.

One base exception per package lets a caller catch "anything from this library" in one clause, while subclasses let
it handle the cases it cares about. Raise the most specific one, and keep the original cause with
``raise ... from error`` so the traceback shows what went wrong and why. ``add_note`` attaches context, such as the
file and the line, without inventing a new exception type for it.

A batch job must not stop at the first bad record. Collect the failures, finish the batch, and raise them together
as an ``ExceptionGroup``. The caller's ``except*`` clauses then handle each kind on its own. Since Python 3.14 an
``except`` that lists several types needs no parentheses, unless it binds a name with ``as``.

Catch narrowly, close to where you can act on the error, and never with a bare ``except:``.
"""

import tomllib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

__all__ = [
    "ConfigError",
    "KitchenError",
    "Order",
    "RecordError",
    "SourceError",
    "TransientError",
    "demo",
    "leaf_messages",
    "load_config",
    "parse_batch",
    "parse_order",
    "run_service",
    "to_int_or_none",
]


class KitchenError(Exception):
    """
    The base of every single error this package raises: ``except KitchenError`` catches each of them.

    A batch reports its failures together in an ``ExceptionGroup``; handle those with ``except* KitchenError``.
    """


class ConfigError(KitchenError):
    """The configuration cannot be used. Not worth retrying: a person has to fix it."""


class TransientError(KitchenError):
    """Something that may pass, such as a timeout. Retry logic catches this class and no other."""


class SourceError(KitchenError):
    """
    A whole source failed, such as a missing file or a refused connection.

    :param source: Which source
    :param reason: What happened
    """

    def __init__(self, source: str, reason: str) -> None:
        super().__init__(f"{source}: {reason}")
        self.source = source


class RecordError(KitchenError, ValueError):
    """
    One record is invalid. Also a ``ValueError``, so generic code that already catches ``ValueError`` keeps working.

    :param line: The line number in the source
    :param field: The field at fault
    :param reason: What is wrong with it
    """

    def __init__(self, line: int, field: str, reason: str) -> None:
        super().__init__(f"line {line}, {field}: {reason}")
        self.line = line
        self.field = field


@dataclass(frozen=True, slots=True)
class Order:
    """
    A parsed order line.

    :param dish: The dish
    :param quantity: How many
    :param price: The price of one
    """

    dish: str
    quantity: int
    price: Decimal


def load_config(text: str) -> dict[str, object]:
    """
    Parse TOML configuration, turning the parser's error into this package's own, with the original kept as cause.

    :param text: The TOML
    :returns: The settings
    :raises ConfigError: When the TOML is invalid or has no kitchen table
    """
    try:
        settings = tomllib.loads(text)
    except tomllib.TOMLDecodeError as error:
        raise ConfigError("the configuration is not valid TOML") from error
    if "kitchen" not in settings:
        raise ConfigError("the configuration has no [kitchen] table")
    return settings


def to_int_or_none(text: object) -> int | None:
    """
    Read an integer, or None when it is not one. Python 3.14's ``except A, B:`` needs no parentheses.

    :param text: Anything
    :returns: The integer, or None
    """
    if isinstance(text, bool) or (isinstance(text, float) and not text.is_integer()):
        return None  # int() would turn True into 1 and quietly cut 7.9 to 7
    try:
        number: int = int(text)  # type: ignore[call-overload]  # any object may arrive here; int() decides
    except ValueError, TypeError:
        return None
    return number


def parse_order(line: int, row: Mapping[str, str]) -> Order:
    """
    Parse one row, raising a :class:`RecordError` that names the line and the field.

    :param line: The row's line number, for the error message
    :param row: The raw row
    :returns: The order
    :raises RecordError: When a field is missing or invalid
    """
    dish = row.get("dish", "").strip()
    if not dish:
        raise RecordError(line, "dish", "missing")
    quantity = to_int_or_none(row.get("quantity"))
    if quantity is None or quantity < 1:
        raise RecordError(line, "quantity", f"expected a whole number above 0, got {row.get('quantity')!r}")
    try:
        price = Decimal(row.get("price", ""))
    except InvalidOperation as error:
        raise RecordError(line, "price", f"not a number: {row.get('price')!r}") from error
    if not price.is_finite() or price < 0:
        raise RecordError(line, "price", f"must be a finite amount of zero or more, got {row.get('price')!r}")
    return Order(dish, quantity, price)


def parse_batch(rows: Iterable[Mapping[str, str]], source: str = "batch") -> list[Order]:
    """
    Parse every row, then raise all the failures together, so one bad row never hides the next.

    Each failure gets a note naming its source: the batch knows that context, the parser of one row does not.

    :param rows: The raw rows
    :param source: The batch's name, for the messages
    :returns: The orders, when every row was valid
    :raises ExceptionGroup: Holding one ``RecordError`` per bad row
    """
    orders: list[Order] = []
    errors: list[RecordError] = []
    total = 0
    for total, row in enumerate(rows, start=1):
        try:
            orders.append(parse_order(total, row))
        except RecordError as error:
            error.add_note(f"from {source}")
            errors.append(error)
    if errors:
        raise ExceptionGroup(f"{source}: {len(errors)} of {total} rows failed", errors)
    return orders


def run_service(batches: Mapping[str, list[dict[str, str]] | None]) -> list[Order]:
    """
    Parse several batches; ``None`` stands for a file that could not be read. Every failure surfaces at the end.

    :param batches: Rows per source name
    :returns: Every order, when nothing failed
    :raises ExceptionGroup: Holding a group per failed batch and a ``SourceError`` per missing source
    """
    orders: list[Order] = []
    failures: list[Exception] = []
    for source, rows in batches.items():
        if rows is None:
            failures.append(SourceError(source, "file not found"))
            continue
        try:
            orders += parse_batch(rows, source)
        except ExceptionGroup as group:
            failures.append(group)
    if failures:
        raise ExceptionGroup("service failed", failures)
    return orders


def leaf_messages(error: BaseException) -> list[str]:
    """
    Flatten an exception, or a group of groups, into one line per failure with its notes, for logs and reports.

    :param error: Any exception
    :returns: One line per leaf exception
    """
    if isinstance(error, BaseExceptionGroup):
        return [line for inner in error.exceptions for line in leaf_messages(inner)]
    notes = getattr(error, "__notes__", [])
    return [f"{type(error).__name__}: {error}" + "".join(f" ({note})" for note in notes)]


def demo() -> None:
    """Chain a config error, collect a batch's failures and handle each kind with except*."""
    try:
        load_config("[kitchen\nname = 'Pass'")
    except ConfigError as error:
        print(f"{error}; caused by {type(error.__cause__).__name__}: {error.__cause__}")
    lunch = [
        {"dish": "sole", "quantity": "1", "price": "31.50"},
        {"dish": "", "quantity": "2", "price": "9"},
        {"dish": "tart", "quantity": "two", "price": "8"},
        {"dish": "soup", "quantity": "1", "price": "six"},
    ]
    try:
        run_service({"lunch.csv": lunch, "dinner.csv": None})
    except* RecordError as records:
        print(f"{len(leaf_messages(records))} bad records, every one reported:")
        for line in leaf_messages(records):
            print(f"  {line}")
    except* SourceError as sources:
        print(f"handled separately: {leaf_messages(sources)}")
    print(f"a RecordError is still a ValueError for old callers: {issubclass(RecordError, ValueError)}")
    print(f"to_int_or_none: {to_int_or_none('7')}, {to_int_or_none('seven')}, {to_int_or_none(None)}")
