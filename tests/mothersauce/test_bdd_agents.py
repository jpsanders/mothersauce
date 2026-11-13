from typing import Any

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from mothersauce.mcp import Server

scenarios("agents.feature")


@pytest.fixture
def session() -> dict[str, Any]:
    """
    Hold the conversation so far: the server and its last answer.

    :returns: A dict the steps fill in
    """
    return {"ids": 0}


def ask(session: dict[str, Any], method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    session["ids"] += 1
    reply = session["server"].handle({"jsonrpc": "2.0", "id": session["ids"], "method": method, "params": params})
    assert reply is not None
    answer: dict[str, Any] = reply["result"]
    session["last"] = answer
    return answer


@given("the MCP server has started")
def server_started(session: dict[str, Any]) -> None:
    session["server"] = Server()
    assert ask(session, "initialize", {"protocolVersion": "2025-11-25"})["serverInfo"]["name"] == "mothersauce"


@when("the agent lists the tools")
def list_tools(session: dict[str, Any]) -> None:
    session["tools"] = ask(session, "tools/list")["tools"]


@then(parsers.parse("it sees {names}"))
def sees_tools(session: dict[str, Any], names: str) -> None:
    expected = [n.strip() for n in names.replace(" and ", ", ").split(",")]
    assert [tool["name"] for tool in session["tools"]] == expected


@then("every tool is marked read only")
def read_only(session: dict[str, Any]) -> None:
    assert all(tool["annotations"]["readOnlyHint"] for tool in session["tools"])


@when(parsers.parse('the agent searches for "{query}"'))
def search(session: dict[str, Any], query: str) -> None:
    ask(session, "tools/call", {"name": "search_recipes", "arguments": {"query": query}})


@then(parsers.parse("the best match is {recipe}"))
def best_match(session: dict[str, Any], recipe: str) -> None:
    assert session["last"]["structuredContent"]["results"][0]["id"] == recipe


@when(parsers.parse("the agent reads the recipe {recipe}"))
def read_recipe(session: dict[str, Any], recipe: str) -> None:
    ask(session, "tools/call", {"name": "get_recipe", "arguments": {"id": recipe}})


@then(parsers.parse('the text contains "{text}"'))
def text_contains(session: dict[str, Any], text: str) -> None:
    assert text in session["last"]["content"][0]["text"]


@then(parsers.parse("the result is an error that suggests {recipe}"))
def error_suggests(session: dict[str, Any], recipe: str) -> None:
    assert session["last"]["isError"] is True
    assert f"did you mean {recipe}" in session["last"]["content"][0]["text"]
