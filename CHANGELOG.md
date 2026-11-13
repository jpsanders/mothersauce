# Changelog

Versions follow [semantic versioning](https://semver.org). Tags carry the bare version, such as `1.0.0`.

## 1.0.0 (2026-11-13)

The first release.

- 26 recipes on a menu of five sections. 21 code recipes, each a typed module with a demo and its own tests:
  dataclasses, pydantic, enums, abstractions, factories, generics, generators, context managers, decorators, object
  oriented design, data structures, errors, SQL, data quality, a pipeline that composes them, structured logging,
  configuration, concurrency, performance, the CLI and the MCP server. 5 practice recipes: the workflow, layout, style,
  testing and behaviour driven tests. The pipeline loads exactly once by key, so a late or corrected line still lands.
- Python 3.15 used where it helps: `lazy import`, `frozendict`, `sentinel()`, unpacking in comprehensions, closed
  `TypedDict`, template strings for SQL, and the generics syntax with defaults.
- `mothersauce`: `list`, `show`, `run`, `search`, `style`, `guide`, `man`, `mcp`, `integrate`, `skill` and `doctor`,
  with `--json` wherever there is data. `list` starts in about 35 ms and never imports pydantic.
- A man page and a guide built from one manual, `docs/MANUAL.md`.
- For agents: a read only MCP server with four tools, a resource per recipe and two prompts; a skill; a Claude Code
  plugin; `integrate` for Claude Code, Codex, OpenCode, Gemini CLI and Cursor; `style --agents` for AGENTS.md; and
  llms.txt.
- Built on python-package-template 1.0.0: pyenv and pyenv-virtualenv, a Makefile that CI runs as is, pytest with
  doctests and pytest-bdd scenarios, a coverage floor of 95%, and a release workflow that attaches the wheel.
