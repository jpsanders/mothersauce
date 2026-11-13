"""
Decorators: cross cutting behaviour written once and applied by name.

Retrying a flaky call, counting calls, caching a slow lookup, warning about an old function: none of this belongs in
the function's own logic, and copying it into every function guarantees that one copy drifts. A decorator wraps the
function instead.

Rules that keep decorators safe in production:

- ``functools.wraps`` copies the name, docstring and signature, so logs, ``help()`` and ``inspect`` stay truthful.
- ``[**P, R]`` keeps the wrapped signature for mypy, so callers are still checked against the real parameters.
- A decorator that takes arguments is a function that returns a decorator. Keep that layering easy to see.
- Retry only what is safe to repeat, only for errors that can pass, with exponential backoff, jitter and a limit.

``functools`` ships the everyday ones: ``cache`` and ``lru_cache`` for pure functions, ``cached_property`` for a value
computed once per object, and ``singledispatch`` to pick an implementation by the type of the first argument.
``warnings.deprecated`` marks old functions so that both mypy and the runtime warn their callers.
"""

import logging
import random
import time
import warnings
from collections import Counter
from collections.abc import Callable, Iterator
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from functools import cache, cached_property, lru_cache, singledispatch, wraps
from typing import Any
from warnings import deprecated

__all__ = [
    "CALLS",
    "Menu",
    "counted",
    "demo",
    "load_menu",
    "parse_price",
    "read_menu",
    "retry",
    "station_for",
    "to_json_value",
]

logger = logging.getLogger(__name__)

CALLS: Counter[str] = Counter()


def _name(func: Callable[..., object]) -> str:
    """
    Name any callable for logs: functions have ``__qualname__``, callable objects and partials may not.

    :param func: The callable
    :returns: Its qualified name, or its class name
    """
    return getattr(func, "__qualname__", None) or type(func).__qualname__


def counted[**P, R](func: Callable[P, R]) -> Callable[P, R]:
    """
    Count every call, keyed by the function's qualified name. The simplest useful decorator, with its full typing.

    :param func: The function to wrap
    :returns: A wrapper with the same signature
    """

    @wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        CALLS[_name(func)] += 1
        return func(*args, **kwargs)

    return wrapper


