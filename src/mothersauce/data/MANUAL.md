# mothersauce

## NAME

mothersauce - the base recipes of production Python, typed, tested and served to your AI agent

## SYNOPSIS

```
mothersauce [--version] [command] [options]
mothersauce list [--section SECTION] [--kind code|practice] [--ids] [--json]
mothersauce show RECIPE [--notes | --code] [--json]
mothersauce run RECIPE
mothersauce search WORDS... [--limit N] [--json]
mothersauce style [--agents]
mothersauce guide
mothersauce man [--install | --raw]
mothersauce mcp
mothersauce integrate [HARNESS...] [--dry-run] [--json]
mothersauce skill
mothersauce doctor [--json]
```

## DESCRIPTION

Every cuisine rests on a handful of mother sauces; learn them and every other sauce is a variation. Production Python
is the same: a few dozen patterns carry almost every codebase. mothersauce collects them as recipes.

A code recipe is one small module of Python 3.15 with full type hints, Sphinx docstrings, a `demo()` you can run, and
its own tests. A practice recipe is a short guide to the work around the code: the workflow, the layout, the style,
the tests. Every recipe has a card that says when to use it and when not to.

The recipes share one example domain, a restaurant's ticket feed, so they read as one system: the pipeline recipe
loads that feed using most of the others. Copy the shape of a recipe, not its names.

The same recipes reach people and agents four ways: this command, this manual (`guide`, `man`), an MCP server
(`mcp`) and an agent skill (`skill`, `integrate`). With no command, `mothersauce` prints the menu.

## COMMANDS

| Command | What it does |
| --- | --- |
| `list` | Print the menu, every recipe by section. `--section` and `--kind` filter it; `--ids` prints ids only. |
| `show RECIPE` | Print a recipe: card, notes and tested source. `--notes` drops the source; `--code` keeps it alone. |
| `run RECIPE` | Run a code recipe's demo. Practice recipes have no demo; read them with `show`. |
| `search WORDS` | Rank the recipes for a problem described in a few words, best first. |
| `style` | Print the house style. `--agents` prints a short block to paste into a project's AGENTS.md or CLAUDE.md. |
| `guide` | Print this manual as Markdown. |
| `man` | Show this manual as a man page. `--install` puts it where `man mothersauce` finds it; `--raw` prints roff. |
| `mcp` | Serve the recipes to an AI agent over the Model Context Protocol, on standard input and output. |
| `integrate` | Add the MCP server to Claude Code, Codex, OpenCode, Gemini CLI and Cursor, and the skill where read. |
| `skill` | Print the agent skill. |
| `doctor` | Check the install: Python, pydantic, the recipes; and report the man page, the skill and pyenv. |

A recipe can be named by its id (`context-managers`), with underscores or spaces (`context_managers`), by its title,
or by its module's name (`value_objects` finds `dataclasses`). A near miss suggests the closest ids.

## OPTIONS

| Option | Meaning |
| --- | --- |
| `--json` | Print one JSON document instead of text: `list`, `show`, `search`, `integrate`, `doctor`. |
| `--section SECTION` | With `list`: only one section, such as "Mother sauces". |
| `--kind KIND` | With `list`: only `code` recipes, or only `practice` recipes. |
| `--ids` | With `list`: one id per line, for scripts. |
| `--notes`, `--code` | With `show`: the card and notes only, or the source only. |
| `--limit N` | With `search`: at most N results. Default: 5. |
| `--agents` | With `style`: the short block for an agent's instructions file. |
| `--install`, `--raw` | With `man`: install the man page, or print its roff source. |
| `--dry-run` | With `integrate`: say what would change and change nothing. |
| `--version` | Print the version and exit. |
| `--help` | Print a command's options and exit. |

## RECIPES

The menu runs like a kitchen: prepare, cook the bases, work the line, run the service, check at the pass.

<!-- recipes:start -->
### Mise en place

| Recipe | What it gives you |
| --- | --- |
| `workflow` | pyenv and pyenv-virtualenv, make targets, and CI that runs exactly what your machine runs. |
| `layout` | The src layout: one package, one concept per module, tests that mirror it, data shipped inside. |
| `style` | Ten checks that end style arguments: black, isort, flake8, darglint, mypy strict, bandit and more. |

