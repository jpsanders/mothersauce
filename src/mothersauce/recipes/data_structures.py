"""
Data structures: the container that makes the code obvious and the operation cheap.

Most slow Python is a list doing a set's job. The standard library has the right structure for almost every problem,
and choosing it removes code and time together:

- ``dict`` and ``set`` answer "is it there?" in constant time, where a list scans every item.
- ``defaultdict`` groups, ``Counter`` counts and ranks, ``deque`` makes queues and sliding windows.
- ``heapq`` keeps the top N of a stream and merges sorted streams without loading them.
- ``bisect`` places a value among sorted boundaries, such as price bands.
- ``OrderedDict`` remembers use order, which is all an LRU cache needs.
- ``ChainMap`` looks keys up through layers, such as overrides over defaults.
- ``frozendict`` (new in Python 3.15), ``frozenset`` and ``MappingProxyType`` hold data nobody may change.
- ``NamedTuple`` and ``TypedDict`` give tuples and JSON shaped dicts names and types.
- ``graphlib.TopologicalSorter`` orders tasks by their dependencies: the heart of any DAG scheduler.
"""

import bisect
import heapq
from collections import ChainMap, Counter, OrderedDict, defaultdict
from collections.abc import Callable, Hashable, Iterable, Iterator, Mapping
from datetime import datetime
from decimal import Decimal
from graphlib import CycleError, TopologicalSorter
from timeit import timeit
from types import MappingProxyType
from typing import NamedTuple, TypedDict

__all__ = [
    "LRUCache",
    "MENU",
    "Reading",
    "TicketJson",
    "demo",
    "group_by",
    "layered",
    "merge_by_time",
    "prep_order",
    "prep_waves",
    "price_band",
    "top",
]

# Immutable reference data: frozendict is hashable and cannot be edited by any code path, at run time or by accident.
MENU: frozendict[str, Decimal] = frozendict(
    {"sole meuniere": Decimal("31.50"), "steak frites": Decimal("24.00"), "tarte tatin": Decimal("9.00")}
)


class Reading(NamedTuple):
    """
    A fridge temperature reading: a tuple, so it is light and unpacks, with names and types on every field.

    :param at: When it was read
    :param fridge: Which fridge
    :param celsius: The temperature
    """

    at: datetime
    fridge: str
    celsius: float


class TicketJson(TypedDict, closed=True):
    """The JSON shape of a ticket. ``closed=True`` (Python 3.15) means no other keys are allowed, and mypy checks it."""

    ticket_id: str
    dishes: list[str]


def group_by[T, K: Hashable](items: Iterable[T], key: Callable[[T], K]) -> dict[K, list[T]]:
    """
    Group items by a key in one pass; ``defaultdict`` creates each list the first time its key appears.

    :param items: The items, in any order
    :param key: The grouping key
    :returns: Lists of items per key, each in input order
    """
    groups: defaultdict[K, list[T]] = defaultdict(list)
    for item in items:
        groups[key(item)].append(item)
    return dict(groups)


def top(dishes: Iterable[str], n: int) -> list[tuple[str, int]]:
    """
    Rank dishes by how often they were ordered.

    >>> top(["sole", "tart", "sole"], 1)
    [('sole', 2)]

    :param dishes: One entry per order
    :param n: How many to return
    :returns: The ``n`` most ordered, with counts; ties keep first seen order
    """
    return Counter(dishes).most_common(n)


def merge_by_time(*streams: Iterable[Reading]) -> Iterator[Reading]:
    """
    Merge streams that are each sorted by time into one sorted stream, holding one item per stream in memory.

    :param streams: Sorted streams, such as one per fridge
    :returns: A lazy iterator over every reading, oldest first
    """
    return heapq.merge(*streams, key=lambda reading: reading.at)


def price_band(price: Decimal, bounds: tuple[int, ...] = (10, 20, 30)) -> str:
    """
    Place a price in a band with a binary search over the band boundaries.

    :param price: The price
    :param bounds: Ascending upper bounds of every band but the last
    :returns: The band's name
    """
    names = ("snack", "starter", "main", "special")
    return names[bisect.bisect_right(bounds, price)]


