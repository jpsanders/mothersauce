"""
The command line: ``mothersauce``.

One ``cmd_*`` function per command. Every command that prints data takes ``--json`` and prints one JSON document with
stable fields, so scripts and AI agents read the same facts people do. Exit status 0 means success, 1 a failure and 2
a mistake in the arguments, with the reason on standard error.

Imports are lazy (``lazy import``, new in Python 3.15). ``mothersauce list`` loads the catalogue and nothing else, so
it starts in milliseconds although some recipes need pydantic: a recipe's module is imported only when ``run`` cooks
it. The manual that ``guide`` prints and ``man`` shows is built from one file, ``docs/MANUAL.md``.
"""

import argparse
import sys
from collections.abc import Callable, Sequence
lazy import contextlib
lazy import dataclasses
lazy import importlib
lazy import io
lazy import json
lazy import os
lazy import shutil
lazy import subprocess  # nosec B404  # runs man with fixed arguments only
lazy from importlib import metadata, resources
lazy from pathlib import Path

lazy from mothersauce import catalogue, integrate, mcp

__all__ = ["PROG", "build_parser", "demo", "main"]

PROG = "mothersauce"
TAGLINE = "the base recipes of production Python"
AGENTS_BLOCK = """## Python house style (mothersauce)

Write Python the way the mothersauce recipes do: strict typing, Sphinx docstrings, absolute imports, untrusted input
parsed with pydantic at the edge, frozen dataclasses for values, every acquire in a `with` block, and `logging`
instead of `print`. Before writing a pattern, look it up: `mothersauce search "<the problem>"`, then
`mothersauce show <recipe>`. The full rules: `mothersauce style`. Run the project's checks before calling a change
done.
"""


def _data(name: str) -> str:
    """
    Read a file shipped in the package's data folder.

    :param name: The file's path inside ``data``
    :returns: Its text
    """
    return (resources.files(PROG) / "data" / name).read_text(encoding="utf-8")


def _version() -> str:
    """
    Read the version only when asked, from the file setuptools_scm writes at install time.

    :returns: The version
    """
    import mothersauce

    return mothersauce.__version__


def _json(data: object) -> int:
    """
    Print data as JSON.

    :param data: Anything JSON can hold
    :returns: Exit code 0
    """
    print(json.dumps(data, indent=1))
    return 0


def _fit(line: str) -> str:
    """
    Cut a line to the terminal's width, at most 120 columns.

    :param line: The line
    :returns: The line, shortened with an ellipsis when too long
    """
    width = min(shutil.get_terminal_size((100, 24)).columns, 120)
    return line if len(line) <= width else line[: width - 1] + "…"


def _recipe(name: str) -> catalogue.Recipe | None:
    """
    Look a recipe up, reporting a miss on standard error.

    :param name: The recipe's id or module name
    :returns: The recipe, or None when there is none
    """
    try:
        return catalogue.get(name)
    except catalogue.CatalogueError as error:
        print(f"{PROG}: {error}", file=sys.stderr)
        return None


def cmd_list(args: argparse.Namespace) -> int:
    """
    Print the menu: every recipe, grouped by section.

    :param args: Parsed arguments
    :returns: Exit code
    """
    found = [r for r in catalogue.recipes() if args.section in (None, r.section) and args.kind in (None, r.kind)]
    if args.ids:
        print("\n".join(r.id for r in found))
        return 0
    if args.json:
        return _json([r.as_dict() for r in found])
    print(f"{PROG}: {TAGLINE}")
    for section in catalogue.SECTIONS:
        if rows := [r for r in found if r.section == section]:
            print(f"\n{section}")
            for recipe in rows:
                print(_fit(f"  {recipe.id:<17} {recipe.summary}"))
    print(f"\n{len(found)} recipes. Read one: {PROG} show <recipe>. Run its demo: {PROG} run <recipe>.")
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    """
    Print one recipe: its card, its notes and its tested source.

    :param args: Parsed arguments
    :returns: Exit code
    """
    recipe = _recipe(args.recipe)
    if recipe is None:
        return 2
    if args.json:
        return _json({**recipe.as_dict(), "notes": recipe.notes(), "source": recipe.source()})
    print(recipe.markdown("notes" if args.notes else "code" if args.code else "all"), end="")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    """
    Run a code recipe's demo: the recipe's own ``demo()`` function.

    :param args: Parsed arguments
    :returns: Exit code
    """
    recipe = _recipe(args.recipe)
    if recipe is None:
        return 2
    if recipe.module is None:
        print(f"{PROG}: {recipe.id} is a practice to follow, not code to run: {PROG} show {recipe.id}", file=sys.stderr)
        return 2
    print(f"{recipe.title}: {recipe.summary}\n")
    importlib.import_module(recipe.module).demo()
    return 0


