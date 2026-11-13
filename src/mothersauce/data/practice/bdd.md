# Behaviour driven tests with pytest-bdd

Behaviour driven development writes acceptance tests in Gherkin, plain sentences a product owner can read and
correct, and binds each sentence to a step function. pytest-bdd runs them as ordinary pytest tests, so they share the
fixtures, the reports and the coverage gate with every other test.

## A feature

```gherkin
Feature: Loading the ticket feed
  The kitchen's tickets reach the database once, bad lines are held back, and a second run loads nothing new.

  Scenario: The first run loads the good lines
    Given the sample ticket feed
    And the staff meal is approved by the head chef
    When the pipeline runs
    Then 12 lines are loaded
    And 3 lines are quarantined
```

Features live in `tests/features/`. Write them in the language of the business: tickets, lines, the head chef. Never
the language of the code: no table names, no function names.

## Step definitions

```python
scenarios("pipeline.feature")


@given("the sample ticket feed", target_fixture="feed")
def sample_feed() -> str:
    return sample_path().as_uri().replace("file:", "csv:", 1)


@then(parsers.parse("{count:d} lines are loaded"))
def lines_loaded(summary: Summary, count: int) -> None:
    assert summary.loaded == count
```

`scenarios()` turns every scenario in the file into a test. `target_fixture` makes a step's return value a fixture
that later steps ask for by name, which is how state flows from Given to When to Then. `parsers.parse` reads values
out of the sentence, so one step serves every number.

## Scenario outlines

```gherkin
  Scenario Outline: Searching finds the right recipe
    When I search for "<question>"
    Then the first result is <recipe>

    Examples:
      | question                 | recipe           |
      | retry a flaky api call   | decorators       |
      | stream a huge csv file   | generators       |
```

One scenario, a table of examples: each row runs as its own test.

## When to use it

Use Gherkin for behaviour someone outside the code cares about: what a job loads, what a command prints, what an
agent can ask the server. Use plain pytest for everything else. A unit test written in Gherkin is three times longer
and no clearer.
