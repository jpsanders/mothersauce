"""
Generics: write the container once and keep every type.

A function that returns "whatever was put in" should say so, or every caller ends up casting. Generics let one class
or function serve many types while mypy still knows which type each call uses.

Python has its own syntax for them, with no ``TypeVar`` boilerplate:

- ``class Repository[K: Hashable, V]`` declares type parameters, with a bound, where the class is declared.
- ``def first[T](items: Iterable[T]) -> T | None`` carries the element type through a function.
- ``[S: (str, bytes)]`` constrains a parameter to exactly one of a few types, never a mix.
- ``[T, C = str]`` gives a parameter a default, so ``Page[int]`` means ``Page[int, str]``.
- ``[**P, R]`` captures a whole parameter list, so a wrapper keeps the signature of what it wraps.
- ``@overload`` describes a function whose return type depends on its argument types.
- ``TypeIs`` teaches mypy what a check function proves.

A ``Result[T, E]`` closes the recipe: success and failure as values, matched exhaustively, for batch jobs where one
bad record must not stop the other ten thousand.
"""

import heapq
from collections.abc import Callable, Hashable, Iterable, Iterator
from dataclasses import dataclass, field
from typing import Protocol, Self, TypeIs, overload

__all__ = [
    "Err",
    "Ok",
    "Page",
    "Repository",
    "Result",
    "concat",
    "defer",
    "demo",
    "first",
    "is_row",
    "parse_quantity",
    "partition",
    "top",
    "try_parse",
]


class Repository[K: Hashable, V]:
    """
    An in memory store keyed by any hashable type. One class, and ``Repository[str, Ticket]`` keeps both types.

    >>> repo = Repository[str, int]().add("a", 1).add("b", 2)
    >>> repo.get("b"), len(repo)
    (2, 2)
    """

    def __init__(self) -> None:
        self._items: dict[K, V] = {}

    def add(self, key: K, value: V) -> Self:
        """
        Store a value, refusing to overwrite silently. Returns ``Self`` so calls chain, in subclasses too.

        :param key: The key
        :param value: The value
        :returns: This repository
        :raises KeyError: When the key is already stored
        """
        if key in self._items:
            raise KeyError(f"{key!r} is already stored")
        self._items[key] = value
        return self

    def get(self, key: K) -> V | None:
        """
        Look a value up.

        :param key: The key
        :returns: The value, or None when absent
        """
        return self._items.get(key)

    def require(self, key: K) -> V:
        """
        Look a value up when absence is a bug.

        :param key: The key
        :returns: The value
        :raises LookupError: When the key is absent
        """
        try:
            return self._items[key]
        except KeyError:
            raise LookupError(f"no item {key!r}") from None

    def find(self, predicate: Callable[[V], bool]) -> list[V]:
        """
        Return every value that matches.

        :param predicate: A test for one value
        :returns: The matching values, in insertion order
        """
        return [v for v in self._items.values() if predicate(v)]

    def __len__(self) -> int:
        return len(self._items)

    def __iter__(self) -> Iterator[V]:
        return iter(self._items.values())


def first[T](items: Iterable[T]) -> T | None:
    """
    Return the first item of anything iterable, keeping its type.

    :param items: Any iterable
    :returns: The first item, or None when there is none
    """
    return next(iter(items), None)


class SupportsLessThan(Protocol):
    """The one method :func:`top` needs. A Protocol bound accepts ints, strings, dates and your own classes."""

    def __lt__(self, other: Self, /) -> bool:
        """
        Compare with another value of the same type.

        :param other: The value on the right
        """
        ...


def top[T: SupportsLessThan](items: Iterable[T], n: int) -> list[T]:
    """
    Return the ``n`` largest items, largest first, in O(len × log n) instead of sorting everything.

    :param items: Comparable items
    :param n: How many to keep
    :returns: The largest items
    """
    return heapq.nlargest(n, items)


def concat[S: (str, bytes)](left: S, right: S) -> S:
    """
    Join two strings or two byte strings. The constraint lets ``str`` with ``str`` through and refuses a mix.

    :param left: The first part
    :param right: The second part, the same type as the first
    :returns: Both parts joined
    """
    return left + right


