"""
SQL: injection proof queries, a schema that grows with the data, idempotent loads and incremental extracts.

Formatting a value into SQL text, as ``f"..."`` does, is how injection happens. A template string, ``t"..."`` (Python
3.14), keeps the literal text and the values apart, so :func:`sql` can turn every value into a ``?`` parameter. Table
and column names cannot be parameters, so they take a format spec instead, ``{table:id}``, and are checked against
a strict pattern before they are quoted. Unsafe SQL is then impossible to write by accident, even in your own DDL.

The loading patterns every warehouse load needs:

- Schema evolution: create the table on first sight, and add a column when a record brings a new field.
- Upserts: ``INSERT ... ON CONFLICT DO UPDATE``, so loading the same batch twice changes nothing.
- Batches of ``executemany`` inside one transaction, which is many times faster than one commit per row.
- A high watermark: extract only the rows newer than the last run, ordered so the new watermark is the last row.

This uses ``sqlite3`` from the standard library. The shapes carry over to other drivers, which need their own
parameter style (``%s`` for psycopg) and their own catalogue query in place of ``PRAGMA table_info``.

Money goes in as text. A column declared NUMERIC turns ``'31.50'`` into the float 31.5, so cents drift exactly as
they would in a float; a TEXT column keeps the digits, and ``Decimal`` reads them back unchanged.
"""

import re
import sqlite3
from collections.abc import Iterable, Mapping
from datetime import date, datetime
from decimal import Decimal
from itertools import batched
from string.templatelib import Interpolation, Template
from typing import Any

from mothersauce.recipes.context_managers import Transaction

__all__ = ["SQL_TYPES", "demo", "ensure_table", "extract_since", "quote_ident", "sql", "sql_type", "upsert"]

SQL_TYPES = frozenset({"TEXT", "INTEGER", "REAL", "NUMERIC", "BLOB"})
_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,62}")


def quote_ident(name: object) -> str:
    """
    Quote a table or column name after checking it is a plain identifier.

    >>> quote_ident("tickets")
    '"tickets"'

    :param name: The name
    :returns: The name in double quotes
    :raises ValueError: When it is not letters, digits and underscores, starting with a letter or underscore
    """
    if not isinstance(name, str) or not _IDENTIFIER.fullmatch(name):
        raise ValueError(f"not a safe SQL identifier: {name!r}")
    return f'"{name}"'


def _names(value: object) -> list[str]:
    if isinstance(value, str) or not isinstance(value, Iterable):
        raise TypeError(f"expected a sequence of names, got {value!r}")
    return [quote_ident(item) for item in value]


def _type_keyword(value: object) -> str:
    if value not in SQL_TYPES:
        raise ValueError(f"not an allowed SQL type: {value!r}")
    return str(value)


def _render(part: Interpolation[object], params: list[object]) -> str:
    value, spec = part.value, part.format_spec
    match spec:
        case "":
            params.append(value)
            return "?"
        case "id":
            return quote_ident(value)
        case "ids":
            return ", ".join(_names(value))
        case "params":
            if not isinstance(value, Iterable) or isinstance(value, str):
                raise TypeError(f"{{...:params}} needs a sequence of values, got {value!r}")
            items = list(value)
            params.extend(items)
            return ", ".join("?" * len(items))
        case "type":
            return _type_keyword(value)
        case "defs":
            if not isinstance(value, Mapping):
                raise TypeError(f"{{...:defs}} needs a mapping of names to types, got {value!r}")
            return ", ".join(f"{quote_ident(name)} {_type_keyword(kind)}" for name, kind in value.items())
        case "excluded":
            return ", ".join(f"{name} = excluded.{name}" for name in _names(value))
        case _:
            raise ValueError(f"unknown format spec {spec!r} in {{{part.expression}:{spec}}}")


def sql(query: Template) -> tuple[str, tuple[object, ...]]:
    """
    Turn a template string into SQL text and its parameters. Values become ``?``; names need a spec.

    Specs: none for a value, ``id`` for one name, ``ids`` for a list of names, ``params`` for a list of values,
    ``type`` for a column type, ``defs`` for a mapping of column names to types, and ``excluded`` for an upsert's
    ``SET`` list.

    >>> dish = "sole'; DROP TABLE tickets; --"
    >>> sql(t"SELECT * FROM {'tickets':id} WHERE dish = {dish}")
    ('SELECT * FROM "tickets" WHERE dish = ?', ("sole'; DROP TABLE tickets; --",))

    :param query: A ``t"..."`` string
    :returns: The SQL text and the parameters, in order
    """
    params: list[object] = []
    text = "".join(part if isinstance(part, str) else _render(part, params) for part in query)
    return text, tuple(params)


def sql_type(value: object) -> str:
    """
    Choose a column type for a Python value. ``Decimal`` gets TEXT, so its digits survive the round trip.

    :param value: A sample value
    :returns: One of :data:`SQL_TYPES`
    """
    match value:
        case int():  # bool is an int subclass, so True lands here too, as 1
            return "INTEGER"
        case float():
            return "REAL"
        case Decimal():
            return "TEXT"
        case bytes():
            return "BLOB"
        case _:
            return "TEXT"


def _adapt(value: object) -> object:
    """
    Convert values sqlite3 has no adapter for: Decimal keeps its digits as text, dates become ISO 8601.

    :param value: A value from a record
    :returns: A value sqlite3 stores as is
    """
    match value:
        case Decimal():
            return str(value)
        case datetime() | date():
            return value.isoformat()
        case _:
            return value


