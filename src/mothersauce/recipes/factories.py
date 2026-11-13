"""
Factories: decide which class to build in exactly one place.

Code that says ``if fmt == "csv": ... elif fmt == "json": ...`` in five places has five places to forget the next
format. A factory moves the decision to one place, and the rest of the code asks for "an exporter for this format".

Three shapes cover most production code. First, a registry filled as classes are defined, by ``__init_subclass__``
or by a decorator: adding a format is the whole change, and nothing else is edited, which is the open closed
principle without ceremony. Second, alternative constructors as classmethods, such as ``from_url`` and
``from_mapping``: many ways to build one type, each named for its input, all returning ``Self`` so subclasses inherit
them correctly. Third, a factory function that reads configuration, here a URL, and returns the right object behind
an abstract type.

Plugins from other packages join the same registry through entry points, without this package knowing their names.
"""

import csv
import io
import json
import tempfile
from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from importlib.metadata import entry_points
from pathlib import Path
from typing import ClassVar, Self
from urllib.parse import parse_qsl, unquote, urlsplit

from mothersauce.recipes.abstractions import CsvTicketSource, JsonLinesTicketSource, Row, TicketSource

__all__ = [
    "PLUGIN_GROUP",
    "SOURCES",
    "TRANSFORMS",
    "CsvExporter",
    "Exporter",
    "JsonExporter",
    "MarkdownExporter",
    "SourceSpec",
    "apply_transforms",
    "demo",
    "load_plugins",
    "make_source",
    "transform",
]

PLUGIN_GROUP = "mothersauce.exporters"


class Exporter(ABC):
    """
    Renders rows in one format. Each subclass registers itself under the format it names in its class line.

    >>> sorted(Exporter.registry)
    ['csv', 'json', 'md']
    """

    registry: ClassVar[dict[str, type[Exporter]]] = {}
    fmt: ClassVar[str]

    def __init_subclass__(cls, /, fmt: str, **kwargs: object) -> None:
        """
        Register a new exporter as Python creates its class.

        :param fmt: The format name, given in the class line: ``class X(Exporter, fmt="xml")``
        :param kwargs: Passed on, so this class composes with other bases
        :raises TypeError: When a second exporter claims the same format
        """
        super().__init_subclass__(**kwargs)
        if fmt in Exporter.registry:
            raise TypeError(f"{cls.__name__} and {Exporter.registry[fmt].__name__} both claim the format {fmt!r}")
        cls.fmt = fmt
        Exporter.registry[fmt] = cls

    @abstractmethod
    def render(self, rows: Sequence[Row]) -> str:
        """
        Render rows as text in this exporter's format.

        :param rows: The rows, all with the same keys
        """
        ...

    @classmethod
    def for_format(cls, fmt: str) -> Exporter:
        """
        Return an exporter for a format name. This is the factory method.

        :param fmt: A registered format, any case
        :returns: A new exporter
        :raises ValueError: Listing the known formats when there is no match
        """
        try:
            return cls.registry[fmt.strip().lower()]()
        except KeyError:
            raise ValueError(f"no exporter for {fmt!r}; known formats: {', '.join(sorted(cls.registry))}") from None


