"""
Object oriented design: small objects with clear jobs, composed rather than inherited.

Inheritance says "is a" and ties the child to every detail of the parent. Composition says "has a" and keeps each
part replaceable. Prefer composition, and keep inheritance for true families, as in the abstractions recipe.

Much of what makes a class pleasant is protocol, the dunder methods Python calls for you:

- ``__repr__`` for debugging; ``__eq__`` and ``__hash__`` together or not at all.
- ``__len__``, ``__iter__``, ``__contains__`` and ``__getitem__`` to behave like a collection.
- ``__add__`` when addition means something, and ``__bool__`` when emptiness does.
- ``functools.total_ordering`` writes the other comparisons from ``__eq__`` and ``__lt__``.

Validation that belongs to one attribute lives in a ``property``; when many attributes share a rule, a descriptor
with ``__set_name__`` holds it once. ``__slots__`` fixes the attribute set, which saves memory on objects made by the
million. A ``classmethod`` builds instances; a ``staticmethod`` is a plain function kept in the class for clarity.
"""

import tracemalloc
from collections import deque
from collections.abc import Iterator
from datetime import time
from functools import total_ordering
from typing import Self, overload

__all__ = ["Bounded", "Fridge", "Kitchen", "Order", "Shift", "demo"]


class Bounded:
    """
    A descriptor for a number that must stay within limits. One rule, declared once, reused by every attribute.

    :param low: The smallest allowed value
    :param high: The largest allowed value
    """

    def __init__(self, low: float, high: float) -> None:
        self.low = low
        self.high = high
        self.name = self.private = ""

    def __set_name__(self, owner: type, name: str) -> None:
        self.name = name
        self.private = f"_{name}"

    @overload
    def __get__(self, instance: None, owner: type) -> Self: ...

    @overload
    def __get__(self, instance: object, owner: type) -> float: ...

    def __get__(self, instance: object | None, owner: type) -> Self | float:
        if instance is None:
            return self  # accessed on the class: return the descriptor itself, as properties do
        value: float = getattr(instance, self.private)
        return value

    def __set__(self, instance: object, value: float) -> None:
        if not self.low <= value <= self.high:
            raise ValueError(f"{self.name} must be {self.low} to {self.high}, got {value}")
        setattr(instance, self.private, value)


class Fridge:
    """
    A fridge whose readings can never be absurd. ``__slots__`` names the storage the descriptors write to.

    :param name: Which fridge
    :param celsius: Its temperature
    :param litres: Its capacity
    """

    __slots__ = ("_celsius", "_litres", "name")
    celsius = Bounded(-30, 15)
    litres = Bounded(1, 5000)

    def __init__(self, name: str, celsius: float, litres: float) -> None:
        self.name = name
        self.celsius = celsius
        self.litres = litres

    @property
    def is_safe(self) -> bool:
        """
        A computed attribute: food safe at 5 °C or below.

        :returns: True when cold enough
        """
        return self.celsius <= 5

    def __repr__(self) -> str:
        return f"Fridge({self.name!r}, celsius={self.celsius}, litres={self.litres})"


@total_ordering
class Shift:
    """
    A kitchen shift. Orders by start time; ``total_ordering`` derives ``<=``, ``>`` and ``>=``.

    :param start: When it starts
    :param end: When it ends
    :raises ValueError: When the shift ends before it starts
    """

    def __init__(self, start: time, end: time) -> None:
        if end <= start:
            raise ValueError("a shift must end after it starts")
        self.start = start
        self.end = end

    @classmethod
    def from_text(cls, text: str) -> Self:
        """
        Build a shift from ``"18:00-23:30"``: an alternative constructor.

        :param text: Start and end, joined by a hyphen
        :returns: The shift
        """
        start, end = (time.fromisoformat(part.strip()) for part in text.split("-"))
        return cls(start, end)

    @staticmethod
    def minutes_between(start: time, end: time) -> int:
        """
        Count the minutes between two times of the same day. Needs no instance, so it is a ``staticmethod``.

        :param start: The first time
        :param end: The second time
        :returns: Minutes from start to end
        """
        return (end.hour * 60 + end.minute) - (start.hour * 60 + start.minute)

    @property
    def minutes(self) -> int:
        """
        The length of the shift.

        :returns: Minutes
        """
        return self.minutes_between(self.start, self.end)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Shift):
            return NotImplemented
        return (self.start, self.end) == (other.start, other.end)

    def __lt__(self, other: Shift) -> bool:
        return (self.start, self.end) < (other.start, other.end)

    def __hash__(self) -> int:
        return hash((self.start, self.end))

    def __repr__(self) -> str:
        return f"Shift.from_text('{self.start:%H:%M}-{self.end:%H:%M}')"


