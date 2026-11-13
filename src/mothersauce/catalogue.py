"""
The recipe catalogue: read once from ``data/recipes.toml``, searched in memory, rendered for people and agents.

Reading the catalogue imports no recipe. Listing, searching and showing stay fast because a recipe's module is
imported only when its demo runs, and its source is read as text.
"""

import ast
import difflib
import re
import tomllib
from dataclasses import dataclass
from functools import cache
from importlib import resources
from typing import Any, Literal

__all__ = ["SECTIONS", "CatalogueError", "Recipe", "get", "recipes", "search"]

SECTIONS = ("Mise en place", "Mother sauces", "On the line", "Service", "The pass")
_STOPWORDS = frozenset("a an and are do does for how i in is it my of on or the to use using what when with".split())
_WEIGHTS = {"id": 8, "title": 5, "tags": 4, "summary": 3, "python": 2, "use_when": 2, "body": 1}


class CatalogueError(LookupError):
    """A recipe that does not exist, or a catalogue file that is inconsistent."""


@dataclass(frozen=True, slots=True)
class Recipe:
    """
    One recipe, as the catalogue describes it.

    :param id: The name commands use, such as ``context-managers``
    :param section: Where it sits on the menu
    :param title: Its title
    :param summary: One line on what it gives you
    :param tags: Words people search for
    :param python: The Python features it shows
    :param use_when: Situations it fits
    :param avoid_when: Situations it does not
    :param related: Ids of related recipes
    :param module: The module holding a code recipe
    :param practice: The Markdown file holding a practice recipe
    """

    id: str
    section: str
    title: str
    summary: str
    tags: tuple[str, ...]
    python: tuple[str, ...]
    use_when: tuple[str, ...]
    avoid_when: tuple[str, ...]
    related: tuple[str, ...]
    module: str | None = None
    practice: str | None = None

    @property
    def kind(self) -> Literal["code", "practice"]:
        """
        Whether the recipe is a module you can run or a practice you follow.

        :returns: ``code`` or ``practice``
        """
        return "code" if self.module else "practice"

    @property
    def package_path(self) -> str:
        """
        The recipe's file inside the installed package.

        :returns: A path such as ``recipes/generators.py`` or ``data/practice/bdd.md``
        """
        if self.module:
            return "/".join(self.module.split(".")[1:]) + ".py"
        return f"data/practice/{self.practice}"

    @property
    def source_path(self) -> str:
        """
        The recipe's file in the repository.

        :returns: A path from the repository root
        """
        return f"src/mothersauce/{self.package_path}"

    @property
    def tests_path(self) -> str | None:
        """
        Where a code recipe's tests live: the package path mirrored under ``tests``.

        :returns: The test file, or None for a practice recipe
        """
        if not self.module:
            return None
        *folders, name = self.module.split(".")
        return "/".join(["tests", *folders, f"test_{name}.py"])

    def source(self) -> str:
        """
        Read the recipe's file: Python source for code, Markdown for practice.

        :returns: The text
        """
        return (resources.files("mothersauce") / self.package_path).read_text(encoding="utf-8")

    def notes(self) -> str:
        """
        Return the explanation: a code recipe's module docstring, or a practice recipe's whole text.

        :returns: The text
        """
        if self.kind == "practice":
            return self.source()
        return ast.get_docstring(ast.parse(self.source())) or ""

    def as_dict(self) -> dict[str, Any]:
        """
        Describe the recipe as plain data, for ``--json`` and for MCP clients.

        :returns: Every field plus the kind and the paths
        """
        return {
            "id": self.id,
            "section": self.section,
            "title": self.title,
            "kind": self.kind,
            "summary": self.summary,
            "tags": list(self.tags),
            "python": list(self.python),
            "use_when": list(self.use_when),
            "avoid_when": list(self.avoid_when),
            "related": list(self.related),
            "source_path": self.source_path,
            "tests_path": self.tests_path,
            "run": f"mothersauce run {self.id}" if self.kind == "code" else None,
        }

    def markdown(self, part: Literal["all", "notes", "code"] = "all") -> str:
        """
        Render the recipe as Markdown: the card, then the notes, then the code. Agents and people read the same text.

        :param part: ``notes`` for the card and the explanation, ``code`` for the source alone, or ``all``
        :returns: The Markdown
        """
        if part == "code" and self.kind == "code":
            return f"```python\n{self.source().rstrip()}\n```\n"
        lines = [f"# {self.title}", "", self.summary, "", f"- **Section:** {self.section}"]
        if self.kind == "code":
            lines.append(f"- **Taste it:** `mothersauce run {self.id}`")
        lines += [
            f"- **Python:** {', '.join(f'`{p}`' for p in self.python)}",
            f"- **Use it when:** {'; '.join(self.use_when)}",
            f"- **Avoid it when:** {'; '.join(self.avoid_when)}",
            f"- **Related:** {', '.join(self.related)}",
            f"- **Source:** `{self.source_path}`" + (f"; tests in `{self.tests_path}`" if self.tests_path else ""),
            "",
        ]
        if self.kind == "practice":
            return "\n".join(lines) + "\n" + self.source()
        if part == "notes":
            return "\n".join(lines) + "\n" + self.notes() + "\n"
        return "\n".join(lines) + "\n```python\n" + self.source().rstrip() + "\n```\n"

    def search_text(self) -> dict[str, str]:
        """
        Collect the text each search weight applies to, lower cased.

        :returns: Field name to text
        """
        return {
            "id": self.id.replace("-", " "),
            "title": self.title,
            "tags": " ".join(self.tags),
            "summary": self.summary,
            "python": " ".join(self.python),
            "use_when": " ".join(self.use_when),
            "body": self.notes(),
        }


