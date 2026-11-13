"""
A Model Context Protocol server for coding agents, with no dependencies.

MCP is JSON-RPC 2.0, and over stdio each message is one line of JSON: read a line, answer a line. That is the whole
transport, so a useful server fits in one module of the standard library and starts in milliseconds, which matters
because an agent harness starts it for every session.

This server is read only. It offers the recipes three ways: as tools an agent calls (list, search, read, the style
guide), as resources it can attach to a conversation, and as prompts that apply a recipe to a task or review code
against the house style. Every tool is marked read only, so harnesses can let agents call them without asking.
"""

import json
import sys
from collections.abc import Callable
from importlib import resources
from typing import Any, TextIO

from mothersauce import catalogue

__all__ = ["PROTOCOL_VERSIONS", "Server", "serve", "style_guide"]

PROTOCOL_VERSIONS = ("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")
INSTRUCTIONS = (
    "mothersauce serves typed, tested reference recipes for production Python. Before writing or reviewing Python, "
    "call search_recipes with the problem in a few words, then get_recipe for the best match, and follow its shape "
    "and the house style from get_style_guide. Copy the shape, not the kitchen names."
)
READ_ONLY = {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False}
URI = "mothersauce://recipes/"

type Json = dict[str, Any]


def style_guide() -> str:
    """
    Read the house style that ships with the package.

    :returns: The style guide as Markdown
    """
    return (resources.files("mothersauce") / "data" / "practice" / "style.md").read_text(encoding="utf-8")


def _text(body: str, structured: Json | None = None) -> Json:
    result: Json = {"content": [{"type": "text", "text": body}], "isError": False}
    if structured is not None:
        result["structuredContent"] = structured
    return result


def _list_recipes(args: Json) -> Json:
    found = [
        r.as_dict()
        for r in catalogue.recipes()
        if args.get("section") in (None, r.section) and args.get("kind") in (None, r.kind)
    ]
    return _text(json.dumps(found, indent=1), {"recipes": found})


def _search_recipes(args: Json) -> Json:
    query = str(args.get("query", "")).strip()
    if not query:
        raise ValueError("query is required")
    hits = [
        {"id": r.id, "title": r.title, "summary": r.summary, "score": score}
        for r, score in catalogue.search(query, int(args.get("limit", 5)))
    ]
    return _text(json.dumps(hits, indent=1), {"results": hits})


def _get_recipe(args: Json) -> Json:
    recipe = catalogue.get(str(args.get("id", "")))
    part = args.get("part", "all")
    if part not in ("all", "notes", "code"):
        raise ValueError("part must be all, notes or code")
    return _text(recipe.markdown(part))


def _get_style_guide(args: Json) -> Json:
    return _text(style_guide())


TOOLS: dict[str, tuple[Callable[[Json], Json], str, Json]] = {
    "list_recipes": (
        _list_recipes,
        "List every recipe with its section, summary, tags and the Python features it shows.",
        {
            "section": {"type": "string", "enum": list(catalogue.SECTIONS)},
            "kind": {"type": "string", "enum": ["code", "practice"]},
        },
    ),
    "search_recipes": (
        _search_recipes,
        "Find the recipes for a problem described in a few words, such as 'retry a flaky api call'.",
        {"query": {"type": "string"}, "limit": {"type": "integer", "minimum": 1, "maximum": 30, "default": 5}},
    ),
    "get_recipe": (
        _get_recipe,
        "Read one recipe as Markdown: when to use it, when not to, and its complete, tested source.",
        {"id": {"type": "string"}, "part": {"type": "string", "enum": ["all", "notes", "code"], "default": "all"}},
    ),
    "get_style_guide": (
        _get_style_guide,
        "Read the house style: layout, naming, typing, docstrings, errors, logging and tests.",
        {},
    ),
}
REQUIRED = {"search_recipes": ["query"], "get_recipe": ["id"]}

PROMPTS: dict[str, tuple[str, list[Json]]] = {
    "apply_recipe": (
        "Write code for a task following one recipe and the house style.",
        [
            {"name": "recipe", "description": "A recipe id, such as context-managers", "required": True},
            {"name": "task", "description": "What the code should do", "required": True},
        ],
    ),
    "review_python": (
        "Review Python code against the recipes and the house style.",
        [{"name": "code", "description": "The code to review", "required": True}],
    ),
}


def _prompt(name: str, args: Json) -> Json:
    if name == "apply_recipe":
        recipe = catalogue.get(str(args.get("recipe", "")))
        text = (
            f"Task: {args.get('task', '')}\n\nSolve it following this recipe. Keep its shape and its checks; use names "
            f"from the task, not from the recipe's kitchen examples.\n\n{recipe.markdown()}\n\n{style_guide()}"
        )
    elif name == "review_python":
        text = (
            "Review this Python against the house style below. For each problem, name the recipe that fixes it "
            f"(call search_recipes when unsure) and show the corrected code.\n\n```python\n{args.get('code', '')}\n"
            f"```\n\n{style_guide()}"
        )
    else:
        raise KeyError(name)
    return {
        "description": PROMPTS[name][0],
        "messages": [{"role": "user", "content": {"type": "text", "text": text}}],
    }


def _resources() -> list[Json]:
    found = [
        {
            "uri": f"{URI}{r.id}",
            "name": r.id,
            "title": r.title,
            "description": r.summary,
            "mimeType": "text/markdown",
        }
        for r in catalogue.recipes()
    ]
    style = {"uri": "mothersauce://style", "name": "style", "title": "House style", "mimeType": "text/markdown"}
    return [*found, style]


