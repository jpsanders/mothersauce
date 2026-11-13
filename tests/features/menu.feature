Feature: Finding a recipe from the command line
  A cook with a problem asks the menu in plain words and gets the recipe to follow.

  Scenario Outline: Searching finds the right recipe first
    When I run mothersauce search "<question>"
    Then the first recipe is <recipe>

    Examples:
      | question               | recipe       |
      | retry a flaky api call | decorators   |
      | stream a huge csv file | generators   |
      | immutable value object | dataclasses  |
      | safe sql query         | sql          |
      | duplicate rows         | data-quality |
      | pyenv virtualenv       | workflow     |

  Scenario: Reading a recipe shows its tested source
    When I run mothersauce show context-managers
    Then the exit status is 0
    And the output starts with "# Context managers"
    And the output contains "class Transaction"

  Scenario: A misspelt recipe gets a suggestion
    When I run mothersauce show generater
    Then the exit status is 2
    And the error suggests "generators"

  Scenario: Tasting the pipeline runs it twice
    When I run mothersauce run pipeline
    Then the exit status is 0
    And the output contains "run-2: read 16, loaded 0, already loaded 12"
