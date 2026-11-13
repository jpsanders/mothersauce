---
name: mothersauce
description: Production Python patterns as typed, tested reference recipes. Use when writing, refactoring or reviewing Python; when choosing between a dataclass and a pydantic model, an ABC and a Protocol, or threads and asyncio; when code needs a factory, generics, a generator pipeline, a context manager, a retry decorator, structured logging, layered configuration, safe SQL, data quality rules or an ETL step; or when setting up a package's layout, style, pytest and BDD tests, pyenv and CI.
---

# mothersauce

mothersauce holds 26 reference recipes for production Python 3.15. Each code recipe is one small module with full
type hints, Sphinx docstrings, a runnable demo and its own tests. Use them as the shape of the code you write.

## Looking things up

When the mothersauce MCP server is connected, use its tools: `search_recipes` with the problem in a few words, then
`get_recipe` with the best id, and `get_style_guide` for the house rules. Otherwise use the command line; every
command that prints data takes `--json`:

```sh
mothersauce search "retry a flaky api call"   # ranked recipes for a problem
mothersauce show decorators                   # when to use it, when not, and the full tested source
mothersauce show decorators --notes           # the card and the explanation only
mothersauce run decorators                    # run its demo
mothersauce style                             # the house style
mothersauce list                              # the whole menu
```

## Which recipe

| The problem | Recipe |
| --- | --- |
| Untrusted JSON, CSV or queue messages | `pydantic` |
| Values passed around inside the program | `dataclasses` |
| A field with a fixed set of values, or a status lifecycle | `enums` |
| Several implementations of one job, or code that must accept fakes | `abstractions` |
| Choosing an implementation from configuration, or plugins | `factories` |
| A container or helper used with many types, or typed decorators | `generics` |
| Files or APIs too big for memory, batching, pagination | `generators` |
| Anything that must be closed, committed or restored | `context-managers` |
| Retries, caching, dispatch by type, deprecations | `decorators` |
| Error hierarchies, or batches that must report every failure | `errors` |
| Grouping, ranking, merging, LRU caches, ordering tasks | `data-structures` |
| Classes with rules: properties, descriptors, dunder methods | `oop` |
| Loading into a database, or any SQL with outside values | `sql` |
| Expected bad rows, quarantine and approved exceptions | `data-quality` |
| An end to end ingestion job | `pipeline` |
| Logs a machine will search | `logging` |
| Settings from files, the environment and flags | `config` |
| Many network or database calls at once | `concurrency` |
| Slow start up or a hot loop | `performance` |
| A command line tool | `cli` |
| Giving agents a tool's data | `mcp-server` |
| Package layout, style, tests, BDD, pyenv and CI | `layout`, `style`, `testing`, `bdd`, `workflow` |

## Rules

- Copy the shape of a recipe, not its names: the recipes use a restaurant's ticket feed as their example domain.
- Follow the house style (`mothersauce style`): strict typing, Sphinx docstrings, absolute imports, no print in
  library code, untrusted input parsed at the edge, every acquire in a `with` block.
- A few recipes use Python 3.15 features. On an older Python keep the pattern and swap the feature: `lazy import`
  for a normal import, `frozendict` for a `MappingProxyType`, `sentinel()` for an `object()`, unpacking in a
  comprehension for `itertools.chain.from_iterable`, and a closed `TypedDict` for `typing_extensions.TypedDict`.