def cmd_search(args: argparse.Namespace) -> int:
    """
    Rank the recipes for a problem described in a few words.

    :param args: Parsed arguments
    :returns: Exit code; 1 when nothing matches
    """
    query = " ".join(args.query)
    hits = catalogue.search(query, args.limit)
    if args.json:
        _json([{"id": r.id, "title": r.title, "summary": r.summary, "score": score} for r, score in hits])
        return 0 if hits else 1
    if not hits:
        print(f"no recipe matches {query!r}; try fewer words, or {PROG} list", file=sys.stderr)
        return 1
    noun = "recipe" if len(hits) == 1 else "recipes"
    print(f"{len(hits)} {noun} for {query!r}: {', '.join(r.id for r, _ in hits)}")
    for recipe, _ in hits:
        print(_fit(f"  {recipe.id:<17} {recipe.summary}"))
    return 0


def cmd_style(args: argparse.Namespace) -> int:
    """
    Print the house style, or a short block for a project's AGENTS.md or CLAUDE.md.

    :param args: Parsed arguments
    :returns: Exit code
    """
    print(AGENTS_BLOCK if args.agents else mcp.style_guide(), end="")
    return 0


def cmd_guide(args: argparse.Namespace) -> int:
    """
    Print the full manual as Markdown, written for people and agents alike.

    :param args: Parsed arguments
    :returns: Exit code
    """
    print(_data("MANUAL.md"), end="")
    return 0


def man_folder() -> Path:
    """
    Find the per user man folder that ``man`` searches without any setup.

    :returns: ``$XDG_DATA_HOME/man/man1``, or ``~/.local/share/man/man1``
    """
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / "man" / "man1"


def cmd_man(args: argparse.Namespace) -> int:
    """
    Show the man page, print it as roff, or install it so ``man mothersauce`` works.

    :param args: Parsed arguments
    :returns: Exit code
    """
    page = _data(f"{PROG}.1")
    if args.install:
        target = man_folder() / f"{PROG}.1"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(page, encoding="utf-8")
        print(f"installed {target}; read it with: man {PROG}")
        return 0
    man = shutil.which("man")
    if man and sys.stdout.isatty() and not args.raw:
        with resources.as_file(resources.files(PROG) / "data" / f"{PROG}.1") as path:
            return subprocess.call([man, "-l", str(path)])  # nosec B603  # man with fixed arguments
    print(page, end="")
    return 0


def cmd_mcp(args: argparse.Namespace) -> int:
    """
    Serve the recipes over MCP on standard input and output, for an agent harness.

    :param args: Parsed arguments
    :returns: Exit code
    """
    mcp.serve()
    return 0


def cmd_integrate(args: argparse.Namespace) -> int:
    """
    Register the MCP server and install the skill in every agent harness found, or the ones named.

    :param args: Parsed arguments
    :returns: Exit code; 1 when nothing was found or a step failed
    """
    steps = integrate.run(args.harnesses, dry=args.dry_run)
    if args.json:
        _json([dataclasses.asdict(step) for step in steps])
    else:
        for step in steps:
            print(step.line())
        if not steps:
            server = {"mcpServers": {PROG: {"command": integrate.command()[0], "args": integrate.command()[1:]}}}
            print(f"no agent harness found; add the server to any MCP client by hand:\n{json.dumps(server)}")
    failed = [s for s in steps if not s.done and not args.dry_run]
    return 1 if failed or not steps else 0