def retry[**P, R](
    *,
    attempts: int = 3,
    on: tuple[type[Exception], ...] = (ConnectionError, TimeoutError),
    base_delay: float = 0.2,
    max_delay: float = 5.0,
    sleep: Callable[[float], None] = time.sleep,
    rng: random.Random | None = None,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """
    Retry a call that fails with a transient error, waiting longer each time.

    The wait before retry ``n`` is a random time between zero and ``base_delay * 2 ** (n - 1)``, capped at
    ``max_delay``:
    exponential backoff with full jitter, so a hundred workers that failed together do not retry together.

    :param attempts: Total tries, the first included
    :param on: The exceptions worth retrying; anything else fails at once
    :param base_delay: Seconds of the first backoff step
    :param max_delay: The longest wait
    :param sleep: How to wait; tests pass a fake
    :param rng: The random source for jitter; tests pass a seeded one
    :returns: The decorator
    :raises ValueError: When attempts is below one
    """
    if attempts < 1:
        raise ValueError("attempts must be at least 1")
    jitter = rng or random.Random()  # nosec B311  # jitter spreads retries; it protects nothing

    def decorate(func: Callable[P, R]) -> Callable[P, R]:
        @wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            for attempt in range(1, attempts + 1):
                try:
                    return func(*args, **kwargs)
                except on as error:
                    if attempt == attempts:
                        error.add_note(f"gave up after {attempts} attempts")
                        raise
                    delay = jitter.uniform(0, min(max_delay, base_delay * 2 ** (attempt - 1)))
                    logger.warning("%s failed (%s); retry %d in %.2fs", _name(func), error, attempt, delay)
                    sleep(delay)
            raise AssertionError("unreachable")  # pragma: no cover

        return wrapper

    return decorate


@cache
def station_for(dish: str) -> str:
    """
    Look up the station for a dish. ``@cache`` remembers every answer: right for a small, pure lookup.

    :param dish: The dish
    :returns: The station
    """
    return "pastry" if any(word in dish for word in ("tart", "brulee", "souffle")) else "grill"


@lru_cache(maxsize=1024)
def parse_price(text: str) -> Decimal:
    """
    Parse a price such as ``"€4,50"``. ``lru_cache`` bounds the memory when inputs are many and repeat often.

    :param text: The price as printed
    :returns: The price
    """
    return Decimal(text.strip().lstrip("€$£").replace(",", "."))


class Menu:
    """
    A menu with an index that is built on first use and then kept: ``cached_property``.

    :param dishes: Dish names
    """

    def __init__(self, dishes: list[str]) -> None:
        self.dishes = dishes
        self.builds = 0

    @cached_property
    def by_initial(self) -> dict[str, list[str]]:
        """
        Group dishes by first letter, once per menu.

        :returns: The index
        """
        self.builds += 1
        index: dict[str, list[str]] = {}
        for dish in sorted(self.dishes):
            index.setdefault(dish[0], []).append(dish)
        return index


@singledispatch
def to_json_value(value: object) -> Any:
    """
    Convert a value to something ``json.dumps`` accepts, with the implementation picked by the value's type.

    This base version runs only for types nobody registered.

    :param value: Any value
    :raises TypeError: For a type nobody registered
    """
    raise TypeError(f"no JSON conversion registered for {type(value).__name__}")


@to_json_value.register
def _(value: str | int | float | bool | None) -> Any:
    return value


@to_json_value.register
def _(value: Decimal) -> Any:
    return str(value)  # text, not float: the cents survive


@to_json_value.register
def _(value: date) -> Any:
    return value.isoformat()  # datetime is a date subclass, so this covers both


@to_json_value.register
def _(value: Enum) -> Any:
    return to_json_value(value.value)


@to_json_value.register
def _(value: list | tuple | set | frozenset) -> Any:  # type: ignore[type-arg]
    items = sorted(value, key=str) if isinstance(value, (set, frozenset)) else value
    return [to_json_value(v) for v in items]


@to_json_value.register
def _(value: dict) -> Any:  # type: ignore[type-arg]
    return {str(k): to_json_value(v) for k, v in value.items()}


@deprecated("read_menu is replaced by load_menu, which strips blank lines")
def read_menu(text: str) -> list[str]:
    """
    Split a menu into lines. Kept for old callers; mypy and the runtime both warn whoever still calls it.

    :param text: The menu
    :returns: Its lines
    """
    return text.splitlines()


def load_menu(text: str) -> list[str]:
    """
    Split a menu into its non blank lines.

    :param text: The menu
    :returns: The dishes
    """
    return [line.strip() for line in text.splitlines() if line.strip()]


def demo() -> None:
    """Retry a flaky supplier, cache lookups, convert awkward types to JSON and warn about an old function."""
    replies: Iterator[Exception | str] = iter([ConnectionError("timeout"), ConnectionError("timeout"), "42 lemons"])
    waits: list[float] = []

    @retry(attempts=4, sleep=waits.append, rng=random.Random(7))  # nosec B311  # seeded, for a repeatable demo
    @counted
    def order_lemons(quantity: int) -> str:
        reply = next(replies)
        if isinstance(reply, Exception):
            raise reply
        return reply

    print(f"supplier answered {order_lemons(42)!r} after {CALLS['demo.<locals>.order_lemons']} calls")
    print(f"backoff waits with jitter: {[round(w, 3) for w in waits]}")
    print(f"wraps kept the name: {order_lemons.__name__}")
    for text in ["€4,50", "€4,50", "£12.00"]:
        parse_price(text)
    print(f"lru_cache: {parse_price.cache_info()}")
    menu = Menu(["tarte tatin", "sole meuniere", "steak frites"])
    menu.by_initial, menu.by_initial
    print(f"cached_property built the index {menu.builds} time for two reads: {menu.by_initial['s']}")
    order = {"dish": "sole", "price": Decimal("31.50"), "at": datetime(2026, 11, 12, 20, 5), "tags": {"fish", "lunch"}}
    print(f"singledispatch to JSON: {to_json_value(order)}")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        read_menu("soup\nsalad")  # type: ignore[deprecated]  # mypy flags it too, which is the point
    print(f"deprecated warns at run time: {caught[0].message}")