class CsvExporter(Exporter, fmt="csv"):
    """Comma separated values with a header line."""

    def render(self, rows: Sequence[Row]) -> str:
        """
        Render as CSV.

        :param rows: The rows
        :returns: CSV text
        """
        out = io.StringIO()
        if rows:
            writer = csv.DictWriter(out, fieldnames=list(rows[0]), lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
        return out.getvalue()


class JsonExporter(Exporter, fmt="json"):
    """A JSON array, one object per row."""

    def render(self, rows: Sequence[Row]) -> str:
        """
        Render as JSON.

        :param rows: The rows
        :returns: JSON text
        """
        return json.dumps(list(rows), indent=1)


class MarkdownExporter(Exporter, fmt="md"):
    """A Markdown table, for pull requests and chat."""

    def render(self, rows: Sequence[Row]) -> str:
        """
        Render as a Markdown table.

        :param rows: The rows
        :returns: The table
        """
        if not rows:
            return ""
        keys = list(rows[0])
        lines = ["| " + " | ".join(keys) + " |", "|" + " --- |" * len(keys)]
        lines += ["| " + " | ".join(_cell(row[k]) for k in keys) + " |" for row in rows]
        return "\n".join(lines) + "\n"


def _cell(text: str) -> str:
    """
    Escape a value for a Markdown table cell: a pipe would start a new column and a newline would end the row.

    :param text: The value
    :returns: The escaped value
    """
    return text.replace("|", "\\|").replace("\n", " ")


type Transform = Callable[[Row], Row]
TRANSFORMS: dict[str, Transform] = {}


def transform(name: str) -> Callable[[Transform], Transform]:
    """
    Register a row transform under a name, so configuration can refer to it as text.

    :param name: The name configuration uses
    :returns: A decorator that registers the function and returns it unchanged
    """

    def register(func: Transform) -> Transform:
        if name in TRANSFORMS:
            raise ValueError(f"transform {name!r} is already registered")
        TRANSFORMS[name] = func
        return func

    return register


@transform("title_dish")
def title_dish(row: Row) -> Row:
    """
    Write the dish in title case for menus and receipts.

    :param row: The row
    :returns: A new row
    """
    return {**row, "dish": row.get("dish", "").title()}


@transform("drop_prices")
def drop_prices(row: Row) -> Row:
    """
    Remove price columns before sharing a report outside the business.

    :param row: The row
    :returns: A new row without keys that mention price
    """
    return {k: v for k, v in row.items() if "price" not in k}


def apply_transforms(rows: Sequence[Row], names: Sequence[str]) -> list[Row]:
    """
    Run named transforms in order, as configuration lists them.

    :param rows: The rows
    :param names: Registered transform names
    :returns: The transformed rows
    :raises ValueError: When a name is not registered
    """
    unknown = [n for n in names if n not in TRANSFORMS]
    if unknown:
        raise ValueError(f"unknown transforms {unknown}; known: {sorted(TRANSFORMS)}")
    out = list(rows)
    for name in names:
        out = [TRANSFORMS[name](row) for row in out]
    return out


@dataclass(frozen=True, slots=True)
class SourceSpec:
    """
    Where to read tickets from. Built from a URL or from a config mapping by its alternative constructors.

    :param scheme: The format, such as ``csv`` or ``jsonl``
    :param path: The file
    :param options: Extra settings from the URL query; a frozendict, so the spec stays hashable
    """

    scheme: str
    path: Path
    options: frozendict[str, str] = field(default_factory=frozendict)

    @classmethod
    def from_url(cls, url: str) -> Self:
        """
        Parse ``scheme:///path?key=value``.

        >>> SourceSpec.from_url("csv:///data/tickets.csv?delimiter=;").options
        frozendict({'delimiter': ';'})

        :param url: The URL
        :returns: The spec
        :raises ValueError: When the URL has no scheme or no path
        """
        parts = urlsplit(url)
        if not parts.scheme or not parts.path:
            raise ValueError(f"expected scheme:///path, got {url!r}")
        return cls(parts.scheme.lower(), Path(unquote(parts.path)), frozendict(parse_qsl(parts.query)))

    @classmethod
    def from_mapping(cls, data: Mapping[str, str]) -> Self:
        """
        Build from a configuration section such as ``{"format": "csv", "path": "tickets.csv"}``.

        :param data: The section; keys other than format and path become options
        :returns: The spec
        """
        options = {k: v for k, v in data.items() if k not in {"format", "path"}}
        return cls(data["format"].lower(), Path(data["path"]), frozendict(options))


SOURCES: dict[str, Callable[[Path], TicketSource]] = {"csv": CsvTicketSource, "jsonl": JsonLinesTicketSource}


def make_source(url: str) -> TicketSource:
    """
    Read a URL and return the right source behind the abstract type. This is the factory function.

    :param url: Such as ``csv:///data/tickets.csv``
    :returns: A ticket source
    :raises ValueError: When nothing reads that scheme
    """
    spec = SourceSpec.from_url(url)
    try:
        build = SOURCES[spec.scheme]
    except KeyError:
        raise ValueError(f"no source reads {spec.scheme!r}; known: {', '.join(sorted(SOURCES))}") from None
    return build(spec.path)


def load_plugins(group: str = PLUGIN_GROUP) -> list[str]:
    """
    Import the exporters other installed packages declare. Importing a subclass is what registers it.

    A plugin package declares, in its pyproject.toml::

        [project.entry-points."mothersauce.exporters"]
        xml = "acme_exporters.xml"

    :param group: The entry point group
    :returns: The names that were loaded
    """
    loaded = []
    for entry in entry_points(group=group):
        entry.load()
        loaded.append(entry.name)
    return loaded


def demo() -> None:
    """Pick a source from a URL, transform by name and export in every registered format."""
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "tickets.csv"
        path.write_text("ticket_id,dish,unit_price\nT-1001,steak frites,24.00\nT-1002,bearnaise,4.50\n", "utf-8")
        source = make_source(path.as_uri().replace("file:", "csv:", 1))
        rows = list(source.read())
    print(f"make_source chose {type(source).__name__} from the URL scheme")
    shared = apply_transforms(rows, ["title_dish", "drop_prices"])
    print(f"exporters registered by subclassing alone: {', '.join(sorted(Exporter.registry))}")
    print(Exporter.for_format("MD").render(shared), end="")
    print(f"loaded plugins: {load_plugins() or 'none installed'}")
    try:
        Exporter.for_format("xml")
    except ValueError as error:
        print(error)