def _read(uri: str) -> Json:
    if uri == "mothersauce://style":
        text = style_guide()
    elif uri.startswith(URI):
        text = catalogue.get(uri.removeprefix(URI)).markdown()
    else:
        raise ValueError(f"unknown resource {uri}")
    return {"contents": [{"uri": uri, "mimeType": "text/markdown", "text": text}]}


class Server:
    """Answers MCP messages. Stateless: every request is answered from the catalogue alone."""

    def handle(self, message: Json) -> Json | None:
        """
        Answer one JSON-RPC message.

        :param message: A request, or a notification, which gets no answer
        :returns: The response, or None for a notification
        """
        if "id" not in message:
            return None
        mid = message["id"]
        try:
            result = self._dispatch(str(message.get("method", "")), message.get("params") or {})
        except KeyError as missing:
            return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"unknown: {missing}"}}
        except (ValueError, catalogue.CatalogueError) as error:
            return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32602, "message": str(error)}}
        return {"jsonrpc": "2.0", "id": mid, "result": result}

    def _dispatch(self, method: str, params: Json) -> Json:
        if method == "initialize":
            asked = str(params.get("protocolVersion", ""))
            return {
                "protocolVersion": asked if asked in PROTOCOL_VERSIONS else PROTOCOL_VERSIONS[0],
                "capabilities": {"tools": {}, "resources": {}, "prompts": {}},
                "serverInfo": {"name": "mothersauce", "title": "mothersauce", "version": _version()},
                "instructions": INSTRUCTIONS,
            }
        if method == "ping":
            return {}
        if method == "tools/list":
            return {
                "tools": [
                    {
                        "name": name,
                        "description": about,
                        "inputSchema": {
                            "type": "object",
                            "properties": props,
                            "required": REQUIRED.get(name, []),
                            "additionalProperties": False,
                        },
                        "annotations": READ_ONLY,
                    }
                    for name, (_, about, props) in TOOLS.items()
                ]
            }
        if method == "tools/call":
            name = str(params.get("name", ""))
            if name not in TOOLS:
                raise ValueError(f"unknown tool {name!r}")
            try:
                return TOOLS[name][0](params.get("arguments") or {})
            except (ValueError, catalogue.CatalogueError) as error:
                return {"content": [{"type": "text", "text": f"Error: {error}"}], "isError": True}
        if method == "resources/list":
            return {"resources": _resources()}
        if method == "resources/templates/list":
            template = {"uriTemplate": URI + "{id}", "name": "recipe", "mimeType": "text/markdown"}
            return {"resourceTemplates": [template]}
        if method == "resources/read":
            return _read(str(params.get("uri", "")))
        if method == "prompts/list":
            return {"prompts": [{"name": n, "description": d, "arguments": a} for n, (d, a) in PROMPTS.items()]}
        if method == "prompts/get":
            return _prompt(str(params.get("name", "")), params.get("arguments") or {})
        raise KeyError(method)


def _version() -> str:
    from mothersauce import __version__

    return __version__


def serve(stdin: TextIO | None = None, stdout: TextIO | None = None) -> None:
    """
    Serve MCP over stdio, one JSON message per line, until the input closes.

    :param stdin: Where requests come from; standard input by default
    :param stdout: Where answers go; standard output by default
    """
    server, reader, writer = Server(), stdin or sys.stdin, stdout or sys.stdout
    for line in reader:
        if not line.strip():
            continue
        try:
            message = json.loads(line)
        except ValueError:
            reply: Any = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}}
        else:
            batch = message if isinstance(message, list) else [message]
            answers = [a for a in (server.handle(m) for m in batch if isinstance(m, dict)) if a is not None]
            reply = answers if isinstance(message, list) else (answers[0] if answers else None)
        if reply:
            writer.write(json.dumps(reply) + "\n")
            writer.flush()


def demo() -> None:
    """Talk to the server the way an agent harness does: start up, list the tools, search, read a resource."""
    server = Server()
    conversation: list[tuple[str, Json]] = [
        ("initialize", {"protocolVersion": "2025-11-25", "clientInfo": {"name": "demo", "version": "1"}}),
        ("notifications/initialized", {}),
        ("tools/list", {}),
        ("tools/call", {"name": "search_recipes", "arguments": {"query": "stream a huge csv file", "limit": 3}}),
        ("resources/read", {"uri": f"{URI}generators"}),
    ]
    for number, (method, params) in enumerate(conversation, start=1):
        request: Json = {"jsonrpc": "2.0", "method": method, "params": params}
        if not method.startswith("notifications/"):
            request["id"] = number
        reply = server.handle(request)
        if reply is None:
            print(f"-> {method}: a notification, so no reply")
            continue
        result = reply["result"]
        if method == "initialize":
            info = result["serverInfo"]
            shown = f"{info['name']} {info['version']}, protocol {result['protocolVersion']}"
        elif method == "tools/list":
            shown = ", ".join(tool["name"] for tool in result["tools"])
        elif method == "tools/call":
            shown = ", ".join(hit["id"] for hit in result["structuredContent"]["results"])
        else:
            shown = result["contents"][0]["text"].splitlines()[0]
        print(f"-> {method}\n<- {shown}")
