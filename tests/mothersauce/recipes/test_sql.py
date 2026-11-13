import sqlite3
from collections.abc import Iterator
from datetime import UTC, date, datetime
from decimal import Decimal
from string.templatelib import Template

import pytest

from mothersauce.recipes.sql import demo, ensure_table, extract_since, quote_ident, sql, sql_type, upsert


@pytest.fixture
def conn() -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(":memory:", autocommit=True)
    yield connection
    connection.close()


def columns(conn: sqlite3.Connection, table: str) -> list[str]:
    return [row[1] for row in conn.execute(f"PRAGMA table_info({table})")]


def test_values_become_parameters() -> None:
    dish, limit = "x' OR '1'='1", 5
    assert sql(t"SELECT * FROM t WHERE dish = {dish} LIMIT {limit}") == (
        "SELECT * FROM t WHERE dish = ? LIMIT ?",
        ("x' OR '1'='1", 5),
    )


def test_name_specs() -> None:
    table, cols, ids = "tickets", ["a", "b"], [1, 2, 3]
    text, params = sql(t"SELECT {cols:ids} FROM {table:id} WHERE a IN ({ids:params})")
    assert text == 'SELECT "a", "b" FROM "tickets" WHERE a IN (?, ?, ?)'
    assert params == (1, 2, 3)


def test_defs_and_excluded_specs() -> None:
    defs, others = {"id": "TEXT", "n": "INTEGER"}, ["n"]
    assert sql(t"CREATE TABLE x ({defs:defs})")[0] == 'CREATE TABLE x ("id" TEXT, "n" INTEGER)'
    assert sql(t"SET {others:excluded}")[0] == 'SET "n" = excluded."n"'


@pytest.mark.parametrize("name", ["1abc", "a b", "a;b", 'a"b', "", "x" * 64, 3])
def test_unsafe_identifiers_are_refused(name: object) -> None:
    with pytest.raises(ValueError, match="not a safe SQL identifier"):
        quote_ident(name)


@pytest.mark.parametrize(
    "query",
    [
        t"{'TEXT; DROP':type}",
        t"{'a':ids}",
        t"{3:ids}",
        t"{'abc':params}",
        t"{['a']:defs}",
        t"{'a':nonsense}",
    ],
)
def test_bad_specs_are_refused(query: Template) -> None:
    with pytest.raises((ValueError, TypeError)):
        sql(query)


@pytest.mark.parametrize(
    ("value", "kind"),
    [
        (True, "INTEGER"),
        (3, "INTEGER"),
        (1.5, "REAL"),
        (Decimal("1.10"), "NUMERIC"),
        (b"\x00", "BLOB"),
        ("x", "TEXT"),
        (None, "TEXT"),
        (date(2026, 1, 1), "TEXT"),
    ],
)
def test_sql_type(value: object, kind: str) -> None:
    assert sql_type(value) == kind


def test_ensure_table_creates_then_evolves(conn: sqlite3.Connection) -> None:
    assert ensure_table(conn, "t", {"id": "a", "n": 1}, "id") == ["id", "n"]
    assert ensure_table(conn, "t", {"id": "b", "n": 2, "price": Decimal(1)}, "id") == ["price"]
    assert ensure_table(conn, "t", {"id": "c"}, "id") == []
    assert columns(conn, "t") == ["id", "n", "price"]


def test_upsert_is_idempotent_and_updates(conn: sqlite3.Connection) -> None:
    rows = [{"id": "a", "n": 1}, {"id": "b", "n": 2}]
    assert upsert(conn, "t", rows, key="id") == 2
    upsert(conn, "t", rows, key="id")
    upsert(conn, "t", [{"id": "a", "n": 10}], key="id")
    assert sorted(conn.execute("SELECT id, n FROM t")) == [("a", 10), ("b", 2)]


def test_upsert_adapts_decimal_and_dates(conn: sqlite3.Connection) -> None:
    when = datetime(2026, 11, 12, 19, 30, tzinfo=UTC)
    upsert(conn, "t", [{"id": "a", "price": Decimal("31.50"), "at": when}], key="id")
    assert conn.execute("SELECT price, at FROM t").fetchone() == (31.5, "2026-11-12T19:30:00+00:00")


def test_upsert_batches_and_new_fields(conn: sqlite3.Connection) -> None:
    rows = [{"id": str(n), "n": n} for n in range(7)] + [{"id": "7", "n": 7, "tip": 1}]
    assert upsert(conn, "t", rows, key="id", batch_size=3) == 8
    assert columns(conn, "t") == ["id", "n", "tip"]
    assert conn.execute("SELECT tip FROM t WHERE id = '7'").fetchone() == (1,)


def test_failed_batch_rolls_back(conn: sqlite3.Connection) -> None:
    upsert(conn, "t", [{"id": "a", "n": 1}], key="id")
    with pytest.raises(sqlite3.ProgrammingError):
        upsert(conn, "t", [{"id": "b", "n": 2}, {"id": "c", "n": object()}], key="id")
    assert [row[0] for row in conn.execute("SELECT id FROM t")] == ["a"]


def test_unsafe_field_names_fail_before_the_database_is_touched(conn: sqlite3.Connection) -> None:
    with pytest.raises(ValueError, match="'bad name'"):
        upsert(conn, "t", [{"id": "b", "bad name": 3}], key="id")
    assert columns(conn, "t") == []


def test_extract_since_moves_the_watermark(conn: sqlite3.Connection) -> None:
    upsert(conn, "t", [{"id": "a", "at": "01"}, {"id": "b", "at": "03"}, {"id": "c", "at": "02"}], key="id")
    rows, mark = extract_since(conn, "t", "at", "01")
    assert [r["id"] for r in rows] == ["c", "b"] and mark == "03"
    assert extract_since(conn, "t", "at", mark) == ([], "03")


def test_demo_runs(capsys: pytest.CaptureFixture[str]) -> None:
    demo()
    out = capsys.readouterr().out
    assert "loaded lunch twice, rows in table: 2" in out
    assert "next watermark 2026-11-12T19:40" in out
