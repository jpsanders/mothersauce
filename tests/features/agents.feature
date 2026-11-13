Feature: Serving the recipes to an AI agent
  An agent harness starts the server, discovers what it offers, and reads recipes without changing anything.

  Background:
    Given the MCP server has started

  Scenario: The agent discovers read only tools
    When the agent lists the tools
    Then it sees list_recipes, search_recipes, get_recipe and get_style_guide
    And every tool is marked read only

  Scenario: The agent finds and reads a recipe
    When the agent searches for "retry a flaky api call"
    Then the best match is decorators
    When the agent reads the recipe decorators
    Then the text contains "def retry"

  Scenario: A wrong recipe name is an error the agent can read
    When the agent reads the recipe generater
    Then the result is an error that suggests generators
