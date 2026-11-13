import importlib
from pathlib import Path

import pytest

from mothersauce import catalogue
from mothersauce.catalogue import SECTIONS, CatalogueError, _load, get, recipes, search

ROOT = Path(__file__).resolve().parents[2]


def test_the_menu() -> None:
    menu = recipes()
    assert len(menu) == 26
    assert len({r.id for r in menu}) == 26
    assert [SECTIONS.index(r.section) for r in menu] == sorted(SECTIONS.index(r.section) for r in menu)


@pytest.mark.parametrize("recipe", [r for r in recipes() if r.kind == "code"], ids=lambda r: r.id)
def test_every_code_recipe_runs_and_is_tested(recipe: catalogue.Recipe) -> None:
    assert recipe.module is not None
    module = importlib.import_module(recipe.module)
    assert callable(getattr(module, "demo", None)), f"{recipe.module} has no demo()"
    assert module.__doc__ and len(module.__doc__.split()) > 40, "the module docstring is the recipe's notes"
    assert recipe.tests_path is not None and (ROOT / recipe.tests_path).is_file()
    assert (ROOT / recipe.source_path).is_file()


@pytest.mark.parametrize("recipe", [r for r in recipes() if r.kind == "practice"], ids=lambda r: r.id)
def test_every_practice_recipe_ships(recipe: catalogue.Recipe) -> None:
    assert recipe.tests_path is None
    assert recipe.source().startswith("# ")
    assert recipe.notes() == recipe.source()


def test_every_recipe_module_is_in_the_catalogue() -> None:
    modules = {r.module for r in recipes() if r.module}
    found = {f"mothersauce.recipes.{p.stem}" for p in (ROOT / "src/mothersauce/recipes").glob("*.py")}
    assert found - {"mothersauce.recipes.__init__"} <= modules


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("context-managers", "context-managers"),
        ("context_managers", "context-managers"),
        (" Context managers ", "context-managers"),
        ("value_objects", "dataclasses"),
        ("logs", "logging"),
        ("Data quality", "data-quality"),
    ],
)
def test_get_is_forgiving(name: str, expected: str) -> None:
    assert get(name).id == expected


def test_get_suggests_close_ids() -> None:
    with pytest.raises(CatalogueError, match="did you mean generators"):
        get("generator")
    with pytest.raises(CatalogueError, match="see mothersauce list"):
        get("xyzzy")


@pytest.mark.parametrize(
    ("query", "first"),
    [
        ("retry a flaky api call", "decorators"),
        ("stream a huge csv file", "generators"),
        ("immutable value object", "dataclasses"),
        ("safe sql query", "sql"),
        ("state machine", "enums"),
        ("duplicate rows", "data-quality"),
        ("log json", "logging"),
        ("pyenv virtualenv", "workflow"),
        ("gherkin scenario", "bdd"),
        ("mcp server", "mcp-server"),
        ("parallel calls", "concurrency"),
        ("slow startup", "performance"),
    ],
)
def test_search_ranks_the_right_recipe_first(query: str, first: str) -> None:
    assert search(query)[0][0].id == first


def test_search_limits_and_misses() -> None:
    assert len(search("python", limit=2)) <= 2
    assert search("zzz qqq") == []
    assert search("the and of") == []


def test_markdown_parts() -> None:
    recipe = get("enums")
    full = recipe.markdown()
    assert full.startswith("# Enums\n") and "```python\n" in full and "**Taste it:** `mothersauce run enums`" in full
    notes = recipe.markdown("notes")
    assert "```python" not in notes and "assert_never" in notes
    assert recipe.markdown("code").startswith('```python\n"""')
    assert get("bdd").markdown().endswith(get("bdd").source())


def test_as_dict() -> None:
    card = get("sql").as_dict()
    assert card["kind"] == "code" and card["run"] == "mothersauce run sql"
    assert card["tests_path"] == "tests/mothersauce/recipes/test_sql.py"
    assert get("style").as_dict()["run"] is None


GOOD = """
[[recipe]]
id = "a"
section = "Service"
title = "A"
summary = "s"
tags = []
python = []
use_when = []
avoid_when = []
related = []
module = "mothersauce.cli"
"""


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("not toml [", "not a catalogue"),
        ("[other]\n", "not a catalogue"),
        (GOOD.replace('"Service"', '"Bar"'), "unknown section"),
        (GOOD + 'practice = "x.md"\n', "exactly one of module and practice"),
        (GOOD + GOOD, "duplicate recipe ids"),
        (GOOD.replace("related = []", 'related = ["nope"]'), "related ids that are not recipes"),
    ],
)
def test_load_refuses_a_broken_catalogue(text: str, message: str) -> None:
    with pytest.raises(CatalogueError, match=message):
        _load(text)