class Order:
    """
    An open order that behaves like a collection of dishes: ``len``, ``in``, iteration, indexing, ``+`` and truth.

    Mutable on purpose, so it defines ``__eq__`` and sets ``__hash__`` to None: an object that can change must not
    sit in a set, where a change would lose it.

    :param dishes: The dishes so far
    """

    __hash__ = None  # type: ignore[assignment]

    def __init__(self, *dishes: str) -> None:
        self._dishes = list(dishes)

    def add(self, dish: str) -> None:
        """
        Add a dish.

        :param dish: The dish
        """
        self._dishes.append(dish)

    def __len__(self) -> int:
        return len(self._dishes)

    def __iter__(self) -> Iterator[str]:
        return iter(self._dishes)

    def __contains__(self, dish: object) -> bool:
        return dish in self._dishes

    def __getitem__(self, index: int) -> str:
        return self._dishes[index]

    def __add__(self, other: Order) -> Order:
        return Order(*self._dishes, *other._dishes)

    def __bool__(self) -> bool:
        return bool(self._dishes)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Order) and self._dishes == other._dishes

    def __repr__(self) -> str:
        return f"Order({', '.join(map(repr, self._dishes))})"


class Kitchen:
    """
    Composition: a kitchen has fridges and a queue of orders. It is neither of them, so it inherits from neither.

    :param fridges: The fridges it owns
    """

    def __init__(self, fridges: list[Fridge]) -> None:
        self.fridges = {fridge.name: fridge for fridge in fridges}
        self.queue: deque[Order] = deque()

    def accept(self, order: Order) -> bool:
        """
        Queue an order, unless it is empty or a fridge is out of range, which is the chef's rule, not the queue's.

        :param order: The order
        :returns: True when it was queued
        """
        if not order or not all(fridge.is_safe for fridge in self.fridges.values()):
            return False
        self.queue.append(order)
        return True

    def next_order(self) -> Order | None:
        """
        Take the oldest order: first in, first out.

        :returns: The order, or None when the queue is empty
        """
        return self.queue.popleft() if self.queue else None


class _Plain:
    def __init__(self, a: float, b: float, c: float) -> None:
        self.a, self.b, self.c = a, b, c


class _Slotted:
    __slots__ = ("a", "b", "c")

    def __init__(self, a: float, b: float, c: float) -> None:
        self.a, self.b, self.c = a, b, c


def _bytes_for(cls: type[_Plain] | type[_Slotted], count: int = 10_000) -> int:
    tracemalloc.start()
    keep = [cls(1.0, 2.0, 3.0) for _ in range(count)]
    size, _peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    del keep
    return size


def demo() -> None:
    """Validate with a descriptor, order shifts, treat an order as a collection and compose a kitchen."""
    walk_in = Fridge("walk in", 3.5, 2000)
    try:
        walk_in.celsius = 40
    except ValueError as error:
        print(f"descriptor caught it: {error}")
    print(f"{walk_in!r} is safe: {walk_in.is_safe}")
    shifts = sorted([Shift.from_text("18:00-23:30"), Shift.from_text("07:00-15:00"), Shift.from_text("11:00-15:00")])
    print(f"shifts in order: {shifts}; longest {max(s.minutes for s in shifts)} minutes")
    order = Order("sole", "tart") + Order("soup")
    print(f"{order!r}: {len(order)} dishes, has tart: {'tart' in order}, first: {order[0]}, empty: {not order}")
    kitchen = Kitchen([walk_in, Fridge("pastry", 4, 300)])
    print(f"kitchen accepted the order: {kitchen.accept(order)}; next up: {kitchen.next_order()}")
    plain, slotted = _bytes_for(_Plain), _bytes_for(_Slotted)
    print(f"10,000 objects: {plain:,} bytes plain, {slotted:,} with __slots__ ({100 - slotted * 100 // plain}% less)")
