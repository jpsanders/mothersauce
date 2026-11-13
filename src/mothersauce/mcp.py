"""
A Model Context Protocol server for coding agents, with no dependencies.

MCP is JSON-RPC 2.0, and over stdio each message is one line of JSON: read a line, answer a line. That is the whole
transport, so a useful server fits in one module of the standard library and starts in milliseconds, which matters
because an agent harness starts it for every session.

This server is read only. It offers the recipes three ways: as tools an agent calls (list, search, read, the style
guide), as resources it can attach to a conversation, and as prompts that apply a recipe to a task or review code
against the house style. Every tool is marked read only, so harnesses can let agents call them without asking.

A server must survive its clients. Every message is checked before it is used, a bad argument becomes an error the
agent can read, and nothing a client sends can end the process: the harness would lose every tool for the session.
"""

import json
import sys
from collections.abc import Callable
from importlib import resources
from typing import Any, TextIO

from mothersauce import catalogue

__all__ = ["PROTOCOL_VERSIONS", "Server", "demo", "serve", "style_guide"]

PROTOCOL_VERSIONS = ("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")
INSTRUCTIONS = (
    "mothersauce serves typed, tested reference recipes for production Python. Before writing or reviewing Python, "
    "call search_recipes with the problem in a few words, then get_recipe for the best match, and follow its shape "
    "and the house style from get_style_guide. Copy the shape, not the kitchen names."
)
READ_ONLY = {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False}
URI = "mothersauce://recipes/"
INVALID_REQUEST, METHOD_NOT_FOUND, INVALID_PARAMS, INTERNAL_ERROR, NOT_FOUND = -32600, -32601, -32602, -32603, -32002

type Json = dict[str, Any]


class ResourceNotFound(LookupError):
    """A resource URI that names nothing this server has."""


def style_guide() -> str:
    """
    Read the house style that ships with the package.

    :returns: The style guide as Markdown
    """
    return (resources.files("mothersauce") / "data" / "practice" / "style.md").read_text(encoding="utf-8")


def _text(structured: Json | str) -> Json:
    """
    Build a tool result. A structured result also travels as its JSON text, for clients that read only text.

    :param structured: A JSON object, or plain text
    :returns: The tool result
    """
    if isinstance(structured, str):
        return {"content": [{"type": "text", "text": structured}], "isError": False}
    text = json.dumps(structured, indent=1)
    return {"content": [{"type": "text", "text": text}], "structuredContent": structured, "isError": False}


def _choice(args: Json, name: str, allowed: tuple[str, ...], default: str | None) -> str | None:
    value = args.get(name)
    if value is None:
        return default
    if value not in allowed:
        raise ValueError(f"{name} must be one of {', '.join(allowed)}")
    return str(value)


def _list_recipes(args: Json) -> Json:
    section = _choice(args, "section", catalogue.SECTIONS, None)
    kind = _choice(args, "kind", ("code", "practice"), None)
    found = [r.as_dict() for r in catalogue.recipes() if section in (None, r.section) and kind in (None, r.kind)]
    return _text({"recipes": found})


def _search_recipes(args: Json) -> Json:
    query = args.get("query")
    if not isinstance(query, str) or not query.strip():
        raise ValueError("query is required: the problem in a few words")
    limit = args.get("limit")
    limit = 5 if limit is None else limit
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 30:
        raise ValueError("limit must be a whole number from 1 to 30")
    hits = [{"id": r.id, "title": r.title, "summary": r.summary, "score": s} for r, s in catalogue.search(query, limit)]
    return _text({"results": hits})


def _get_recipe(args: Json) -> Json:
    name = args.get("id")
    if not isinstance(name, str):
        raise ValueError("id is required, such as context-managers")
    part = _choice(args, "part", ("all", "notes", "code"), "all")
    return _text(catalogue.get(name).markdown(part))  # type: ignore[arg-type]  # _choice allowed only these three


def _get_style_guide(args: Json) -> Json:
    return _text(style_guide())