### Mother sauces

| Recipe | What it gives you |
| --- | --- |
| `dataclasses` | Small, honest value objects: frozen, slotted, validated, replaced rather than mutated. |
| `pydantic` | Parse, don't validate, at the edges: frozen models that forbid extras, reusable constraints, unions. |
| `enums` | Closed sets of names: StrEnum, IntEnum, Flag, a state machine, and exhaustive match with assert_never. |
| `abstractions` | ABCs for families you own, with a template method; Protocols for shapes you accept. |
| `factories` | Decide which class to build in one place: registries, __init_subclass__, from_ constructors, plugins. |
| `generics` | Write the container once and keep every type: PEP 695 syntax, bounds, defaults, ParamSpec, Result. |
| `generators` | Any size of input in the memory of one record: streams, stages, batches, windows, send, cursors. |
| `context-managers` | Every acquire paired with its release: timers, atomic writes, nested transactions, ExitStack. |
| `decorators` | Cross cutting behaviour written once: typed retry with backoff and jitter, caches, singledispatch. |
| `oop` | Composition over inheritance, dunder protocols, properties, descriptors and __slots__. |
| `data-structures` | The container that makes the code obvious: Counter, deque, heapq, bisect, ChainMap, graphlib. |
| `errors` | A hierarchy you can catch, chains you can follow, and batches that report every failure at once. |

### On the line

| Recipe | What it gives you |
| --- | --- |
| `sql` | Injection proof queries with template strings, schema evolution, idempotent upserts and high watermarks. |
| `data-quality` | Rules as data, severities, quarantine, and overrides with an audit trail. |
| `pipeline` | Most recipes plated together: a small, real ETL with quality rules, upserts by key and JSON logs. |

### Service

| Recipe | What it gives you |
| --- | --- |
| `logging` | JSON lines with a run id from a ContextVar, secrets redacted, configured once with dictConfig. |
| `config` | One frozen settings object from defaults, TOML, environment and flags, with where each value came from. |
| `concurrency` | Wait for many slow things at once, bounded, in order, without losing a single error. |
| `performance` | Measure first, then make the common path cheap: lazy imports, timeit, import costs. |
| `cli` | This package's own CLI: subcommands, --json wherever there is data, exit codes, a man page, lazy imports. |
| `mcp-server` | This package's own MCP server: JSON-RPC over stdio with tools, resources and prompts. |

### The pass

| Recipe | What it gives you |
| --- | --- |
| `testing` | Fixtures, parametrize, fakes over mocks, doctests and a coverage gate: nothing broken leaves the pass. |
| `bdd` | Gherkin features run by pytest-bdd: behaviour written so a person can read it and pytest can run it. |
<!-- recipes:end -->

## FOR AI AGENTS

Everything a person reads, an agent can read too. Run commands with `--json` and parse the document; the fields are
stable. `mothersauce guide` returns this whole manual, so an agent can learn the tool without a browser. No command
touches the network. `man --install` writes one file in the user's man folder, and `integrate` edits the agent
harnesses' own configuration, after a backup.

### The MCP server

`mothersauce mcp` speaks the Model Context Protocol over stdio. Every tool is read only.

| Tool | What it returns |
| --- | --- |
| `search_recipes` | The recipes for a problem: `{"query": "retry a flaky api call", "limit": 5}`. |
| `get_recipe` | One recipe as Markdown: `{"id": "decorators", "part": "all"}`; part is `all`, `notes` or `code`. |
| `list_recipes` | Every recipe's card, optionally for one `section` or `kind`. |
| `get_style_guide` | The house style. |

It also offers every recipe as a resource, `mothersauce://recipes/<id>`, the style guide as `mothersauce://style`,
and two prompts: `apply_recipe` (a recipe and a task) and `review_python` (code to review against the style).

Add it to any MCP client by hand:

```
{"mcpServers": {"mothersauce": {"command": "mothersauce", "args": ["mcp"]}}}
```

or without installing anything first, through uv:

```
{"mcpServers": {"mothersauce": {"command": "uvx",
  "args": ["--from", "git+https://github.com/jpsanders/mothersauce", "mothersauce", "mcp"]}}}
```

