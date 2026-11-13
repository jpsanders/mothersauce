# The menu

Every recipe, by section. Generated from `src/mothersauce/data/recipes.toml` by `make docs`; edit that file,
not this one. Read any recipe with `mothersauce show <id>` and run a code recipe with `mothersauce run <id>`.

## Mise en place

### The local and CI workflow

pyenv and pyenv-virtualenv, make targets, and CI that runs exactly what your machine runs.

- **Id:** `workflow`, practice; source [`src/mothersauce/data/practice/workflow.md`](src/mothersauce/data/practice/workflow.md)
- **Python:** `pyenv install 3.15.2`, `pyenv virtualenv`, `make checks`, `reusable workflows`, `tags without v`
- **Use it when:** Starting any Python repository; CI and local results disagree; Cutting a release
- **Avoid it when:** A single throwaway script, where a virtual environment is enough
- **Related:** `layout`, `style`, `testing`

### Code layout

The src layout: one package, one concept per module, tests that mirror it, data shipped inside.

- **Id:** `layout`, practice; source [`src/mothersauce/data/practice/layout.md`](src/mothersauce/data/practice/layout.md)
- **Python:** `src/ layout`, `__all__`, `py.typed`, `__main__.py`, `[project.scripts]`, `importlib.resources`
- **Use it when:** Laying out a new package; A module has grown past one idea
- **Avoid it when:** Splitting a 200 line module into ten files before it needs it
- **Related:** `workflow`, `style`, `cli`

### Code style

Nine checks that end style arguments: black, isort, flake8, darglint, mypy strict, bandit and more.

- **Id:** `style`, practice; source [`src/mothersauce/data/practice/style.md`](src/mothersauce/data/practice/style.md)
- **Python:** `black 120`, `mypy --strict`, `Sphinx docstrings`, `absolute imports`, `# nosec <code>  # reason`
- **Use it when:** Agreeing how code should look before the first review; Briefing an AI agent on house rules
- **Avoid it when:** Reformatting a whole legacy codebase in the same pull request as a fix
- **Related:** `workflow`, `layout`, `testing`

## Mother sauces

### Dataclasses

Small, honest value objects: frozen, slotted, validated, replaced rather than mutated.

- **Id:** `dataclasses`, code; source [`src/mothersauce/recipes/value_objects.py`](src/mothersauce/recipes/value_objects.py)
- **Tests:** [`tests/mothersauce/recipes/test_value_objects.py`](tests/mothersauce/recipes/test_value_objects.py)
- **Python:** `@dataclass(frozen, slots, kw_only, order)`, `field(init=False)`, `InitVar`, `copy.replace`, `ClassVar`
- **Use it when:** Data with a little behaviour; Values passed between your own functions; Keys and watermarks
- **Avoid it when:** Untrusted input from outside: parse it with pydantic first
- **Related:** `pydantic`, `oop`, `enums`

### Pydantic models

Parse, don't validate, at the edges: strict models, reusable constraints, discriminated unions.

- **Id:** `pydantic`, code; source [`src/mothersauce/recipes/models.py`](src/mothersauce/recipes/models.py)
- **Tests:** [`tests/mothersauce/recipes/test_models.py`](tests/mothersauce/recipes/test_models.py)
- **Python:** `BaseModel`, `ConfigDict(frozen, extra='forbid')`, `Annotated constraints`, `field_validator`, `model_validator`, `computed_field`, `Field(discriminator)`, `TypeAdapter`
- **Use it when:** Reading JSON, CSV, queues or requests; Publishing a data contract as JSON schema
- **Avoid it when:** Hot inner loops over data you already validated: use dataclasses there
- **Related:** `dataclasses`, `config`, `errors`

### Enums

Closed sets of names: StrEnum, IntEnum, Flag, a state machine, and exhaustive match with assert_never.

- **Id:** `enums`, code; source [`src/mothersauce/recipes/enums.py`](src/mothersauce/recipes/enums.py)
- **Tests:** [`tests/mothersauce/recipes/test_enums.py`](tests/mothersauce/recipes/test_enums.py)
- **Python:** `StrEnum`, `auto()`, `IntEnum`, `Flag`, `@unique`, `match`, `assert_never`, `frozendict`
- **Use it when:** A field takes one of a known set of values; Statuses that move through a lifecycle
- **Avoid it when:** Values that grow at run time, such as customer names
- **Related:** `dataclasses`, `data-quality`

### Abstractions: ABC and Protocol

ABCs for families you own, with a template method; Protocols for shapes you accept.

