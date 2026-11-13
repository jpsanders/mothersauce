# AGENTS.md

Instructions for AI coding agents working in this repository. People will find them useful too.

## Commands

```sh
make init-dev     # install the package and the development tools into the active environment
make format       # apply black and isort
make checks       # every check CI runs, in CI's order; run it before you say a change is done
make docs         # rebuild docs/RECIPES.md, the README menu, llms.txt and the skill copy from the catalogue
make man          # rebuild the man page and the packaged manual after editing docs/MANUAL.md
make bench        # start up times; fails if `mothersauce list` imports a heavy module
make demo         # run every recipe's demo
```

Develop on Python 3.15; the package requires it. `mothersauce guide` prints the user manual.

## Layout

```text
src/mothersauce/recipes/         one module per pattern, each with a demo() and full Sphinx docstrings
src/mothersauce/data/recipes.toml  the catalogue: one entry per recipe; the source of every generated doc
src/mothersauce/data/practice/   the practice recipes, as Markdown; style.md is also the MCP style guide
src/mothersauce/data/SKILL.md    the agent skill; skills/mothersauce/SKILL.md is a generated copy
src/mothersauce/cli.py           the command line, one cmd_* function per command
src/mothersauce/mcp.py           the MCP server, standard library only
src/mothersauce/catalogue.py     loads, searches and renders the catalogue without importing any recipe
src/mothersauce/integrate.py     wires the server and the skill into agent harnesses
docs/MANUAL.md                   the one source for `guide`, `man` and the packaged man page
tests/mothersauce/               pytest tests, mirroring the package
tests/features/                  Gherkin features, run by the tests/mothersauce/test_bdd_*.py step files
```

## Adding a recipe

1. Write `src/mothersauce/recipes/<module>.py`: a module docstring that explains the pattern (it becomes the
   recipe's notes), `__all__`, typed code, and a `demo()` that prints a short, deterministic story.
2. Write `tests/mothersauce/recipes/test_<module>.py`, including a test that runs `demo()`.
3. Add an entry to `src/mothersauce/data/recipes.toml`, then `make docs man` and `make checks`.

`tests/mothersauce/test_catalogue.py` fails until every recipe module has a demo, a docstring, tests and an entry.

## Rules the checks enforce

- mypy runs in strict mode on the package and the tests: full type hints everywhere; an ignore names its code.
- Docstrings use the Sphinx style (`:param name:`, `:returns:`, `:yields:`, `:raises:`); darglint checks them.
  Abstract and Protocol methods describe their return in the summary and end with `...`.
- Imports are absolute; lines are at most 120 characters in every file type.
- bandit fails on shell injection and similar; a justified exception reads `# nosec B603  # reason`.
- The generated files (docs/RECIPES.md, the README menu, llms.txt, the skill copy, the packaged manual and man page)
  are never edited by hand; `make checks` fails while any is stale.

## Conventions the checks cannot see

- Recipes are self contained and use the restaurant ticket feed as their domain; the pipeline recipe composes them.
- Keep the fast path fast: nothing heavy at import time, and `lazy import` in the CLI.
- Every command that prints data takes `--json`. Exit 0 on success, 1 on a failure, 2 on bad arguments.
- Prose in docs and docstrings uses no dashes as punctuation.
- Add an entry to CHANGELOG.md for anything a user would notice.
- Tags carry the bare version, `1.2.0`, never `v1.2.0`; the release workflow checks the README badge, the plugin
  files and `.mcp.json` name the same version.