TOOLS: dict[str, tuple[Callable[[Json], Json], str, Json, list[str]]] = {
    "list_recipes": (
        _list_recipes,
        "List every recipe with its section, summary, tags and the Python features it shows.",
        {
            "section": {"type": "string", "enum": list(catalogue.SECTIONS)},
            "kind": {"type": "string", "enum": ["code", "practice"]},
        },
        [],
    ),
    "search_recipes": (
        _search_recipes,
        "Find the recipes for a problem described in a few words, such as 'retry a flaky api call'.",
        {"query": {"type": "string"}, "limit": {"type": "integer", "minimum": 1, "maximum": 30, "default": 5}},
        ["query"],
    ),
    "get_recipe": (
        _get_recipe,
        "Read one recipe as Markdown: when to use it, when not to, and its complete, tested source.",
        {"id": {"type": "string"}, "part": {"type": "string", "enum": ["all", "notes", "code"], "default": "all"}},
        ["id"],
    ),
    "get_style_guide": (
        _get_style_guide,
        "Read the house style: layout, naming, typing, docstrings, errors, logging and tests.",
        {},
        [],
    ),
}

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


def _prompt(params: Json) -> Json:
    name = params.get("name")
    if name not in PROMPTS:
        raise ValueError(f"unknown prompt {name!r}; prompts: {', '.join(PROMPTS)}")
    args = params.get("arguments") or {}
    if not isinstance(args, dict):
        raise ValueError("arguments must be an object")
    missing = [a["name"] for a in PROMPTS[name][1] if a["required"] and not str(args.get(a["name"]) or "").strip()]
    if missing:
        raise ValueError(f"missing required arguments: {', '.join(missing)}")
    if name == "apply_recipe":
        recipe = catalogue.get(str(args["recipe"]))
        text = (
            f"Task: {args['task']}\n\nSolve it following this recipe. Keep its shape and its checks; use names from "
            f"the task, not from the recipe's kitchen examples.\n\n{recipe.markdown()}\n\n{style_guide()}"
        )
    else:
        text = (
            "Review this Python against the house style below. For each problem, name the recipe that fixes it "
            f"(call search_recipes when unsure) and show the corrected code.\n\n```python\n{args['code']}\n```\n\n"
            f"{style_guide()}"
        )
    return {"description": PROMPTS[name][0], "messages": [{"role": "user", "content": {"type": "text", "text": text}}]}


def _resources() -> list[Json]:
    found = [
        {"uri": f"{URI}{r.id}", "name": r.id, "title": r.title, "description": r.summary, "mimeType": "text/markdown"}
        for r in catalogue.recipes()
    ]
    style = {"uri": "mothersauce://style", "name": "style", "title": "House style", "mimeType": "text/markdown"}
    return [*found, style]


def _read(params: Json) -> Json:
    uri = params.get("uri")
    if not isinstance(uri, str):
        raise ValueError("uri is required")
    if uri == "mothersauce://style":
        text = style_guide()
    elif uri.startswith(URI):
        try:
            text = catalogue.get(uri.removeprefix(URI)).markdown()
        except catalogue.CatalogueError:
            raise ResourceNotFound(uri) from None
    else:
        raise ResourceNotFound(uri)
    return {"contents": [{"uri": uri, "mimeType": "text/markdown", "text": text}]}


def _call_tool(params: Json) -> Json:
    name = params.get("name")
    if name not in TOOLS:
        raise ValueError(f"unknown tool {name!r}")
    args = params.get("arguments") or {}
    if not isinstance(args, dict):
        raise ValueError("arguments must be an object")
    try:
        return TOOLS[name][0](args)
    except (ValueError, TypeError, catalogue.CatalogueError) as error:
        return {"content": [{"type": "text", "text": f"Error: {error}"}], "isError": True}


