import json
from collections.abc import Iterator, Sequence
from pathlib import Path

import pytest

from mothersauce.recipes import factories
from mothersauce.recipes.abstractions import CsvTicketSource, JsonLinesTicketSource, Row
from mothersauce.recipes.factories import (
    CsvExporter,
    Exporter,
    JsonExporter,
    MarkdownExporter,
    SourceSpec,
    apply_transforms,
    demo,
    load_plugins,
    make_source,
    transform,
)

ROWS: list[Row] = [{"ticket_id": "T-1", "dish": "frites", "unit_price": "5.00"}]


@pytest.fixture
def clean_registry() -> Iterator[None]:
    """
    Let a test define exporters without leaking them into other tests.

    :yields: Nothing; the registry is restored afterwards
    """
    saved = dict(Exporter.registry)
    yield
    Exporter.registry.clear()
    Exporter.registry.update(saved)


def test_subclasses_register_themselves() -> None:
    assert Exporter.registry == {"csv": CsvExporter, "json": JsonExporter, "md": MarkdownExporter}


@pytest.mark.parametrize("name", ["csv", "CSV", " csv "])
def test_for_format_is_forgiving_about_case(name: str) -> None:
    assert isinstance(Exporter.for_format(name), CsvExporter)


def test_for_format_lists_known_formats() -> None:
    with pytest.raises(ValueError, match="known formats: csv, json, md"):
        Exporter.for_format("xml")


@pytest.mark.usefixtures("clean_registry")
def test_a_new_format_is_one_class() -> None:
    class TsvExporter(Exporter, fmt="tsv"):
        def render(self, rows: Sequence[Row]) -> str:
            return "\n".join("\t".join(r.values()) for r in rows)

    assert Exporter.for_format("tsv").render(ROWS) == "T-1\tfrites\t5.00"


@pytest.mark.usefixtures("clean_registry")
def test_duplicate_format_is_refused() -> None:
    with pytest.raises(TypeError, match="both claim the format 'csv'"):

        class Another(Exporter, fmt="csv"):
            def render(self, rows: Sequence[Row]) -> str:
                return ""


def test_each_exporter_renders() -> None:
    assert CsvExporter().render(ROWS) == "ticket_id,dish,unit_price\nT-1,frites,5.00\n"
    assert json.loads(JsonExporter().render(ROWS)) == ROWS
    assert MarkdownExporter().render(ROWS).splitlines()[2] == "| T-1 | frites | 5.00 |"


def test_exporters_handle_no_rows() -> None:
    assert CsvExporter().render([]) == "" and MarkdownExporter().render([]) == ""


def test_transforms_run_in_the_order_named() -> None:
    assert apply_transforms(ROWS, ["title_dish", "drop_prices"]) == [{"ticket_id": "T-1", "dish": "Frites"}]


def test_unknown_transform_is_named() -> None:
    with pytest.raises(ValueError, match="unknown transforms \\['shout'\\]"):
        apply_transforms(ROWS, ["title_dish", "shout"])


def test_transform_names_are_unique() -> None:
    with pytest.raises(ValueError, match="already registered"):
        transform("title_dish")(lambda row: row)


def test_source_spec_from_url() -> None:
    spec = SourceSpec.from_url("JSONL:///var/data/t.jsonl?limit=10&skip=2")
    assert spec == SourceSpec("jsonl", Path("/var/data/t.jsonl"), frozendict(limit="10", skip="2"))
    assert hash(spec) == hash(SourceSpec.from_url("jsonl:///var/data/t.jsonl?limit=10&skip=2"))


@pytest.mark.parametrize("url", ["tickets.csv", "csv://"])
def test_source_spec_rejects_incomplete_urls(url: str) -> None:
    with pytest.raises(ValueError, match="expected scheme:///path"):
        SourceSpec.from_url(url)


def test_source_spec_from_mapping() -> None:
    spec = SourceSpec.from_mapping({"format": "CSV", "path": "t.csv", "delimiter": ";"})
    assert (spec.scheme, spec.path, spec.options) == ("csv", Path("t.csv"), frozendict(delimiter=";"))


def test_make_source_picks_the_class_by_scheme(tmp_path: Path) -> None:
    assert isinstance(make_source(f"csv://{tmp_path}/t.csv"), CsvTicketSource)
    assert isinstance(make_source(f"jsonl://{tmp_path}/t.jsonl"), JsonLinesTicketSource)
    with pytest.raises(ValueError, match="no source reads 'parquet'"):
        make_source(f"parquet://{tmp_path}/t.parquet")


class FakeEntryPoint:
    def __init__(self, name: str) -> None:
        self.name = name
        self.loaded = False

    def load(self) -> object:
        self.loaded = True
        return object()


def test_load_plugins_imports_every_entry_point(monkeypatch: pytest.MonkeyPatch) -> None:
    found = [FakeEntryPoint("xml"), FakeEntryPoint("parquet")]
    monkeypatch.setattr(factories, "entry_points", lambda group: found if group == factories.PLUGIN_GROUP else [])
    assert load_plugins() == ["xml", "parquet"]
    assert all(e.loaded for e in found)


def test_demo_runs(capsys: pytest.CaptureFixture[str]) -> None:
    demo()
    out = capsys.readouterr().out
    assert "make_source chose CsvTicketSource" in out
    assert "| T-1001 | Steak Frites |" in out


def test_source_spec_decodes_spaces_and_accents(tmp_path: Path) -> None:
    folder = tmp_path / "menu du jour é"
    folder.mkdir()
    path = folder / "t.csv"
    path.write_text("a\n1\n", encoding="utf-8")
    source = make_source(path.as_uri().replace("file:", "csv:", 1))
    assert list(source.read()) == [{"a": "1"}]


def test_markdown_cells_escape_pipes_and_newlines() -> None:
    table = MarkdownExporter().render([{"dish": "fish | chips", "note": "two\nlines"}])
    assert table.splitlines()[2] == "| fish \\| chips | two lines |"