- **Id:** `abstractions`, code; source [`src/mothersauce/recipes/abstractions.py`](src/mothersauce/recipes/abstractions.py)
- **Tests:** [`tests/mothersauce/recipes/test_abstractions.py`](tests/mothersauce/recipes/test_abstractions.py)
- **Python:** `ABC`, `@abstractmethod`, `Protocol`, `@runtime_checkable`, `itertools.batched`, `type aliases`
- **Use it when:** Several implementations of one job; Code that should accept fakes in tests
- **Avoid it when:** One implementation with no second in sight: write the class, abstract later
- **Related:** `factories`, `generics`, `oop`

### Factories

Decide which class to build in one place: registries, __init_subclass__, from_ constructors, plugins.

- **Id:** `factories`, code; source [`src/mothersauce/recipes/factories.py`](src/mothersauce/recipes/factories.py)
- **Tests:** [`tests/mothersauce/recipes/test_factories.py`](tests/mothersauce/recipes/test_factories.py)
- **Python:** `__init_subclass__`, `decorator registry`, `@classmethod from_url`, `Self`, `frozendict`, `importlib.metadata.entry_points`
- **Use it when:** Choosing an implementation from configuration; Letting other packages add formats
- **Avoid it when:** Two cases that will never become three: an if is clearer
- **Related:** `abstractions`, `decorators`, `config`

### Generics

Write the container once and keep every type: PEP 695 syntax, bounds, defaults, ParamSpec, Result.

- **Id:** `generics`, code; source [`src/mothersauce/recipes/generics.py`](src/mothersauce/recipes/generics.py)
- **Tests:** [`tests/mothersauce/recipes/test_generics.py`](tests/mothersauce/recipes/test_generics.py)
- **Python:** `class Repository[K: Hashable, V]`, `def first[T]`, `[S: (str, bytes)]`, `[T, C = str]`, `[**P, R]`, `@overload`, `TypeIs`, `type Result[T, E = str]`
- **Use it when:** Containers, repositories and helpers used with many types; Typed decorators
- **Avoid it when:** A function that only ever takes one type
- **Related:** `abstractions`, `decorators`, `errors`

### Generators

Any size of input in the memory of one record: streams, stages, batches, windows, send, cursors.

- **Id:** `generators`, code; source [`src/mothersauce/recipes/generators.py`](src/mothersauce/recipes/generators.py)
- **Tests:** [`tests/mothersauce/recipes/test_generators.py`](tests/mothersauce/recipes/test_generators.py)
- **Python:** `yield`, `yield from`, `Generator[T]`, `itertools.batched`, `groupby`, `deque(maxlen)`, `send()`, `(*group for group in groups)`, `__iter__ / __next__`
- **Use it when:** Reading files, APIs or queries too big for memory; Pipelines of small stages
- **Avoid it when:** You need random access or several passes: build a list
- **Related:** `context-managers`, `concurrency`, `pipeline`

### Context managers

Every acquire paired with its release: timers, atomic writes, nested transactions, ExitStack.

- **Id:** `context-managers`, code; source [`src/mothersauce/recipes/context_managers.py`](src/mothersauce/recipes/context_managers.py)
- **Tests:** [`tests/mothersauce/recipes/test_context_managers.py`](tests/mothersauce/recipes/test_context_managers.py)
- **Python:** `@contextmanager`, `__enter__ / __exit__`, `Literal[False]`, `ExitStack`, `suppress`, `chdir`, `os.replace`
- **Use it when:** Anything that must be closed, released, committed or restored; Temporary state in tests
- **Avoid it when:** Cleanup that does not exist: a with block that does nothing is noise
- **Related:** `errors`, `sql`, `generators`

### Decorators

Cross cutting behaviour written once: typed retry with backoff and jitter, caches, singledispatch.

- **Id:** `decorators`, code; source [`src/mothersauce/recipes/decorators.py`](src/mothersauce/recipes/decorators.py)
- **Tests:** [`tests/mothersauce/recipes/test_decorators.py`](tests/mothersauce/recipes/test_decorators.py)
- **Python:** `functools.wraps`, `[**P, R]`, `retry with full jitter`, `cache`, `lru_cache`, `cached_property`, `singledispatch`, `warnings.deprecated`
- **Use it when:** The same wrapper logic on many functions; Retrying transient network errors
- **Avoid it when:** Logic specific to one function: put it in the function
- **Related:** `generics`, `errors`, `performance`

### Object oriented design

Composition over inheritance, dunder protocols, properties, descriptors and __slots__.

- **Id:** `oop`, code; source [`src/mothersauce/recipes/oop.py`](src/mothersauce/recipes/oop.py)
- **Tests:** [`tests/mothersauce/recipes/test_oop.py`](tests/mothersauce/recipes/test_oop.py)
- **Python:** `__set_name__`, `@property`, `__eq__ and __hash__`, `__len__ / __iter__ / __contains__`, `@total_ordering`, `__slots__`, `@classmethod`, `@staticmethod`
- **Use it when:** Objects with state and rules; Classes that should feel like built in types
- **Avoid it when:** Plain data: a dataclass says it in fewer lines
- **Related:** `dataclasses`, `abstractions`, `data-structures`