def ensure_table(conn: sqlite3.Connection, table: str, record: Mapping[str, object], key: str) -> list[str]:
    """
    Create the table on first sight, or add any columns this record brings that the table lacks.

    :param conn: The connection
    :param table: The table
    :param record: A record with every field the batch uses
    :param key: The primary key column
    :returns: The columns that were added; every column when the table was created
    """
    existing = {row[1] for row in conn.execute(*sql(t"PRAGMA table_info({table:id})"))}
    if not existing:
        definitions = {name: sql_type(value) for name, value in record.items()}
        conn.execute(*sql(t"CREATE TABLE {table:id} ({definitions:defs}, PRIMARY KEY ({key:id}))"))
        return list(record)
    added = [name for name in record if name not in existing]
    for name in added:
        column_type = sql_type(record[name])
        conn.execute(*sql(t"ALTER TABLE {table:id} ADD COLUMN {name:id} {column_type:type}"))
    return added


def upsert(
    conn: sqlite3.Connection, table: str, rows: Iterable[Mapping[str, object]], key: str, batch_size: int = 500
) -> int:
    """
    Insert or update rows by key, in batches, each batch in one transaction. Loading twice changes nothing.

    :param conn: A connection in autocommit mode
    :param table: The table
    :param rows: The rows; later rows may bring new fields
    :param key: The primary key column
    :param batch_size: Rows per transaction
    :returns: Rows written
    """
    written = 0
    for batch in batched(rows, batch_size):
        columns = list(dict.fromkeys(name for row in batch for name in row))
        sample = {name: next((row[name] for row in batch if row.get(name) is not None), "") for name in columns}
        others = [name for name in columns if name != key]
        insert = t"INSERT INTO {table:id} ({columns:ids}) VALUES ({columns:params}) ON CONFLICT ({key:id}) "
        text, _ = sql(insert + (t"DO UPDATE SET {others:excluded}" if others else Template("DO NOTHING")))
        with Transaction(conn) as cur:
            ensure_table(conn, table, sample, key)
            cur.executemany(text, [tuple(_adapt(row.get(name)) for name in columns) for row in batch])
        written += len(batch)
    return written


def extract_since(
    conn: sqlite3.Connection, table: str, column: str, key: str, watermark: tuple[object, object] | None
) -> tuple[list[dict[str, Any]], tuple[object, object] | None]:
    """
    Read only the rows after the watermark, oldest first, and return the new watermark with them.

    Timestamps tie, so the watermark is a pair: the column and the key. Rows compare as ``(column, key)`` tuples, so
    a row that arrives later with the same timestamp as the last one read is still found by the next run.

    :param conn: The connection
    :param table: The table
    :param column: The column that only grows, such as an updated timestamp
    :param key: The unique key that breaks ties
    :param watermark: Where the last run ended; None to read everything
    :returns: The new rows, and the watermark for the next run (unchanged when nothing is new)
    """
    if watermark is None:
        query = sql(t"SELECT * FROM {table:id} ORDER BY {column:id}, {key:id}")
    else:
        last, last_key = watermark
        query = sql(
            t"SELECT * FROM {table:id} WHERE ({column:id}, {key:id}) > ({last}, {last_key}) "
            t"ORDER BY {column:id}, {key:id}"
        )
    cursor = conn.execute(*query)
    names = [d[0] for d in cursor.description]
    rows = [dict(zip(names, values, strict=True)) for values in cursor]
    return rows, ((rows[-1][column], rows[-1][key]) if rows else watermark)


def demo() -> None:
    """Build safe SQL, evolve a table, load twice without duplicates and extract incrementally."""
    hostile = "sole'; DROP TABLE tickets; --"
    print("a hostile value stays a parameter:", sql(t"SELECT * FROM {'tickets':id} WHERE dish = {hostile}"))
    try:
        sql(t"SELECT * FROM {'tickets; DROP TABLE tickets':id}")
    except ValueError as error:
        print(f"a hostile name is refused: {error}")
    conn = sqlite3.connect(":memory:", autocommit=True)
    lunch = [
        {"ticket_id": "T-1001", "dish": "sole", "price": Decimal("31.50"), "updated_at": "2026-11-12T12:05"},
        {"ticket_id": "T-1002", "dish": "tart", "price": Decimal("9.00"), "updated_at": "2026-11-12T12:20"},
    ]
    upsert(conn, "tickets", lunch, key="ticket_id")
    upsert(conn, "tickets", lunch, key="ticket_id")
    print(f"loaded lunch twice, rows in table: {conn.execute('SELECT count(*) FROM tickets').fetchone()[0]}")
    _, watermark = extract_since(conn, "tickets", "updated_at", "ticket_id", None)
    dinner = [{"ticket_id": "T-1002", "dish": "tart", "tip": 2, "updated_at": "2026-11-12T19:40"}]
    upsert(conn, "tickets", dinner, key="ticket_id")
    columns = [row[1] for row in conn.execute("PRAGMA table_info(tickets)")]
    print(f"a new field added a column: {columns}")
    rows, watermark = extract_since(conn, "tickets", "updated_at", "ticket_id", watermark)
    print(f"incremental extract since lunch: {[(r['ticket_id'], r['tip']) for r in rows]}, next watermark {watermark}")
    price = conn.execute("SELECT price FROM tickets WHERE ticket_id = 'T-1001'").fetchone()[0]
    print(f"money kept its cents: {price!r} reads back as {Decimal(price)!r}")
    conn.close()
