"""
Abstractions: ABCs for the families you own, Protocols for the shapes you accept.

Two tools, two jobs.

An abstract base class says "every member of this family has these methods" and can carry the shared behaviour. Use
it for a family you own, where the base class holds the algorithm and each subclass fills in the steps: the template
method pattern. Python refuses to instantiate a subclass that forgot a step, with an error that names it.

A ``Protocol`` says "anything with these methods will do", and mypy checks it without any inheritance. Use it at the
boundary, for things you accept but do not own: a file, a client from another library, a fake in a test. Code that
depends on a Protocol works with anything that fits, which is the dependency inversion principle in one line.
"""

import csv
import json
import tempfile
from abc import ABC, abstractmethod
from collections.abc import Generator, Iterable, Iterator, Mapping, Sequence
from contextlib import closing
from itertools import batched
from pathlib import Path
from typing import IO, Protocol, runtime_checkable

__all__ = [
    "Closeable",
    "CsvTicketSource",
    "JsonLinesTicketSource",
    "ListSink",
    "Row",
    "Sink",
    "TicketSource",
    "copy_rows",
    "demo",
]

type Row = dict[str, str]


class TicketSource(ABC):
    """
    A family of row sources. :meth:`read` is the template method: the algorithm is fixed here, once.

    Subclasses must supply :meth:`_open` and :meth:`_rows`. They may override :meth:`clean`, a hook with a default.
    """

    def __init__(self) -> None:
        self.rows_read = 0

    def read(self) -> Generator[Row]:
        """
        Open, yield every clean non empty row, and close when the rows run out or the generator is closed.

        :yields: Rows with lower case keys and stripped values
        """
        handle = self._open()
        try:
            for raw in self._rows(handle):
                row = self.clean(raw)
                if row:
                    self.rows_read += 1
                    yield row
        finally:
            handle.close()

    @abstractmethod
    def _open(self) -> IO[str]:
        """Open the underlying file or stream and return a text handle."""
        ...

    @abstractmethod
    def _rows(self, handle: IO[str]) -> Iterable[Mapping[str, object]]:
        """
        Turn the open handle into raw rows.

        :param handle: What :meth:`_open` returned
        """
        ...

    def clean(self, raw: Mapping[str, object]) -> Row:
        """
        Normalise one raw row: lower case keys, stripped text, and empty cells dropped.

        :param raw: The row as parsed
        :returns: The clean row; empty when every cell was blank
        """
        cells = {str(k).strip().lower(): str(v).strip() for k, v in raw.items() if k and v is not None}
        return {k: v for k, v in cells.items() if v}


class CsvTicketSource(TicketSource):
    """
    Rows from a CSV file with a header line.

    :param path: The file
    """

    def __init__(self, path: Path) -> None:
        super().__init__()
        self.path = path

    def _open(self) -> IO[str]:
        return self.path.open(newline="", encoding="utf-8")

    def _rows(self, handle: IO[str]) -> Iterable[Mapping[str, object]]:
        return csv.DictReader(handle)


class JsonLinesTicketSource(TicketSource):
    """
    Rows from a JSON lines file, one object per line.

    :param path: The file
    """

    def __init__(self, path: Path) -> None:
        super().__init__()
        self.path = path

    def _open(self) -> IO[str]:
        return self.path.open(encoding="utf-8")

    def _rows(self, handle: IO[str]) -> Iterator[Mapping[str, object]]:
        for line in handle:
            if line.strip():
                yield json.loads(line)


class Sink(Protocol):
    """Anything that can store a batch of rows. No base class needed: having the method is enough."""

    def write(self, rows: Sequence[Row]) -> int:
        """
        Store one batch of rows and return how many were stored.

        :param rows: One batch
        """
        ...


@runtime_checkable
class Closeable(Protocol):
    """Something with ``close()``. ``@runtime_checkable`` lets ``isinstance`` test for it, by method name only."""

    def close(self) -> None:
        """Release what it holds."""
        ...


def copy_rows(source: TicketSource, sink: Sink, batch_size: int = 500) -> int:
    """
    Copy every row from any source to any sink, in batches. It knows the abstractions and nothing else.

    :param source: Where the rows come from
    :param sink: Where they go
    :param batch_size: Rows per write
    :returns: Rows written
    """
    written = 0
    for batch in batched(source.read(), batch_size):
        written += sink.write(batch)
    return written


class ListSink:
    """A sink for tests and demos. It never mentions :class:`Sink`, yet mypy accepts it wherever a Sink is wanted."""

    def __init__(self) -> None:
        self.rows: list[Row] = []
        self.closed = False

    def write(self, rows: Sequence[Row]) -> int:
        """
        Keep the rows in memory.

        :param rows: One batch
        :returns: How many were kept
        """
        self.rows.extend(rows)
        return len(rows)

    def close(self) -> None:
        """Mark the sink closed."""
        self.closed = True


def demo() -> None:
    """Read the same tickets from CSV and JSON lines into a sink that only fits the Protocol."""
    with tempfile.TemporaryDirectory() as folder:
        csv_path = Path(folder) / "tickets.csv"
        csv_path.write_text("Ticket_ID, Dish ,Quantity\nT-1001, steak frites ,2\n,,\nT-1002,bearnaise,1\n", "utf-8")
        jsonl_path = Path(folder) / "tickets.jsonl"
        jsonl_path.write_text('{"ticket_id": "T-1003", "dish": "creme brulee", "quantity": 3}\n\n', "utf-8")
        with closing(ListSink()) as sink:  # whoever opens a resource closes it; copy_rows only borrows the sink
            for source in (CsvTicketSource(csv_path), JsonLinesTicketSource(jsonl_path)):
                copied = copy_rows(source, sink)
                print(f"{type(source).__name__}: copied {copied}, read {source.rows_read}, blank rows skipped")
            print(f"first row, cleaned: {sink.rows[0]}")
            print(f"the sink has close(), so the runtime checkable Protocol matches: {isinstance(sink, Closeable)}")
        print(f"and closing() closed it at the end of the block: {sink.closed}")
    try:
        TicketSource()  # type: ignore[abstract]
    except TypeError as error:
        print(f"the base class cannot be built: {error}")
