import os
import sqlite3
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path

import pytest

from mothersauce.recipes.context_managers import (
    Transaction,
    atomic_write,
    demo,
    env_vars,
    opened,
    remove_if_present,
    timed,
)


@pytest.fixture
def conn() -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(":memory:", autocommit=True)
    connection.execute("CREATE TABLE t (id INTEGER PRIMARY KEY)")
    yield connection
    connection.close()


def ids(conn: sqlite3.Connection) -> list[int]:
    return [row[0] for row in conn.execute("SELECT id FROM t ORDER BY id")]


def test_timed_fills_in_after_the_block() -> None:
    with timed("work") as timer:
        assert timer.seconds == 0.0
    assert timer.seconds > 0 and timer.label == "work"


def test_timed_records_even_when_the_block_fails() -> None:
    with pytest.raises(ZeroDivisionError), timed("boom") as timer:
        1 / 0
    assert timer.seconds > 0


def test_atomic_write_replaces_the_file(tmp_path: Path) -> None:
    target = tmp_path / "out.csv"
    target.write_text("old", encoding="utf-8")
    with atomic_write(target) as handle:
        handle.write("new")
        assert target.read_text(encoding="utf-8") == "old"  # readers still see the old file mid write
    assert target.read_text(encoding="utf-8") == "new"
    assert [p.name for p in tmp_path.iterdir()] == ["out.csv"]


def test_atomic_write_leaves_the_target_untouched_on_failure(tmp_path: Path) -> None:
    target = tmp_path / "out.csv"
    target.write_text("old", encoding="utf-8")
    with pytest.raises(RuntimeError), atomic_write(target) as handle:
        handle.write("partial")
        raise RuntimeError("crash")
    assert target.read_text(encoding="utf-8") == "old"
    assert [p.name for p in tmp_path.iterdir()] == ["out.csv"]


def test_transaction_commits(conn: sqlite3.Connection) -> None:
    with Transaction(conn) as cur:
        cur.execute("INSERT INTO t VALUES (1)")
    assert ids(conn) == [1] and not conn.in_transaction


def test_transaction_rolls_back_and_reraises(conn: sqlite3.Connection) -> None:
    with pytest.raises(ValueError), Transaction(conn) as cur:
        cur.execute("INSERT INTO t VALUES (1)")
        raise ValueError("bad batch")
    assert ids(conn) == []


def test_nested_transaction_is_a_savepoint(conn: sqlite3.Connection) -> None:
    with Transaction(conn) as cur:
        cur.execute("INSERT INTO t VALUES (1)")
        with pytest.raises(sqlite3.IntegrityError), Transaction(conn) as inner:
            inner.execute("INSERT INTO t VALUES (2)")
            inner.execute("INSERT INTO t VALUES (1)")
        with Transaction(conn) as inner:
            inner.execute("INSERT INTO t VALUES (3)")
    assert ids(conn) == [1, 3]


def test_outer_failure_undoes_released_savepoints(conn: sqlite3.Connection) -> None:
    with pytest.raises(RuntimeError), Transaction(conn):
        with Transaction(conn) as inner:
            inner.execute("INSERT INTO t VALUES (1)")
        raise RuntimeError("abort the whole batch")
    assert ids(conn) == []


def test_transaction_needs_autocommit_mode() -> None:
    with closing(sqlite3.connect(":memory:")) as legacy, pytest.raises(ValueError, match="autocommit=True"):
        Transaction(legacy)


def test_opened_closes_the_ones_already_open(tmp_path: Path) -> None:
    good = tmp_path / "a.txt"
    good.write_text("a", encoding="utf-8")
    with opened([good, good]) as handles:
        assert [h.read() for h in handles] == ["a", "a"]
    assert all(h.closed for h in handles)
    leaked: list[object] = []
    with pytest.raises(FileNotFoundError), opened([good, tmp_path / "missing"]) as handles:
        leaked.extend(handles)
    assert leaked == []


def test_env_vars_restore_old_values(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MS_KEEP", "before")
    monkeypatch.delenv("MS_NEW", raising=False)
    with env_vars(MS_KEEP="during", MS_NEW="set"):
        assert os.environ["MS_KEEP"] == "during" and os.environ["MS_NEW"] == "set"
    assert os.environ["MS_KEEP"] == "before" and "MS_NEW" not in os.environ


def test_env_vars_can_unset_for_a_block(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MS_GONE", "x")
    with env_vars(MS_GONE=None):
        assert "MS_GONE" not in os.environ
    assert os.environ["MS_GONE"] == "x"


def test_remove_if_present(tmp_path: Path) -> None:
    path = tmp_path / "f"
    path.touch()
    assert remove_if_present(path) is True
    assert remove_if_present(path) is False


def test_demo_runs(capsys: pytest.CaptureFixture[str]) -> None:
    demo()
    out = capsys.readouterr().out
    assert "still reads 'soup of the day'" in out
    assert "committed: ['T-1']" in out
