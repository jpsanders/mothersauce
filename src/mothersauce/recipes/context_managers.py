"""
Context managers: every acquire paired with its release, on success and on failure.

``with`` guarantees that the cleanup runs whatever happens in the block. The file closes, the transaction commits or
rolls back, the temporary file disappears. Writing your own manager gives a resource that guarantee everywhere it is
used, instead of a ``try``/``finally`` copied into every caller and forgotten in one.

There are two ways to write one. ``@contextmanager`` on a generator suits most cases: code before ``yield`` is the
setup and code after it is the teardown, with the ``yield`` inside ``try``/``finally`` when the teardown must run on
errors too. A class with ``__enter__`` and ``__exit__`` suits a manager that holds state, is reused, or must look at
the exception. ``__exit__`` returning True swallows the exception, so return False unless swallowing is the point.

``ExitStack`` manages resources whose number is known only at run time, and ``contextlib`` ships ``suppress``,
``chdir`` and ``nullcontext`` for the everyday cases.
"""

import os
import sqlite3
import stat
import tempfile
import time
from collections.abc import Generator, Sequence
from contextlib import ExitStack, chdir, contextmanager, suppress
from dataclasses import dataclass
from itertools import count
from pathlib import Path
from types import TracebackType
from typing import Literal, TextIO

__all__ = ["Timer", "Transaction", "atomic_write", "demo", "env_vars", "opened", "remove_if_present", "timed"]

_savepoints = count(1)


@dataclass(slots=True)
class Timer:
    """
    What :func:`timed` measured. ``seconds`` is filled in when the block ends.

    :param label: What was timed
    :param seconds: The elapsed wall clock time
    """

    label: str
    seconds: float = 0.0


@contextmanager
def timed(label: str) -> Generator[Timer]:
    """
    Time a block. The timer is yielded first and filled in afterwards, so the caller can read it after the block.

    :param label: What is being timed
    :yields: The timer
    """
    timer = Timer(label)
    start = time.perf_counter()
    try:
        yield timer
    finally:
        timer.seconds = time.perf_counter() - start


@contextmanager
def atomic_write(path: Path, encoding: str = "utf-8") -> Generator[TextIO]:
    """
    Write a file so readers see the old version or the new one, never half of either.

    The text goes to a temporary file in the same folder, is flushed to disk, and then replaces the target in one
    ``os.replace``, which POSIX guarantees is atomic. On an error the temporary file is removed and the target is
    untouched. The new file keeps the old one's permissions, because a temporary file starts as private (0600).

    :param path: The file to write
    :param encoding: Text encoding
    :yields: A handle to write to
    """
    fd, temp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    temp = Path(temp_name)
    replaced = False
    try:
        with os.fdopen(fd, "w", encoding=encoding, newline="") as handle:
            yield handle
            handle.flush()
            os.fsync(handle.fileno())
        if path.exists():
            os.chmod(temp, stat.S_IMODE(path.stat().st_mode))
        else:
            umask = os.umask(0)
            os.umask(umask)
            os.chmod(temp, 0o666 & ~umask)
        os.replace(temp, path)
        replaced = True
    finally:
        if not replaced:
            temp.unlink(missing_ok=True)


class Transaction:
    """
    Commit on success, roll back on any exception, and nest with savepoints.

    The connection must be opened with ``autocommit=True``, so that this class, and not the sqlite3 module, decides
    where transactions begin and end. A nested ``Transaction`` becomes a savepoint: its failure undoes only its own
    work, and the outer transaction carries on.

    :param conn: An open connection in autocommit mode
    :raises ValueError: When the connection is not in autocommit mode
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        if conn.autocommit is not True:
            raise ValueError("open the connection with sqlite3.connect(..., autocommit=True)")
        self.conn = conn
        self._savepoint: str | None = None

    def __enter__(self) -> sqlite3.Cursor:
        if self.conn.in_transaction:
            self._savepoint = f"sp_{next(_savepoints)}"
            self.conn.execute(f"SAVEPOINT {self._savepoint}")
        else:
            self.conn.execute("BEGIN")
        return self.conn.cursor()

    def __exit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None
    ) -> Literal[False]:
        if self._savepoint is None:
            self.conn.execute("COMMIT" if exc_type is None else "ROLLBACK")
        else:
            if exc_type is not None:
                self.conn.execute(f"ROLLBACK TO {self._savepoint}")
            self.conn.execute(f"RELEASE {self._savepoint}")
            self._savepoint = None
        return False  # never swallow: the caller must know the work was undone, and Literal[False] tells mypy so


@contextmanager
def opened(paths: Sequence[Path]) -> Generator[list[TextIO]]:
    """
    Open any number of files at once. If the fifth fails to open, the first four are closed before the error spreads.

    :param paths: The files
    :yields: Their handles, in order
    """
    with ExitStack() as stack:
        yield [stack.enter_context(p.open(encoding="utf-8")) for p in paths]


@contextmanager
def env_vars(**values: str | None) -> Generator[None]:
    """
    Set environment variables for the length of a block and restore the old values afterwards.

    :param values: Names and values; None removes the variable for the block
    :yields: Nothing; the variables are set inside the block
    """
    saved = {name: os.environ.get(name) for name in values}
    try:
        for name, value in values.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        yield
    finally:
        for name, old in saved.items():
            if old is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = old


def remove_if_present(path: Path) -> bool:
    """
    Delete a file if it is there. ``suppress`` names the one error that is expected and lets every other one through.

    :param path: The file
    :returns: True when a file was deleted
    """
    with suppress(FileNotFoundError):
        path.unlink()
        return True
    return False


def demo() -> None:
    """Time a block, survive a crash mid write, roll back a failed batch, and restore the environment."""
    with timed("sum of squares") as timer:
        sum(n * n for n in range(200_000))
    print(f"timed {timer.label!r}: {timer.seconds * 1000:.1f} ms")
    with tempfile.TemporaryDirectory() as folder, chdir(folder):
        menu = Path("menu.txt")
        menu.write_text("soup of the day\n", encoding="utf-8")
        try:
            with atomic_write(menu) as handle:
                handle.write("half a new menu")
                raise RuntimeError("power cut")
        except RuntimeError:
            pass
        print(f"after a crash mid write the file still reads {menu.read_text(encoding='utf-8').strip()!r}")
        print(f"and no temporary file is left behind: {sorted(p.name for p in Path().iterdir())}")
        try:
            with opened([menu, Path("missing.txt")]):
                pass
        except FileNotFoundError:
            print("ExitStack closed menu.txt when missing.txt failed to open")
    conn = sqlite3.connect(":memory:", autocommit=True)
    conn.execute("CREATE TABLE tickets (id TEXT PRIMARY KEY, dish TEXT)")
    with Transaction(conn) as cur:
        cur.execute("INSERT INTO tickets VALUES ('T-1', 'sole')")
        try:
            with Transaction(conn) as inner:
                inner.execute("INSERT INTO tickets VALUES ('T-2', 'tart')")
                inner.execute("INSERT INTO tickets VALUES ('T-1', 'duplicate')")
        except sqlite3.IntegrityError:
            print("the nested batch failed and its savepoint rolled back; the outer transaction carries on")
    print(f"committed: {[row[0] for row in conn.execute('SELECT id FROM tickets')]}")
    conn.close()
    with env_vars(KITCHEN_MODE="service"):
        print(f"inside the block KITCHEN_MODE={os.environ['KITCHEN_MODE']}")
    print(f"afterwards it is gone again: {'KITCHEN_MODE' not in os.environ}")