### Data structures

The container that makes the code obvious: Counter, deque, heapq, bisect, ChainMap, graphlib.

- **Id:** `data-structures`, code; source [`src/mothersauce/recipes/data_structures.py`](src/mothersauce/recipes/data_structures.py)
- **Tests:** [`tests/mothersauce/recipes/test_data_structures.py`](tests/mothersauce/recipes/test_data_structures.py)
- **Python:** `defaultdict`, `Counter`, `OrderedDict`, `ChainMap`, `heapq.merge`, `bisect`, `frozendict`, `NamedTuple`, `TypedDict(closed=True)`, `graphlib.TopologicalSorter`
- **Use it when:** Grouping, counting, ranking, merging or scheduling; A list doing a set's job
- **Avoid it when:** Reaching for a library before checking collections, heapq and graphlib
- **Related:** `generators`, `performance`, `oop`

### Errors

A hierarchy you can catch, chains you can follow, and batches that report every failure at once.

- **Id:** `errors`, code; source [`src/mothersauce/recipes/errors.py`](src/mothersauce/recipes/errors.py)
- **Tests:** [`tests/mothersauce/recipes/test_errors.py`](tests/mothersauce/recipes/test_errors.py)
- **Python:** `class KitchenError(Exception)`, `raise ... from error`, `add_note`, `ExceptionGroup`, `except*`, `except ValueError, TypeError:`
- **Use it when:** A package other code depends on; Batch jobs where one bad record must not stop the rest
- **Avoid it when:** Exceptions for normal control flow in hot loops
- **Related:** `data-quality`, `logging`, `context-managers`

## On the line

### SQL loading

Injection proof queries with t-strings, schema evolution, idempotent upserts and high watermarks.

- **Id:** `sql`, code; source [`src/mothersauce/recipes/sql.py`](src/mothersauce/recipes/sql.py)
- **Tests:** [`tests/mothersauce/recipes/test_sql.py`](tests/mothersauce/recipes/test_sql.py)
- **Python:** `t"..."`, `string.templatelib`, `{table:id}`, `ON CONFLICT DO UPDATE`, `executemany`, `PRAGMA table_info`
- **Use it when:** Loading records into a database; Any SQL that includes a value from outside
- **Avoid it when:** Building SQL with f-strings, ever
- **Related:** `context-managers`, `pipeline`, `data-quality`

### Data quality

Rules as data, severities, quarantine, and overrides with an audit trail.

- **Id:** `data-quality`, code; source [`src/mothersauce/recipes/quality.py`](src/mothersauce/recipes/quality.py)
- **Tests:** [`tests/mothersauce/recipes/test_quality.py`](tests/mothersauce/recipes/test_quality.py)
- **Python:** `decorator registry`, `frozen dataclasses`, `IntEnum severity`, `Counter`, `except A, B, C:`
- **Use it when:** Loads where some bad rows are expected; Known exceptions that need an approver
- **Avoid it when:** Structural parsing, which belongs in a pydantic model
- **Related:** `pipeline`, `pydantic`, `enums`

### The pipeline

Every recipe plated together: a small, real ETL with quality rules, upserts, watermarks and JSON logs.

- **Id:** `pipeline`, code; source [`src/mothersauce/recipes/pipeline.py`](src/mothersauce/recipes/pipeline.py)
- **Tests:** [`tests/mothersauce/recipes/test_pipeline.py`](tests/mothersauce/recipes/test_pipeline.py)
- **Python:** `make_source`, `check_batch`, `FeedLine model`, `upsert`, `Watermark`, `log_context`, `Summary`
- **Use it when:** Seeing how the recipes compose in one place; Starting an ingestion job
- **Avoid it when:** Copying it whole: take the parts your job needs
- **Related:** `sql`, `data-quality`, `generators`

## Service

### Structured logging

JSON lines with a run id from a ContextVar, secrets redacted, configured once with dictConfig.

- **Id:** `logging`, code; source [`src/mothersauce/recipes/logs.py`](src/mothersauce/recipes/logs.py)
- **Tests:** [`tests/mothersauce/recipes/test_logs.py`](tests/mothersauce/recipes/test_logs.py)
- **Python:** `logging.getLogger(__name__)`, `logging.Filter`, `logging.Formatter`, `ContextVar`, `dictConfig`, `extra=`
- **Use it when:** Any program that runs without a person watching; Logs that a machine will search
- **Avoid it when:** print() in library code
- **Related:** `errors`, `config`, `pipeline`

### Configuration

