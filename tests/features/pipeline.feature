Feature: Loading the ticket feed
  The kitchen's tickets reach the database once. Lines that break a rule are held back for a person to look at, an
  approved exception goes through with its approver on record, and a second run loads nothing new.

  Background:
    Given the sample ticket feed
    And an empty database

  Scenario: The first run loads the good lines
    Given the staff meal is approved by the head chef
    When the pipeline runs
    Then 12 lines are loaded
    And 3 lines are quarantined
    And 1 line is invalid

  Scenario: A second run loads nothing new
    Given the staff meal is approved by the head chef
    When the pipeline runs
    And the pipeline runs again
    Then 0 lines are loaded
    And 12 lines are skipped as already loaded

  Scenario: Without approval the staff meal is held back
    When the pipeline runs
    Then 11 lines are loaded
    And 4 lines are quarantined
