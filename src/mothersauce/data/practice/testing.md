# Testing with pytest

Every recipe in this package has a test file next to its mirror path, and every test runs on every push. The patterns
below are all in use in `tests/`.

## Fixtures for setup, with cleanup after `yield`

```python
@pytest.fixture
def conn() -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(":memory:", autocommit=True)
    yield connection
    connection.close()
```

A fixture is a context manager pytest drives: setup before `yield`, teardown after, run even when the test fails.
pytest's own fixtures cover most needs: `tmp_path` for files, `monkeypatch` for the environment and attributes,
`capsys` for output, `caplog` for logs.

## Tables of cases with parametrize

```python
@pytest.mark.parametrize(("price", "band"), [("9.99", "snack"), ("10", "starter"), ("30", "special")])
def test_price_band_boundaries(price: str, band: str) -> None:
    assert price_band(Decimal(price)) == band
```

Boundaries are where bugs live, so put them in the table: the last value of one band and the first of the next.

## Fakes over mocks

A fake is a small working implementation, such as `ListSink` for a sink or `Flaky` for a supplier that fails twice and
then answers. It fits the Protocol the code depends on, so the test exercises real calls instead of asserting which
methods a mock saw. Use `monkeypatch` for the few places a fake cannot reach, such as `entry_points`.

## Doctests keep the documentation honest

Examples in docstrings run as tests, because `pytest` runs with `--doctest-modules` over `src/`. An example that
drifts from the code fails the build.

## The gates

- `--strict-markers` turns a typo in a marker name into an error, and `xfail_strict` fails an expected failure that
  starts passing.
- Coverage has a floor: `fail_under = 95` with branch coverage. It catches code paths nobody runs, not ideas nobody
  tested, so it is a floor, never a goal.
- mypy checks the tests in strict mode too: a test that calls a function wrongly is a bug in the test.

## Naming

Name a test for the behaviour it pins, as a sentence: `test_second_run_loads_nothing_new`,
`test_retry_does_not_retry_other_errors`. When it fails, the name alone says what broke.
