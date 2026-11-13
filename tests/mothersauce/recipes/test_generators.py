import gc
import sys
from collections.abc import Iterator
from itertools import islice
from pathlib import Path

import pytest

from mothersauce.recipes.generators import (
    Paginated,
    demo,
    flatten,
    parse_rows,
    read_lines,
    running_average,
    runs,
    traced,
    where,
    window,
)


@pytest.fixture
def ticket_file(tmp_path: Path) -> Path:
    path = tmp_path / "tickets.csv"
    path.write_text("ticket_id,quantity\r\nT-1,1\r\n\r\nT-2,3\r\nT-3,5\r\n", encoding="utf-8")
    return path


def test_read_lines_skips_blanks_and_endings(ticket_file: Path) -> None:
    assert list(read_lines(ticket_file)) == ["ticket_id,quantity", "T-1,1", "T-2,3", "T-3,5"]


def test_nothing_runs_until_consumed(tmp_path: Path) -> None:
    lines = read_lines(tmp_path / "missing.csv")  # no error yet: the body has not started
    with pytest.raises(FileNotFoundError):
        next(lines)


def test_file_closes_when_the_consumer_stops_early(ticket_file: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    handles = []
    real_open = Path.open

    def spy(self: Path, *args: object, **kwargs: object) -> object:
        handle = real_open(self, *args, **kwargs)  # type: ignore[call-overload]
        handles.append(handle)
        return handle

    monkeypatch.setattr(Path, "open", spy)
    lines = read_lines(ticket_file)
    assert next(lines) == "ticket_id,quantity"
    assert not handles[0].closed
    lines.close()
    assert handles[0].closed


def test_pipeline_of_stages(ticket_file: Path) -> None:
    rows = parse_rows(read_lines(ticket_file))
    big = where(rows, lambda row: int(row["quantity"]) > 2)
    assert [row["ticket_id"] for row in big] == ["T-2", "T-3"]


def test_stages_interleave_one_record_at_a_time() -> None:
    log: list[str] = []
    stage = traced(traced(iter([1, 2]), "a", log), "b", log)
    assert next(stage) == 1
    assert log == ["a 1", "b 1"]


def test_runs_groups_consecutive_keys() -> None:
    assert list(runs([1, 1, 2, 1], key=lambda n: n)) == [(1, [1, 1]), (2, [2]), (1, [1])]


def test_window() -> None:
    assert list(window(range(5), 2)) == [(0, 1), (1, 2), (2, 3), (3, 4)]
    assert list(window(range(2), 3)) == []
    with pytest.raises(ValueError, match="at least 1"):
        list(window([], 0))


def test_flatten_is_lazy() -> None:
    def groups() -> Iterator[list[int]]:
        yield [1, 2]
        raise AssertionError("read too far")

    assert list(islice(flatten(groups()), 2)) == [1, 2]


def test_running_average_receives_values() -> None:
    average = running_average()
    assert next(average) == 0.0
    assert [average.send(v) for v in (2.0, 4.0, 9.0)] == [2.0, 3.0, 5.0]


def test_paginated_fetches_lazily() -> None:
    calls: list[str | None] = []
    pages: dict[str | None, tuple[list[int], str | None]] = {None: ([1], "b"), "b": ([], "c"), "c": ([2], None)}

    def fetch(cursor: str | None) -> tuple[list[int], str | None]:
        calls.append(cursor)
        return pages[cursor]

    items = Paginated(fetch)
    assert next(items) == 1 and calls == [None]
    assert list(items) == [2] and calls == [None, "b", "c"]
    assert items.pages == 3
    with pytest.raises(StopIteration):
        next(items)


def test_generator_memory_does_not_grow() -> None:
    gc.collect()
    assert sys.getsizeof(n for n in range(10**7)) < 1_000


def test_demo_runs(capsys: pytest.CaptureFixture[str]) -> None:
    demo()
    out = capsys.readouterr().out
    assert "nothing has run yet: True" in out
    assert "paged API flattened: [1, 2, 3, 4, 5] in 3 fetches" in out