class LRUCache[K: Hashable, V]:
    """
    Keep the ``capacity`` most recently used items. ``OrderedDict.move_to_end`` makes every operation O(1).

    :param capacity: How many items to keep, at least one
    :raises ValueError: When capacity is below one
    """

    def __init__(self, capacity: int) -> None:
        if capacity < 1:
            raise ValueError("capacity must be at least 1")
        self.capacity = capacity
        self._items: OrderedDict[K, V] = OrderedDict()

    def get(self, key: K) -> V | None:
        """
        Read an item and mark it as recently used.

        :param key: The key
        :returns: The value, or None
        """
        if key not in self._items:
            return None
        self._items.move_to_end(key)
        return self._items[key]

    def put(self, key: K, value: V) -> None:
        """
        Store an item, evicting the least recently used one when full.

        :param key: The key
        :param value: The value
        """
        self._items[key] = value
        self._items.move_to_end(key)
        if len(self._items) > self.capacity:
            self._items.popitem(last=False)

    def keys(self) -> list[K]:
        """
        List the keys from least to most recently used.

        :returns: The keys
        """
        return list(self._items)


def layered(*layers: Mapping[str, str]) -> ChainMap[str, str]:
    """
    Look settings up through layers where the first match wins, such as the CLI over the environment over defaults.

    Nothing is copied: a change to any layer shows through at once.

    :param layers: Mappings, highest priority first
    :returns: A read through view of all of them
    """
    return ChainMap(*layers)  # type: ignore[arg-type]  # ChainMap wants MutableMapping, but only reads here


def prep_order(tasks: Mapping[str, set[str]]) -> list[str]:
    """
    Order prep tasks so that each comes after everything it needs.

    :param tasks: Each task with the tasks it depends on
    :returns: One valid order
    :raises ValueError: Naming the loop when the dependencies are circular
    """
    try:
        return list(TopologicalSorter(tasks).static_order())
    except CycleError as error:
        raise ValueError(f"circular dependency: {' -> '.join(error.args[1])}") from None


def prep_waves(tasks: Mapping[str, set[str]]) -> list[list[str]]:
    """
    Group tasks into waves that can run in parallel: everything in a wave only needs earlier waves.

    :param tasks: Each task with the tasks it depends on
    :returns: The waves, each sorted by name
    """
    sorter = TopologicalSorter(tasks)
    sorter.prepare()
    waves = []
    while sorter.is_active():
        ready = sorted(sorter.get_ready())
        waves.append(ready)
        sorter.done(*ready)
    return waves


def demo() -> None:
    """Group, rank, merge, band, cache, layer, protect and schedule, each with the structure built for it."""
    orders = ["sole", "steak", "sole", "tart", "steak", "sole"]
    print(f"group by first letter: {group_by(orders, lambda dish: dish[0])}")
    print(f"top two dishes: {top(orders, 2)}")
    walk_in = [Reading(datetime(2026, 11, 12, h), "walk in", 3.1 + h / 10) for h in (8, 10, 12)]
    pastry = [Reading(datetime(2026, 11, 12, h), "pastry", 4.0) for h in (9, 11)]
    print("merged readings:", [f"{r.at:%H}h {r.fridge}" for r in merge_by_time(walk_in, pastry)])
    print("price bands:", {dish: price_band(price) for dish, price in MENU.items()})
    cache = LRUCache[str, int](2)
    for key in ("a", "b", "a", "c"):
        cache.put(key, ord(key))
    print(f"LRU kept {cache.keys()} after a, b, a, c with room for two")
    settings = layered({"timeout": "5"}, {"timeout": "30", "retries": "3"})
    print(f"layered lookup: timeout {settings['timeout']}, retries {settings['retries']}")
    rates = MappingProxyType({"vat": "0.23"})
    try:
        rates["vat"] = "0"  # type: ignore[index]
    except TypeError:
        print("MappingProxyType: a read only window onto a dict its owner can still change")
    try:
        MENU["sole meuniere"] = Decimal(0)  # type: ignore[index]
    except TypeError:
        print("frozendict: the menu cannot be edited")
    mise_en_place: dict[str, set[str]] = {
        "stock": set(),
        "roux": set(),
        "garnish": set(),
        "veloute": {"stock", "roux"},
        "plate": {"veloute", "garnish"},
    }
    print(f"prep order: {prep_order(mise_en_place)}")
    print(f"prep in parallel waves: {prep_waves(mise_en_place)}")
    haystack_list = list(range(100_000))
    haystack_set = set(haystack_list)
    slow = timeit(lambda: 99_999 in haystack_list, number=200)
    fast = timeit(lambda: 99_999 in haystack_set, number=200)
    print(f"membership in 100,000 items: the set is about {slow / fast:,.0f} times faster than the list")
