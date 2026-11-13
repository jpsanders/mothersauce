# House style

The rules a reviewer would otherwise repeat, in one place. Nine checks enforce most of them (`make checks`); the rest
are the habits the recipes show.

## Enforced by the checks

- **Formatting:** black at 120 columns, imports sorted by isort with the black profile. Nobody formats by hand.
- **Types:** mypy in strict mode, on the tests too. Every function has full hints; `Any` needs a reason; an ignore
  names its code, `# type: ignore[misc]`, and an unused one fails the build.
- **Docstrings:** Sphinx style, `:param name:`, `:returns:`, `:yields:` for generators, `:raises Error:`, checked
  against the signature by darglint. The first line is an imperative sentence: "Return the total", not "Returns".
- **Imports:** absolute only (`from mothersauce.recipes import sql`); relative imports fail flake8.
- **Security:** bandit on every push. A justified exception reads `# nosec B603  # fixed arguments, never a shell`.
- **Files:** editorconfig: spaces, Unix line endings, a final newline, and 120 columns in every file type.

## Habits the recipes show

- **Parse at the edge.** Untrusted input becomes a pydantic model at the boundary, with `extra="forbid"`. Inside,
  pass typed objects: frozen dataclasses for values, enums for closed sets.
- **Small objects, composed.** Composition over inheritance; an ABC only for a family you own, a `Protocol` for what
  you accept. A factory decides which class to build, in one place.
- **Stream, do not load.** Generators for anything read from outside; `itertools.batched` for bulk writes.
- **Pair every acquire with a release.** Files, transactions, locks and temporary state live in `with` blocks.
- **Errors are part of the API.** One base exception per package, `raise ... from error` to keep the cause,
  `add_note` for context, and an `ExceptionGroup` when a batch has many failures. Never a bare `except:`.
- **Log, do not print.** `logger = logging.getLogger(__name__)`, values as arguments (`logger.info("loaded %d", n)`),
  configuration once at the entry point, JSON lines for machines.
- **Configuration once.** Defaults, a TOML file, the environment and flags, merged and validated at start up into one
  frozen object. Nothing reads `os.environ` deep in the code.
- **SQL from template strings.** Values are always parameters; names pass through a checked `{name:id}` spec.
- **Bound concurrency.** A limit on workers and on work in flight, and every error kept.
- **Measure before optimising.** `timeit`, `python -X importtime`, `python -m profiling.sampling`. Heavy imports are
  lazy, so a command starts in milliseconds.

## Naming

- Modules, functions and variables in `snake_case`; classes in `PascalCase`; constants in `UPPER_CASE`.
- Name things for what they are in the domain (`ticket`, `watermark`), never for their type (`data`, `obj`, `lst`).
- A function that returns a bool reads as a question: `is_safe`, `can_become`, `has_override`.
- A leading underscore marks module private helpers; `__all__` lists the public names.

## Tests

- pytest, with fixtures for setup and `parametrize` for tables of cases. Prefer a small fake to a mock.
- One behaviour per test, named as a sentence: `test_second_run_loads_nothing_new`.
- Acceptance behaviour in Gherkin, run by pytest-bdd; unit behaviour in plain pytest.
- Examples in docstrings run as doctests, so documentation cannot drift from the code.
- Coverage is a floor (95%), not a goal: the gate catches untested code paths, not untested ideas.