def _load(text: str) -> tuple[Recipe, ...]:
    try:
        entries = tomllib.loads(text)["recipe"]
    except (tomllib.TOMLDecodeError, KeyError) as error:
        raise CatalogueError(f"recipes.toml is not a catalogue: {error}") from error
    found = []
    for entry in entries:
        if entry.get("section") not in SECTIONS:
            raise CatalogueError(f"{entry.get('id')}: unknown section {entry.get('section')!r}")
        if bool(entry.get("module")) == bool(entry.get("practice")):
            raise CatalogueError(f"{entry.get('id')}: name exactly one of module and practice")
        sequences = {k: tuple(v) for k, v in entry.items() if isinstance(v, list)}
        found.append(Recipe(**{**entry, **sequences}))
    ids = [recipe.id for recipe in found]
    if duplicates := sorted({i for i in ids if ids.count(i) > 1}):
        raise CatalogueError(f"duplicate recipe ids: {duplicates}")
    unknown = sorted({r for recipe in found for r in recipe.related if r not in ids})
    if unknown:
        raise CatalogueError(f"related ids that are not recipes: {unknown}")
    return tuple(sorted(found, key=lambda r: SECTIONS.index(r.section)))


@cache
def recipes() -> tuple[Recipe, ...]:
    """
    Load the catalogue once per process, in menu order.

    :returns: Every recipe
    """
    return _load((resources.files("mothersauce") / "data" / "recipes.toml").read_text(encoding="utf-8"))


def _normalise(name: str) -> str:
    return name.strip().lower().replace("_", "-").replace(" ", "-")


def get(name: str) -> Recipe:
    """
    Find a recipe by id, forgiving case, spaces and underscores, or by its module's name.

    :param name: Such as ``context_managers``, ``Context managers`` or ``value_objects``
    :returns: The recipe
    :raises CatalogueError: With the closest ids, when nothing matches
    """
    wanted = _normalise(name)
    for recipe in recipes():
        module_name = (recipe.module or "").rsplit(".", 1)[-1].replace("_", "-")
        if wanted in (recipe.id, module_name, _normalise(recipe.title)):
            return recipe
    ids = [recipe.id for recipe in recipes()]
    close = difflib.get_close_matches(wanted, ids, n=3, cutoff=0.5)
    hint = f"; did you mean {' or '.join(close)}?" if close else "; see mothersauce list"
    raise CatalogueError(f"no recipe {name!r}{hint}")


def _words(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9_]+", text.lower()))


def search(query: str, limit: int = 5) -> list[tuple[Recipe, int]]:
    """
    Rank recipes for a question such as "retry a flaky api call". Matches in ids and titles weigh most.

    :param query: Words describing the problem
    :param limit: The most results to return
    :returns: Recipes with their scores, best first; empty when nothing matches
    """
    tokens = [t for t in _words(query) if t not in _STOPWORDS and len(t) > 1]
    scored = []
    for recipe in recipes():
        fields = {name: _words(text) for name, text in recipe.search_text().items()}
        score = 0
        for token in tokens:
            for name, words in fields.items():
                if token in words or (len(token) >= 3 and any(w.startswith(token) for w in words)):
                    score += _WEIGHTS[name]
        if score:
            scored.append((recipe, score))
    best = max((score for _, score in scored), default=0)
    floor = max(3, best * 0.3)  # drop the long tail of recipes that only mention a word in passing
    return sorted((pair for pair in scored if pair[1] >= floor), key=lambda pair: -pair[1])[:limit]