### The skill and the plugin

`mothersauce integrate` finds the harnesses installed for the current user and registers the server in each. It
installs the skill in the three that read skills folders: Claude Code, Codex and OpenCode. Claude Code and Codex are
changed through `claude mcp add` and `codex mcp add`; when the `claude` command is missing, the line to run is printed
instead, because Claude Code's own configuration file is never edited from outside. The other configuration files
are edited after a backup, and one that does not parse is left alone. `--dry-run` reports exactly what a real run
would do. The repository is also a Claude Code plugin, with the skill and the server in one step:

```
/plugin install mothersauce --marketplace jpsanders/mothersauce
```

On Claude Code before 2.1.275, add the marketplace first with `/plugin marketplace add jpsanders/mothersauce`, then
run `/plugin install mothersauce@mothersauce`.

`mothersauce skill` prints the skill for any other harness, and `npx skills add jpsanders/mothersauce` installs it
in the harnesses that tool knows.

### One line in AGENTS.md

`mothersauce style --agents` prints a short block for a project's AGENTS.md or CLAUDE.md. It tells any agent working
in that project to write Python the way the recipes do and to look patterns up before writing them.

## THE WORKFLOW

The repository is built on python-package-template and keeps its workflow: a pyenv virtual environment per project,
one Makefile for every command, and CI that runs exactly what the Makefile runs.

```
pyenv install 3.15.2
pyenv virtualenv 3.15.2 mothersauce
pyenv local mothersauce
make init-dev
make checks
```

`make checks` runs editorconfig-checker, black, isort, bandit, flake8, darglint, mypy in strict mode, the docs and
man page freshness checks, and pytest with doctests, pytest-bdd scenarios and a coverage floor of 95%, in the order
CI runs them. `make docs`
and `make man` rebuild the generated documents, `make bench` times the start up, and `make demo` runs every demo. The
`workflow` recipe has the details: `mothersauce show workflow`.

## JSON OUTPUT

`list --json` prints an array of recipe cards with the fields `id`, `section`, `title`, `kind`, `summary`, `tags`,
`python`, `use_when`, `avoid_when`, `related`, `source_path`, `tests_path` and `run`. `show --json` prints one card
with `notes` and `source` added. `search --json` prints an array of objects with `id`, `title`, `summary` and `score`,
best first. `doctor --json` prints an array of checks with `check`, `ok`, `required` and `detail`.

## EXIT STATUS

0 on success. 1 when a search finds nothing, a required check fails, or `integrate` finds no harness or a step fails.
2 when the arguments are wrong, such as an unknown recipe, with the reason on standard error.

## ENVIRONMENT

| Variable | Effect |
| --- | --- |
| `XDG_DATA_HOME` | Where `man --install` writes: `$XDG_DATA_HOME/man/man1`. Default: `~/.local/share/man/man1`. |
| `CLAUDE_CONFIG_DIR` | The Claude Code folder `integrate` uses. Default: `~/.claude`. |
| `CODEX_HOME` | The Codex folder `integrate` uses. Default: `~/.codex`. |
| `XDG_CONFIG_HOME` | Where `integrate` looks for OpenCode. Default: `~/.config`. |

## FILES

`~/.local/share/man/man1/mothersauce.1` is the installed man page. `integrate` writes `SKILL.md` to
`skills/mothersauce/` for Claude Code and Codex and to `skill/mothersauce/` for OpenCode, and leaves a backup named
`*.mothersauce.bak` next to any configuration file it edits.

## EXAMPLES

Find and read the recipe for a problem:

```
mothersauce search retry a flaky api call
mothersauce show decorators --notes
```

Run the pipeline that uses every other recipe:

```
mothersauce run pipeline
```

Give every agent harness on this machine the server and the skill, after a dry run:

```
mothersauce integrate --dry-run
mothersauce integrate
```

Install the man page, then read it:

```
mothersauce man --install
man mothersauce
```

## SEE ALSO

The repository: https://github.com/jpsanders/mothersauce. The template it is built on:
https://github.com/jpsanders/python-package-template. The Model Context Protocol: https://modelcontextprotocol.io.

## AUTHOR

James Phillip Sanders, https://jamesphillipsanders.com
