"""
Generators: any size of input in the memory of one record.

A function with ``yield`` returns a generator. It produces one item when asked, then waits. Chain a few and you have
a pipeline where each record passes through every stage before the next one is read, so a ten gigabyte file needs the
memory of one row. Nothing runs until something consumes the pipeline, and when the consumer stops, the work stops.

The building blocks:

- a streaming reader whose file closes even when the consumer stops early;
- stages that parse, filter and group, each a few lines;
- ``itertools.batched`` for bulk writes, and a ``deque`` with ``maxlen`` for sliding windows;
- ``yield from``, and unpacking in a generator expression (new in Python 3.15) to flatten;
- a generator that receives values through ``send``;
- an iterator class, for when the state deserves a name, such as an API cursor.
"""

import csv
import sys
import tempfile
from collections import deque
from collections.abc import Callable, Generator, Iterable, Iterator
from itertools import batched, groupby, islice
from pathlib import Path

__all__ = [
    "Paginated",
    "demo",
    "flatten",
    "parse_rows",
    "read_lines",
    "running_average",
    "runs",
    "traced",
    "where",
    "window",
]


def read_lines(path: Path) -> Generator[str]:
    """
    Stream the non blank lines of a text file without their line endings.

    The ``with`` block lives inside the generator, so the file closes when the lines run out, when the consumer
    breaks out of its loop, or when the generator is garbage collected, whichever comes first.

    :param path: The file
    :yields: One line at a time
    """
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield line.rstrip("\r\n")


def parse_rows(lines: Iterable[str]) -> Generator[dict[str, str]]:
    """
    Parse CSV lines, the first being the header. ``csv`` accepts any iterable of strings, including a generator.

    :param lines: Lines of CSV text
    :yields: One dict per data line
    """
    yield from csv.DictReader(lines)


def where[T](items: Iterable[T], keep: Callable[[T], bool]) -> Generator[T]:
    """
    Keep the items that pass a test: a filter stage.

    :param items: The input stage
    :param keep: The test
    :yields: The items that passed
    """
    yield from (item for item in items if keep(item))


def runs[T, K](items: Iterable[T], key: Callable[[T], K]) -> Generator[tuple[K, list[T]]]:
    """
    Group consecutive items that share a key, such as a sorted log split by day. Input order is kept.

    :param items: Items, already ordered by the key
    :param key: The grouping key
    :yields: Each key with its run of items
    """
    for value, group in groupby(items, key=key):
        yield value, list(group)


def window[T](items: Iterable[T], size: int) -> Generator[tuple[T, ...]]:
    """
    Slide a window over a stream. A ``deque`` with ``maxlen`` drops the oldest item for free.

    >>> list(window([1, 2, 3, 4], 3))
    [(1, 2, 3), (2, 3, 4)]

    :param items: The stream
    :param size: Items per window, at least one
    :yields: Each full window
    :raises ValueError: When size is below one
    """
    if size < 1:
        raise ValueError("window size must be at least 1")
    recent: deque[T] = deque(maxlen=size)
    for item in items:
        recent.append(item)
        if len(recent) == size:
            yield tuple(recent)


def flatten[T](groups: Iterable[Iterable[T]]) -> Generator[T]:
    """
    Flatten one level of nesting lazily, with Python 3.15's unpacking in a generator expression.

    >>> list(flatten([[1, 2], [], [3]]))
    [1, 2, 3]

    :param groups: Iterables of items
    :yields: Every item of every group, in order
    """
    yield from (*group for group in groups)


def running_average() -> Generator[float, float]:
    """
    Keep an average of everything sent in. Prime it with ``next``, then ``send`` values and read the average back.

    >>> avg = running_average(); next(avg)
    0.0
    >>> avg.send(10.0), avg.send(20.0)
    (10.0, 15.0)

    :yields: The average so far
    """
    total = count = 0.0
    average = 0.0
    while True:
        value = yield average
        total += value
        count += 1
        average = total / count


def traced[T](items: Iterable[T], label: str, log: list[str]) -> Generator[T]:
    """
    Pass items through unchanged, noting each one: a way to watch a lazy pipeline run.

    :param items: The input stage
    :param label: The stage name in the log
    :param log: Where notes go
    :yields: The same items
    """
    for item in items:
        log.append(f"{label} {item}")
        yield item


class Paginated[T]:
    """
    Iterate every item of a paged API, fetching each page only when the previous one is used up.

    :param fetch: Called with a cursor (None for the first page); returns the items and the next cursor
    """

    def __init__(self, fetch: Callable[[str | None], tuple[list[T], str | None]]) -> None:
        self._fetch = fetch
        self._buffer: deque[T] = deque()
        self._cursor: str | None = None
        self._done = False
        self.pages = 0

    def __iter__(self) -> Iterator[T]:
        return self

    def __next__(self) -> T:
        while not self._buffer:
            if self._done:
                raise StopIteration
            items, self._cursor = self._fetch(self._cursor)
            self.pages += 1
            self._buffer.extend(items)
            self._done = self._cursor is None
        return self._buffer.popleft()


def demo() -> None:
    """Show the lazy flow, the memory it saves, batches, windows, send and a paged API."""
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "tickets.csv"
        lines = ["ticket_id,dish,quantity"] + [f"T-{1000 + n},dish {n % 3},{n % 4 + 1}" for n in range(10)]
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        log: list[str] = []
        records = ((row["ticket_id"], int(row["quantity"])) for row in parse_rows(read_lines(path)))
        read = traced(records, "read", log)
        big = traced((ticket for ticket, quantity in where(read, lambda r: r[1] > 2)), "kept", log)
        print("nothing has run yet:", log == [])
        print("first two kept:", list(islice(big, 2)))
        print("each record went through every stage before the next was read:", log[:4])
    numbers_list = [n for n in range(1_000_000)]
    numbers_lazy = (n for n in range(1_000_000))
    print(f"a million ints: list {sys.getsizeof(numbers_list):,} bytes, generator {sys.getsizeof(numbers_lazy)} bytes")
    print("batches of 4 for bulk inserts:", [len(b) for b in batched(range(10), 4)])
    print("3 item windows:", list(window("abcde", 3))[:2])
    produce = ["apple", "avocado", "beet", "basil", "corn"]
    print("runs by first letter:", [(letter, len(words)) for letter, words in runs(produce, lambda word: word[0])])
    average = running_average()
    next(average)
    print("running average of covers:", [average.send(c) for c in (40.0, 60.0, 50.0)])
    pages = {None: ([1, 2], "p2"), "p2": ([3], "p3"), "p3": ([4, 5], None)}
    items = Paginated(lambda cursor: pages[cursor])
    print(f"paged API flattened: {list(items)} in {items.pages} fetches; flatten: {list(flatten([[1], [2, 3]]))}")
