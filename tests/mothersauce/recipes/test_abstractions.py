from collections.abc import Iterable, Mapping, Sequence
from io import StringIO
from pathlib import Path
from typing import IO

import pytest

from mothersauce.recipes.abstractions import (
    Closeable,
    CsvTicketSource,
    JsonLinesTicketSource,
    ListSink,
    Row,
    TicketSource,
    copy_rows,
    demo,
)


class TrackingSource(TicketSource):
    """A test double built on the real template method, to watch it close the handle."""

    def __init__(self, rows: list[Mapping[str, object]]) -> None:
        super().__init__()
        self.raw = rows
        self.handle = StringIO()

    def _open(self) -> IO[str]:
        return self.handle

    def _rows(self, handle: IO[str]) -> Iterable[Mapping[str, object]]:
        return self.raw


class CountingSink:
    """Fits the Sink Protocol, has no close(), and inherits nothing."""

    def __init__(self) -> None:
        self.batches: list[int] = []

    def write(self, rows: Sequence[Row]) -> int:
        self.batches.append(len(rows))
        return len(rows)


def test_csv_source_cleans_rows(tmp_path: Path) -> None:
    path = tmp_path / "t.csv"
    path.write_text("ID ,Dish\n T-1 , Frites \n,\n", encoding="utf-8")
    source = CsvTicketSource(path)
    assert list(source.read()) == [{"id": "T-1", "dish": "Frites"}]
    assert source.rows_read == 1


def test_json_lines_source_skips_blank_lines(tmp_path: Path) -> None:
    path = tmp_path / "t.jsonl"
    path.write_text('{"a": 1}\n\n{"a": 2, "b": null}\n', encoding="utf-8")
    assert list(JsonLinesTicketSource(path).read()) == [{"a": "1"}, {"a": "2"}]


def test_template_method_closes_even_when_the_caller_stops_early() -> None:
    source = TrackingSource([{"a": "1"}, {"a": "2"}])
    rows = source.read()
    assert next(rows) == {"a": "1"}
    rows.close()  # what a for loop does on break, and what garbage collection does eventually
    assert source.handle.closed


def test_abstract_base_cannot_be_instantiated() -> None:
    with pytest.raises(TypeError, match="abstract"):
        TicketSource()  # type: ignore[abstract]


def test_incomplete_subclass_fails_where_it_is_built() -> None:
    class Half(TicketSource):
        def _open(self) -> IO[str]:
            return StringIO()

    with pytest.raises(TypeError, match="_rows"):
        Half()  # type: ignore[abstract]


def test_copy_rows_batches_into_any_sink() -> None:
    sink = CountingSink()
    rows: list[Mapping[str, object]] = [{"n": str(i)} for i in range(5)]
    assert copy_rows(TrackingSource(rows), sink, batch_size=2) == 5
    assert sink.batches == [2, 2, 1]


def test_copy_rows_leaves_closing_to_the_owner() -> None:
    sink = ListSink()
    copy_rows(TrackingSource([{"a": "1"}]), sink)
    assert not sink.closed and sink.rows == [{"a": "1"}]


def test_cells_of_spaces_count_as_empty() -> None:
    source = TrackingSource([{"a": "  ", "b": " x "}, {"a": " ", "b": ""}])
    assert list(source.read()) == [{"b": "x"}]
    assert source.rows_read == 1


def test_runtime_checkable_protocol_checks_method_names() -> None:
    assert isinstance(ListSink(), Closeable)
    assert isinstance(StringIO(), Closeable)
    assert not isinstance(CountingSink(), Closeable)


def test_demo_runs(capsys: pytest.CaptureFixture[str]) -> None:
    demo()
    out = capsys.readouterr().out
    assert "CsvTicketSource: copied 2, read 2" in out
    assert "cannot be built" in out