@dataclass(frozen=True, slots=True)
class Page[T, C = str]:
    """
    One page of results. ``C`` defaults to ``str``, so ``Page[int]`` is ``Page[int, str]``.

    :param items: The results on this page
    :param cursor: Where the next page starts; None on the last page
    """

    items: tuple[T, ...]
    cursor: C | None = None

    @property
    def is_last(self) -> bool:
        """
        Whether this is the final page.

        :returns: True when there is no cursor
        """
        return self.cursor is None


def defer[**P, R](func: Callable[P, R], *args: P.args, **kwargs: P.kwargs) -> Callable[[], R]:
    """
    Bind arguments now and call later, with the arguments type checked against ``func`` at the binding site.

    :param func: Any callable
    :param args: Its positional arguments
    :param kwargs: Its keyword arguments
    :returns: A callable taking nothing that returns what ``func`` returns
    """
    return lambda: func(*args, **kwargs)


def is_row(value: object) -> TypeIs[dict[str, str]]:
    """
    Check that a value is a row of strings; in the branch where the check passed, mypy sees ``dict[str, str]``.

    :param value: Anything, such as a decoded JSON value
    :returns: True when it is a dict with only string keys and values
    """
    return isinstance(value, dict) and all(isinstance(k, str) and isinstance(v, str) for k, v in value.items())


@overload
def parse_quantity(text: str) -> int: ...


@overload
def parse_quantity(text: None) -> None: ...


def parse_quantity(text: str | None) -> int | None:
    """
    Parse a quantity. The overloads tell mypy: text in, int out; None in, None out.

    :param text: The quantity as text, or None for a missing cell
    :returns: The quantity, or None when given None
    """
    return None if text is None else int(text.strip())


@dataclass(frozen=True, slots=True)
class Ok[T]:
    """
    A success.

    :param value: The result
    """

    value: T


@dataclass(frozen=True, slots=True)
class Err[E]:
    """
    A failure, as a value.

    :param error: What went wrong
    """

    error: E


type Result[T, E = str] = Ok[T] | Err[E]


def try_parse[T](parse: Callable[[str], T], text: str) -> Result[T]:
    """
    Run a parser and capture a ``ValueError`` as an :class:`Err` instead of raising it.

    :param parse: The parser, such as ``int``
    :param text: Its input
    :returns: ``Ok`` with the value, or ``Err`` with the message
    """
    try:
        return Ok(parse(text))
    except ValueError as error:
        return Err(f"{text!r}: {error}")


def partition[T, E](results: Iterable[Result[T, E]]) -> tuple[list[T], list[E]]:
    """
    Split results into values and errors, keeping both types.

    :param results: Any mix of Ok and Err
    :returns: The values and the errors, each in input order
    """
    values: list[T] = []
    errors: list[E] = []
    for result in results:
        match result:
            case Ok(value):
                values.append(value)
            case Err(error):
                errors.append(error)
    return values, errors


@dataclass(order=True, frozen=True, slots=True)
class _Dish:
    covers: int
    name: str = field(compare=False)


def demo() -> None:
    """Store, rank, page, bind and parse with full types, then split a batch into values and errors."""
    repo = Repository[str, _Dish]()
    repo.add("steak", _Dish(41, "steak frites")).add("sole", _Dish(17, "sole meuniere")).add("tart", _Dish(29, "tarte"))
    print(f"repo holds {len(repo)}; busy dishes: {[d.name for d in repo.find(lambda d: d.covers > 20)]}")
    print(f"top two by covers: {[d.name for d in top(repo, 2)]}; first: {first(repo)}")
    print(f"concat keeps the type: {concat('mise ', 'en place')!r}, {concat(b'ab', b'cd')!r}")
    page = Page[int](items=(1, 2, 3), cursor="eyJvZmZzZXQiOjN9")
    print(f"page of {len(page.items)}, last page: {page.is_last}")
    later = defer(round, 3.14159, ndigits=2)
    print(f"deferred call, typed at the binding: {later()}")
    decoded: object = {"ticket_id": "T-1001", "dish": "sole"}
    if is_row(decoded):
        print(f"TypeIs narrowed it to dict[str, str]: {sorted(decoded)}")
    print(f"overloads: {parse_quantity(' 3 ')} and {parse_quantity(None)}")
    values, errors = partition(try_parse(int, text) for text in ["2", "two", "5", ""])
    print(f"parsed {values}; {len(errors)} errors kept as values: {errors[0]}")