def cmd_skill(args: argparse.Namespace) -> int:
    """
    Print the agent skill, ready to save as ``skills/mothersauce/SKILL.md`` in any harness.

    :param args: Parsed arguments
    :returns: Exit code
    """
    print(integrate.skill_text(), end="")
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    """
    Check what mothersauce needs and report the optional extras.

    :param args: Parsed arguments
    :returns: Exit code; 1 when something required is missing
    """
    checks: list[dict[str, object]] = []

    def check(name: str, ok: bool, detail: str, required: bool = True) -> None:
        checks.append({"check": name, "ok": ok, "required": required, "detail": detail})

    version = sys.version.split()[0]
    check("python", sys.version_info >= (3, 15), f"{version}, needs 3.15 or later")
    try:
        check("pydantic", True, metadata.version("pydantic"))
    except metadata.PackageNotFoundError:
        check("pydantic", False, f"missing: pip install --force-reinstall {PROG}")
    missing = [r.id for r in catalogue.recipes() if not (resources.files(PROG) / r.package_path).is_file()]
    check("recipes", not missing, f"{len(catalogue.recipes())} recipes" + (f", missing {missing}" if missing else ""))
    page = man_folder() / f"{PROG}.1"
    check("man page", page.is_file(), str(page) if page.is_file() else f"run: {PROG} man --install", required=False)
    skill = Path.home() / ".claude" / "skills" / PROG / "SKILL.md"
    check("agent skill", skill.is_file(), str(skill) if skill.is_file() else f"run: {PROG} integrate", required=False)
    pyenv = shutil.which("pyenv")
    check("pyenv", bool(pyenv), pyenv or "not found; see the workflow recipe", required=False)
    if args.json:
        _json(checks)
    else:
        for item in checks:
            mark = "ok" if item["ok"] else ("!!" if item["required"] else "--")
            print(f"[{mark}] {item['check']:<12} {item['detail']}")
    return 0 if all(item["ok"] for item in checks if item["required"]) else 1


def build_parser() -> argparse.ArgumentParser:
    """
    Build the argument parser with every command.

    :returns: The parser
    """
    parser = argparse.ArgumentParser(prog=PROG, description=f"{PROG}: {TAGLINE}.")
    parser.add_argument("--version", action="store_true", help="print the version and exit")
    sub = parser.add_subparsers(dest="command", metavar="command")

    def add(
        name: str, func: Callable[[argparse.Namespace], int], about: str, json_flag: bool = False
    ) -> argparse.ArgumentParser:
        command = sub.add_parser(name, help=about, description=about)
        if json_flag:
            command.add_argument("--json", action="store_true", help="print JSON")
        command.set_defaults(func=func)
        return command

    listing = add("list", cmd_list, "show the menu: every recipe by section", json_flag=True)
    listing.add_argument("--section", choices=catalogue.SECTIONS, help="only this section")
    listing.add_argument("--kind", choices=["code", "practice"], help="only code recipes, or only practices")
    listing.add_argument("--ids", action="store_true", help="print the ids only, one per line")
    show = add("show", cmd_show, "show a recipe: when to use it, when not, and its tested source", json_flag=True)
    show.add_argument("recipe", help="a recipe id, such as context-managers")
    part = show.add_mutually_exclusive_group()
    part.add_argument("--notes", action="store_true", help="the card and the explanation, without the source")
    part.add_argument("--code", action="store_true", help="the source alone")
    add("run", cmd_run, "run a recipe's demo").add_argument("recipe", help="a code recipe's id")
    search = add("search", cmd_search, "find the recipes for a problem", json_flag=True)
    search.add_argument("query", nargs="+", help="the problem in a few words")
    search.add_argument("--limit", type=int, default=5, metavar="N", help="at most N results (default 5)")
    style = add("style", cmd_style, "print the house style")
    style.add_argument("--agents", action="store_true", help="print a short block for AGENTS.md or CLAUDE.md")
    add("guide", cmd_guide, "print the full manual, for people and agents")
    man = add("man", cmd_man, "show the man page")
    man.add_argument("--install", action="store_true", help=f"install it so `man {PROG}` works")
    man.add_argument("--raw", action="store_true", help="print the roff source")
    add("mcp", cmd_mcp, "serve the recipes to an AI agent over MCP (stdio)")
    integrate_cmd = add("integrate", cmd_integrate, "add the MCP server and the skill to your agent harnesses", True)
    integrate_cmd.add_argument("harnesses", nargs="*", help="claude, codex, opencode, gemini, cursor (default: all)")
    integrate_cmd.add_argument("--dry-run", action="store_true", help="only say what would change")
    add("skill", cmd_skill, "print the agent skill")
    add("doctor", cmd_doctor, "check the install and the optional extras", json_flag=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """
    Run the command line.

    :param argv: Arguments, without the program name; ``sys.argv`` when omitted
    :returns: Exit code
    """
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.version:
        print(f"{PROG} {_version()}")
        return 0
    if not getattr(args, "func", None):
        args = parser.parse_args(["list"])
    result: int = args.func(args)
    return result


def demo() -> None:
    """Show the commands, then read one command's JSON the way an agent would."""
    for action in build_parser()._subparsers._group_actions[0]._choices_actions:  # type: ignore[union-attr]
        print(f"  {action.dest:<10} {action.help}")
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        main(["search", "retry", "a", "flaky", "api", "call", "--json"])
    best = json.loads(out.getvalue())[0]
    print(f"\nan agent runs `{PROG} search retry a flaky api call --json` and reads: {best['id']} ({best['score']})")
