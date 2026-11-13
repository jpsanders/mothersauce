import io
import json
from typing import Any

import pytest

from mothersauce.mcp import PROTOCOL_VERSIONS, Server, demo, serve, style_guide

SERVER = Server()


def call(method: str, params: dict[str, Any] | None = None, mid: int = 1) -> dict[str, Any]:
    reply = SERVER.handle({"jsonrpc": "2.0", "id": mid, "method": method, "params": params or {}})
    assert reply is not None and reply["id"] == mid
    return reply


def tool(name: str, **arguments: Any) -> dict[str, Any]:
    result: dict[str, Any] = call("tools/call", {"name": name, "arguments": arguments})["result"]
    return result


@pytest.mark.parametrize(("asked", "agreed"), [("2025-06-18", "2025-06-18"), ("1999-01-01", PROTOCOL_VERSIONS[0])])
def test_initialize_negotiates_the_protocol(asked: str, agreed: str) -> None:
    result = call("initialize", {"protocolVersion": asked})["result"]
    assert result["protocolVersion"] == agreed
    assert result["serverInfo"]["name"] == "mothersauce"
    assert set(result["capabilities"]) == {"tools", "resources", "prompts"}
    assert "search_recipes" in result["instructions"]


def test_ping_and_notifications() -> None:
    assert call("ping")["result"] == {}
    assert SERVER.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None


def test_tools_are_listed_read_only_with_schemas() -> None:
    tools = {t["name"]: t for t in call("tools/list")["result"]["tools"]}
    assert set(tools) == {"list_recipes", "search_recipes", "get_recipe", "get_style_guide"}
    assert tools["search_recipes"]["inputSchema"]["required"] == ["query"]
    assert tools["get_recipe"]["inputSchema"]["required"] == ["id"]
    assert all(t["annotations"]["readOnlyHint"] and not t["annotations"]["destructiveHint"] for t in tools.values())


def test_search_recipes_tool() -> None:
    result = tool("search_recipes", query="retry a flaky api call", limit=3)
    assert result["isError"] is False
    assert result["structuredContent"]["results"][0]["id"] == "decorators"
    assert json.loads(result["content"][0]["text"])[0]["id"] == "decorators"


def test_get_recipe_tool_parts() -> None:
    assert tool("get_recipe", id="generators")["content"][0]["text"].startswith("# Generators")
    assert tool("get_recipe", id="generators", part="code")["content"][0]["text"].startswith("```python")


def test_list_recipes_tool_filters() -> None:
    cards = tool("list_recipes", kind="practice")["structuredContent"]["recipes"]
    assert [c["id"] for c in cards] == ["workflow", "layout", "style", "testing", "bdd"]
    assert len(tool("list_recipes")["structuredContent"]["recipes"]) == 26


def test_style_guide_tool() -> None:
    assert tool("get_style_guide")["content"][0]["text"] == style_guide()


@pytest.mark.parametrize(
    ("name", "arguments", "message"),
    [
        ("get_recipe", {"id": "nope"}, "no recipe 'nope'"),
        ("get_recipe", {"id": "sql", "part": "dessert"}, "part must be"),
        ("search_recipes", {"query": "  "}, "query is required"),
    ],
)
def test_tool_errors_are_results_not_crashes(name: str, arguments: dict[str, Any], message: str) -> None:
    result = tool(name, **arguments)
    assert result["isError"] is True and message in result["content"][0]["text"]


def test_unknown_tool_and_method() -> None:
    assert call("tools/call", {"name": "make_coffee"})["error"]["code"] == -32602
    assert call("sampling/createMessage")["error"]["code"] == -32601


def test_resources() -> None:
    listed = call("resources/list")["result"]["resources"]
    assert len(listed) == 27 and listed[-1]["uri"] == "mothersauce://style"
    assert call("resources/templates/list")["result"]["resourceTemplates"][0]["uriTemplate"].endswith("{id}")
    text = call("resources/read", {"uri": "mothersauce://recipes/sql"})["result"]["contents"][0]["text"]
    assert text.startswith("# SQL loading")
    style = call("resources/read", {"uri": "mothersauce://style"})["result"]["contents"][0]
    assert style["mimeType"] == "text/markdown"
    assert call("resources/read", {"uri": "https://example.com"})["error"]["code"] == -32602


def test_prompts() -> None:
    prompts = {p["name"]: p for p in call("prompts/list")["result"]["prompts"]}
    assert set(prompts) == {"apply_recipe", "review_python"}
    applied = call("prompts/get", {"name": "apply_recipe", "arguments": {"recipe": "sql", "task": "load orders"}})
    text = applied["result"]["messages"][0]["content"]["text"]
    assert text.startswith("Task: load orders") and "# SQL loading" in text and "# House style" in text
    review = call("prompts/get", {"name": "review_python", "arguments": {"code": "print(1)"}})
    assert "print(1)" in review["result"]["messages"][0]["content"]["text"]
    assert call("prompts/get", {"name": "nope"})["error"]["code"] == -32601


def test_serve_reads_lines_and_answers_lines() -> None:
    stdin = io.StringIO(
        "\n".join(
            [
                '{"jsonrpc": "2.0", "id": 1, "method": "ping"}',
                "",
                "not json",
                '{"jsonrpc": "2.0", "method": "notifications/initialized"}',
                '[{"jsonrpc": "2.0", "id": 2, "method": "ping"}, {"jsonrpc": "2.0", "id": 3, "method": "ping"}]',
            ]
        )
        + "\n"
    )
    stdout = io.StringIO()
    serve(stdin, stdout)
    replies = [json.loads(line) for line in stdout.getvalue().splitlines()]
    assert replies[0]["result"] == {}
    assert replies[1]["error"]["code"] == -32700
    assert [r["id"] for r in replies[2]] == [2, 3]
    assert len(replies) == 3


def test_demo_runs(capsys: pytest.CaptureFixture[str]) -> None:
    demo()
    out = capsys.readouterr().out
    assert "<- list_recipes, search_recipes, get_recipe, get_style_guide" in out
    assert "<- # Generators" in out
