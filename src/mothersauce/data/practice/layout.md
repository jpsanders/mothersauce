# Code layout

A layout should let a newcomer find anything in two guesses. This one is the src layout, with one concept per module
and tests that mirror the package.

```text
src/mothersauce/
  __init__.py        the public surface: the version, read lazily, and nothing heavy
  __main__.py        so `python -m mothersauce` works
  py.typed           tells type checkers to trust the package's hints
  cli.py             the command line, one cmd_* function per command
  catalogue.py       the recipe catalogue, read from data/recipes.toml
  mcp.py             the MCP server
  integrate.py       wiring the server and the skill into agent harnesses
  recipes/           one module per pattern
  data/              files shipped in the wheel: the catalogue, the manual, the man page, the skill, samples
tests/
  mothersauce/       mirrors the package: recipes/generators.py is tested in recipes/test_generators.py
  features/          Gherkin features, run by pytest-bdd
docs/MANUAL.md       the one source of the guide and the man page
scripts/             build_man.py, build_docs.py, bench_startup.py
```

## Rules

- **The src layout.** The package lives under `src/`, so Python never imports it from the working folder by
  accident: tests import the installed package, which in development is an editable install of `src/`. The CI job
  that installs the built wheel is what catches a file missing from the package.
- **One concept per module.** When a module needs a second sentence to say what it is for, it is two modules.
- **`__all__` lists the public names.** Everything else is private, and a leading underscore says so.
- **Absolute imports.** `from mothersauce.recipes import sql`, never `from . import sql`; flake8 enforces it.
- **No work at import time.** A module defines things; it does not open files, read the environment or connect to
  anything. Heavy dependencies are imported lazily, so importing the package is instant.
- **Data through importlib.resources.** `resources.files("mothersauce") / "data" / "recipes.toml"` works from a
  wheel, a zip or a source tree; a path built from `__file__` does not.
- **Entry points in pyproject.toml.** `[project.scripts]` makes the command; `__main__.py` makes `python -m` work.
- **Generated files are never edited by hand.** `make docs` and `make man` write them, and `make checks` fails while
  they are stale.
