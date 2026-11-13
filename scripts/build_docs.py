"""
Build the documents that list the recipes, from the catalogue in ``src/mothersauce/data/recipes.toml``.

One source, five places that must agree with it: ``docs/RECIPES.md``, the menu in ``README.md``, the recipe list in
``docs/MANUAL.md``, ``llms.txt``, and the skill copy in ``skills/mothersauce/SKILL.md`` that the Claude Code plugin
and ``npx skills`` read.

    python scripts/build_docs.py           # write them
    python scripts/build_docs.py --check   # fail when any of them is stale
"""

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from mothersauce.catalogue import SECTIONS, Recipe, recipes  # noqa: E402  # needs the path above

REPO = "https://github.com/jpsanders/mothersauce"
SKILL = ROOT / "src" / "mothersauce" / "data" / "SKILL.md"
SKILL_COPY = ROOT / "skills" / "mothersauce" / "SKILL.md"
RECIPES_MD = ROOT / "docs" / "RECIPES.md"
README = ROOT / "README.md"
MANUAL = ROOT / "docs" / "MANUAL.md"
LLMS = ROOT / "llms.txt"


def _link(recipe: Recipe) -> str:
    """
    Link a recipe's id to its source file on GitHub, absolute so the link also works on PyPI.

    :param recipe: The recipe
    :returns: A Markdown link
    """
    return f"[`{recipe.id}`]({REPO}/blob/main/{recipe.source_path})"


def recipes_md() -> str:
    """
    Render the full menu: every recipe's card, by section.

    :returns: The Markdown
    """
    out = [
        "# The menu",
        "",
        "Every recipe, by section. Generated from `src/mothersauce/data/recipes.toml` by `make docs`; edit that file,",
        "not this one. Read any recipe with `mothersauce show <id>` and run a code recipe with `mothersauce run <id>`.",
    ]
    for section in SECTIONS:
        out += ["", f"## {section}"]
        for recipe in (r for r in recipes() if r.section == section):
            out += ["", f"### {recipe.title}", "", f"{recipe.summary}", ""]
            out.append(f"- **Id:** `{recipe.id}`, {recipe.kind}; source [`{recipe.source_path}`]({recipe.source_path})")
            if recipe.tests_path:
                out.append(f"- **Tests:** [`{recipe.tests_path}`]({recipe.tests_path})")
            out.append(f"- **Python:** {', '.join(f'`{p}`' for p in recipe.python)}")
            out.append(f"- **Use it when:** {'; '.join(recipe.use_when)}")
            out.append(f"- **Avoid it when:** {'; '.join(recipe.avoid_when)}")
            out.append(f"- **Related:** {', '.join(f'`{r}`' for r in recipe.related)}")
    return "\n".join(out) + "\n"


def readme_menu() -> str:
    """
    Render the README's menu: one table row per recipe.

    :returns: The Markdown table
    """
    rows = ["| Section | Recipe | What it gives you |", "| --- | --- | --- |"]
    for recipe in recipes():
        rows.append(f"| {recipe.section} | {_link(recipe)} | {recipe.summary} |")
    return "\n".join(rows)


def manual_menu() -> str:
    """
    Render the manual's recipe list, in the subset of Markdown that build_man.py turns into roff.

    :returns: The Markdown
    """
    out: list[str] = []
    for section in SECTIONS:
        out += [f"### {section}", "", "| Recipe | What it gives you |", "| --- | --- |"]
        out += [f"| `{r.id}` | {r.summary} |" for r in recipes() if r.section == section]
        out.append("")
    return "\n".join(out).rstrip()


def llms_txt() -> str:
    """
    Render llms.txt: what the project is and where an agent finds each part.

    :returns: The text
    """
    lines = [
        "# mothersauce",
        "",
        "> The base recipes of production Python 3.15: factories, abstractions, dataclasses, pydantic, generators,",
        "> context managers, generics and more, each a typed, tested module with a runnable demo, plus the practices",
        "> around them. A CLI, a man page, an MCP server and an agent skill serve them to people and AI agents.",
        "",
        "Install: `uv tool install mothersauce` or `pip install mothersauce`. Then `mothersauce list`,",
        '`mothersauce search "<problem>"`, `mothersauce show <recipe>`, `mothersauce run <recipe>`, or',
        "`mothersauce mcp` as an MCP server. `mothersauce guide` prints the full manual.",
        "",
        "## Docs",
        "",
        f"- [README]({REPO}/blob/main/README.md): what it is, install, use with an agent",
        f"- [Manual]({REPO}/blob/main/docs/MANUAL.md): every command, the MCP tools, the workflow",
        f"- [Menu]({REPO}/blob/main/docs/RECIPES.md): every recipe with when to use it and when not",
        f"- [Skill]({REPO}/blob/main/skills/mothersauce/SKILL.md): which recipe for which problem",
        f"- [AGENTS.md]({REPO}/blob/main/AGENTS.md): working on this repository",
        "",
        "## Recipes",
        "",
    ]
    lines += [f"- [{r.id}]({REPO}/blob/main/{r.source_path}): {r.summary}" for r in recipes()]
    return "\n".join(lines) + "\n"


def _between(text: str, name: str, body: str) -> str:
    """
    Replace the text between ``<!-- name:start -->`` and ``<!-- name:end -->``.

    :param text: The document
    :param name: The marker name
    :param body: The new text between the markers
    :returns: The document with the block replaced
    :raises SystemExit: When the markers are missing
    """
    pattern = re.compile(rf"(<!-- {name}:start -->\n).*?(<!-- {name}:end -->)", re.S)
    if not pattern.search(text):
        raise SystemExit(f"markers <!-- {name}:start --> and <!-- {name}:end --> not found")
    return pattern.sub(lambda m: m.group(1) + body + "\n" + m.group(2), text)


def main() -> int:
    """
    Write or check every generated document.

    :returns: Exit code
    """
    parser = argparse.ArgumentParser(description="Build the recipe docs from the catalogue.")
    parser.add_argument("--check", action="store_true", help="fail when a generated file is stale")
    args = parser.parse_args()
    wanted = {
        RECIPES_MD: recipes_md(),
        README: _between(README.read_text(encoding="utf-8"), "menu", readme_menu()),
        MANUAL: _between(MANUAL.read_text(encoding="utf-8"), "recipes", manual_menu()),
        LLMS: llms_txt(),
        SKILL_COPY: SKILL.read_text(encoding="utf-8"),
    }
    stale = [p for p, text in wanted.items() if not p.is_file() or p.read_text(encoding="utf-8") != text]
    if args.check:
        for path in stale:
            print(f"out of date: {path.relative_to(ROOT)} (run: make docs)", file=sys.stderr)
        return 1 if stale else 0
    for path in stale:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(wanted[path], encoding="utf-8")
        print(f"wrote {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