One frozen settings object from defaults, TOML, environment and flags, with where each value came from.

- **Id:** `config`, code; source [`src/mothersauce/recipes/config.py`](src/mothersauce/recipes/config.py)
- **Tests:** [`tests/mothersauce/recipes/test_config.py`](tests/mothersauce/recipes/test_config.py)
- **Python:** `tomllib`, `pydantic BaseModel`, `SecretStr`, `sentinel()`, `int | UNSET`, `deep merge`
- **Use it when:** Programs configured from more than one place; Settings that must fail fast when wrong
- **Avoid it when:** Reading os.environ deep inside business logic
- **Related:** `pydantic`, `logging`, `cli`

### Concurrency

Wait for many slow things at once, bounded, in order, without losing a single error.

- **Id:** `concurrency`, code; source [`src/mothersauce/recipes/concurrency.py`](src/mothersauce/recipes/concurrency.py)
- **Tests:** [`tests/mothersauce/recipes/test_concurrency.py`](tests/mothersauce/recipes/test_concurrency.py)
- **Python:** `ThreadPoolExecutor`, `wait(FIRST_COMPLETED)`, `asyncio.TaskGroup`, `asyncio.Semaphore`, `asyncio.timeout`, `queue.Queue`, `sentinel()`
- **Use it when:** Many network or database calls; A dispatcher feeding workers
- **Avoid it when:** CPU bound work on the default build: use processes, or the free threaded build
- **Related:** `generators`, `errors`, `performance`

### Performance

Measure first, then make the common path cheap: lazy imports, timeit, import costs.

- **Id:** `performance`, code; source [`src/mothersauce/recipes/performance.py`](src/mothersauce/recipes/performance.py)
- **Tests:** [`tests/mothersauce/recipes/test_performance.py`](tests/mothersauce/recipes/test_performance.py)
- **Python:** `lazy import`, `timeit.Timer`, `python -X importtime`, `python -m profiling.sampling`, `str.join`
- **Use it when:** A command line tool that should start instantly; Deciding between two ways with numbers
- **Avoid it when:** Optimising code you have not measured
- **Related:** `data-structures`, `generators`, `cli`

### Command line interface

This package's own CLI: subcommands, --json on everything, real exit codes, a man page, lazy imports.

- **Id:** `cli`, code; source [`src/mothersauce/cli.py`](src/mothersauce/cli.py)
- **Tests:** [`tests/mothersauce/test_cli.py`](tests/mothersauce/test_cli.py)
- **Python:** `argparse subparsers`, `lazy import`, `--json`, `importlib.resources`, `sys.exit(main())`
- **Use it when:** Any tool people or agents run from a shell
- **Avoid it when:** Interactive prompts in a tool that scripts and agents will call
- **Related:** `mcp-server`, `layout`, `performance`

### An MCP server with no dependencies

This package's own MCP server: JSON-RPC over stdio with tools, resources and prompts.

- **Id:** `mcp-server`, code; source [`src/mothersauce/mcp.py`](src/mothersauce/mcp.py)
- **Tests:** [`tests/mothersauce/test_mcp.py`](tests/mothersauce/test_mcp.py)
- **Python:** `json`, `sys.stdin lines`, `dispatch dict`, `TypedDict`, `read only tool annotations`
- **Use it when:** Giving AI agents your tool's data and actions; A server that must start in milliseconds
- **Avoid it when:** Streaming or authenticated remote servers: use the official SDK there
- **Related:** `cli`, `abstractions`, `errors`

## The pass

### Testing with pytest

Fixtures, parametrize, fakes over mocks, doctests and a coverage gate: nothing broken leaves the pass.

- **Id:** `testing`, practice; source [`src/mothersauce/data/practice/testing.md`](src/mothersauce/data/practice/testing.md)
- **Python:** `@pytest.fixture`, `@pytest.mark.parametrize`, `tmp_path`, `monkeypatch`, `capsys`, `--doctest-modules`, `fail_under`
- **Use it when:** Every change; Pinning a bug before fixing it
- **Avoid it when:** Asserting on log text or timing that varies between machines
- **Related:** `bdd`, `style`, `workflow`

### Behaviour driven tests

Gherkin features run by pytest-bdd: behaviour written so a person can read it and pytest can run it.

- **Id:** `bdd`, practice; source [`src/mothersauce/data/practice/bdd.md`](src/mothersauce/data/practice/bdd.md)
- **Python:** `Feature / Scenario`, `Given / When / Then`, `scenarios()`, `target_fixture`, `parsers.parse`, `Scenario Outline`
- **Use it when:** Acceptance tests a product owner should be able to read; End to end behaviour of a job
- **Avoid it when:** Unit tests of one function: plain pytest says it shorter
- **Related:** `testing`, `pipeline`, `cli`