def _initialize(params: Json) -> Json:
    asked = str(params.get("protocolVersion", ""))
    return {
        "protocolVersion": asked if asked in PROTOCOL_VERSIONS else PROTOCOL_VERSIONS[0],
        "capabilities": {"tools": {}, "resources": {}, "prompts": {}},
        "serverInfo": {"name": "mothersauce", "title": "mothersauce", "version": _version()},
        "instructions": INSTRUCTIONS,
    }


def _list_tools(params: Json) -> Json:
    tools = []
    for name, (_, about, props, required) in TOOLS.items():
        schema = {"type": "object", "properties": props, "required": required, "additionalProperties": False}
        tools.append({"name": name, "description": about, "inputSchema": schema, "annotations": READ_ONLY})
    return {"tools": tools}


def _list_prompts(params: Json) -> Json:
    return {"prompts": [{"name": n, "description": d, "arguments": a} for n, (d, a) in PROMPTS.items()]}


def _templates(params: Json) -> Json:
    return {"resourceTemplates": [{"uriTemplate": URI + "{id}", "name": "recipe", "mimeType": "text/markdown"}]}


METHODS: dict[str, Callable[[Json], Json]] = {
    "initialize": _initialize,
    "ping": lambda params: {},
    "tools/list": _list_tools,
    "tools/call": _call_tool,
    "resources/list": lambda params: {"resources": _resources()},
    "resources/templates/list": _templates,
    "resources/read": _read,
    "prompts/list": _list_prompts,
    "prompts/get": _prompt,
}


def _error(mid: object, code: int, message: str, data: object = None) -> Json:
    error: Json = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return {"jsonrpc": "2.0", "id": mid, "error": error}


class Server:
    """Answers MCP messages. Stateless: every request is answered from the catalogue alone."""

    def handle(self, message: Json) -> Json | None:
        """
        Answer one JSON-RPC message. Whatever arrives, the answer is a result or an error, never an exception.

        :param message: A request, or a notification, which gets no answer
        :returns: The response, or None for a notification
        """
        if "id" not in message:
            return None
        mid, method, params = message["id"], message.get("method"), message.get("params")
        if not isinstance(method, str):
            return _error(mid, INVALID_REQUEST, "invalid request: method must be a string")
        if method not in METHODS:
            return _error(mid, METHOD_NOT_FOUND, f"method not found: {method}")
        if params is not None and not isinstance(params, dict):
            return _error(mid, INVALID_PARAMS, "params must be an object")
        try:
            return {"jsonrpc": "2.0", "id": mid, "result": METHODS[method](params or {})}
        except ResourceNotFound as missing:
            return _error(mid, NOT_FOUND, "resource not found", {"uri": str(missing)})
        except (ValueError, TypeError, catalogue.CatalogueError) as error:
            return _error(mid, INVALID_PARAMS, str(error))
        except Exception as error:  # the last line of defence: one bad message must not end the session
            print(f"mothersauce mcp: {type(error).__name__}: {error}", file=sys.stderr)
            return _error(mid, INTERNAL_ERROR, "internal error")


def _version() -> str:
    from mothersauce import __version__

    return __version__


def _answer(server: Server, message: object) -> Json | None:
    if not isinstance(message, dict):
        return _error(None, INVALID_REQUEST, "invalid request: expected a JSON object")
    return server.handle(message)


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
            reply: Any = _error(None, -32700, "parse error")
        else:
            if isinstance(message, list):
                answers = [a for a in (_answer(server, m) for m in message) if a is not None]
                reply = answers if message else _error(None, INVALID_REQUEST, "invalid request: empty batch")
            else:
                reply = _answer(server, message)
        if reply:
            writer.write(json.dumps(reply) + "\n")
            writer.flush()


def demo() -> None:
    """Talk to the server the way an agent harness does, then send it a malformed request it must survive."""
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
    bad = server.handle({"jsonrpc": "2.0", "id": 9, "method": "tools/call", "params": {"name": 3, "arguments": "x"}})
    print(f"-> a malformed tools/call\n<- error {bad['error']['code']}: {bad['error']['message']}" if bad else "")
