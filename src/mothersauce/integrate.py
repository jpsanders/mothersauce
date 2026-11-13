"""
Connect mothersauce to agent harnesses: register its MCP server, and install its skill where the harness reads one.

Claude Code and Codex are changed through their own command line, ``claude mcp add`` and ``codex mcp add``, because
they rewrite their configuration while they run. Without that command line, Claude Code is left alone and the exact
command is printed instead: its configuration file is live state, never safe to edit from outside. Codex, OpenCode,
Gemini CLI and Cursor configuration files are edited after a backup next to them, and a file that does not parse is
left untouched. A dry run reports exactly what a real run would do.

The server is registered in all five. The skill goes to Claude Code, Codex and OpenCode, which read skills folders.
"""

import json
import os
import shlex
import shutil
import subprocess  # nosec B404  # fixed commands only, never a shell
import sys
import tomllib
from collections.abc import Callable
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any

__all__ = ["HARNESSES", "Step", "command", "run", "skill_text"]

NAME = "mothersauce"
UVX = ["uvx", "--from", "git+https://github.com/jpsanders/mothersauce", NAME, "mcp"]


@dataclass(frozen=True, slots=True)
class Step:
    """
    One change made, or that would be made.

    :param harness: Which harness
    :param what: ``mcp`` or ``skill``
    :param target: The file or command changed
    :param done: Whether it happened
    :param note: Anything the user should know
    """

    harness: str
    what: str
    target: str
    done: bool
    note: str = ""

    def line(self) -> str:
        """
        Describe the step in one line.

        :returns: The line
        """
        mark = "ok" if self.done else "--"
        return f"[{mark}] {self.harness:8} {self.what:5} {self.target}" + (f"  ({self.note})" if self.note else "")


def _ephemeral(path: str) -> bool:
    """
    Tell whether a path lies in uv's cache, where ``uvx`` puts throwaway environments that a cache clean removes.

    :param path: An executable or interpreter path
    :returns: True for a throwaway environment
    """
    caches = [os.environ.get("UV_CACHE_DIR", ""), str(Path.home() / ".cache" / "uv"), "/uv/archive-v"]
    return any(marker and marker in path for marker in caches)


def command() -> list[str]:
    """
    Return the command a harness runs to start the server: the installed ``mothersauce``, else this interpreter.

    When this copy runs from a throwaway uvx environment, register ``uvx`` itself, which outlives a cache clean.

    :returns: Program and arguments
    """
    installed = shutil.which(NAME)
    found = [installed, "mcp"] if installed else [sys.executable, "-m", NAME, "mcp"]
    return UVX if _ephemeral(found[0]) or _ephemeral(sys.prefix) else found


def skill_text() -> str:
    """
    Read the skill shipped with the package.

    :returns: Markdown with front matter
    """
    return (resources.files(NAME) / "data" / "SKILL.md").read_text(encoding="utf-8")


def _write_skill(folder: Path, harness: str, dry: bool) -> Step:
    target = folder / NAME / "SKILL.md"
    if not dry:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(skill_text(), encoding="utf-8")
    return Step(harness, "skill", str(target), not dry)


def _backup(path: Path) -> None:
    if path.is_file():
        shutil.copy2(path, path.with_name(path.name + ".mothersauce.bak"))


def _json_server(path: Path, key: str, entry: dict[str, Any], harness: str, dry: bool) -> Step:
    try:
        data = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    except ValueError:
        return Step(harness, "mcp", str(path), False, "not plain JSON (comments?); add the server by hand")
    if not isinstance(data, dict) or not isinstance(data.setdefault(key, {}), dict):
        return Step(harness, "mcp", str(path), False, "unexpected layout; add the server by hand")
    if data[key].get(NAME) == entry:
        return Step(harness, "mcp", str(path), True, "already there")
    data[key][NAME] = entry
    if not dry:
        _backup(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return Step(harness, "mcp", str(path), not dry)


def _run(args: list[str], env: dict[str, str] | None = None) -> tuple[int, str]:
    try:
        result = subprocess.run(  # nosec B603  # fixed commands
            args, capture_output=True, text=True, timeout=60, env={**os.environ, **(env or {})}, check=False
        )
    except (OSError, subprocess.SubprocessError) as error:
        return 1, str(error)
    return result.returncode, (result.stdout + result.stderr).strip()


def claude(home: Path, dry: bool) -> list[Step]:
    """
    Register the server with ``claude mcp add`` and install the skill for Claude Code.

    :param home: The home folder
    :param dry: Only say what would change
    :returns: The steps
    """
    folder = Path(os.environ.get("CLAUDE_CONFIG_DIR") or home / ".claude")
    if not folder.is_dir():
        return []
    cli = shutil.which("claude")
    add = ["claude", "mcp", "add", "--scope", "user", NAME, "--", *command()]
    if not cli:
        step = Step("claude", "mcp", shlex.join(add), False, "the claude command is not on PATH; run this line")
    elif dry:
        step = Step("claude", "mcp", shlex.join(add), False, "would run")
    else:
        _run([cli, "mcp", "remove", "--scope", "user", NAME])
        code, out = _run([cli, *add[1:]])
        step = Step("claude", "mcp", shlex.join(add), code == 0, "" if code == 0 else out[:160])
    return [step, _write_skill(folder / "skills", "claude", dry)]


def codex(home: Path, dry: bool) -> list[Step]:
    """
    Register the server and install the skill for Codex.

    :param home: The home folder
    :param dry: Only say what would change
    :returns: The steps
    """
    folder = Path(os.environ.get("CODEX_HOME") or home / ".codex")
    if not folder.is_dir():
        return []
    path, cmd = folder / "config.toml", command()
    try:
        current = tomllib.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    except tomllib.TOMLDecodeError:
        return [Step("codex", "mcp", str(path), False, "config.toml does not parse; add the server by hand")]
    skill = _write_skill(folder / "skills", "codex", dry)
    if NAME in (current.get("mcp_servers") or {}):
        return [Step("codex", "mcp", str(path), True, "already there"), skill]
    if shutil.which("codex"):
        add = ["codex", "mcp", "add", NAME, "--", *cmd]
        if dry:
            return [Step("codex", "mcp", shlex.join(add), False, "would run"), skill]
        code, out = _run(add)
        return [Step("codex", "mcp", shlex.join(add), code == 0, "" if code == 0 else out[:160]), skill]
    if not dry:
        _backup(path)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(f"\n[mcp_servers.{NAME}]\ncommand = {json.dumps(cmd[0])}\nargs = {json.dumps(cmd[1:])}\n")
    return [Step("codex", "mcp", str(path), not dry), skill]


def opencode(home: Path, dry: bool) -> list[Step]:
    """
    Register the server and install the skill for OpenCode.

    :param home: The home folder
    :param dry: Only say what would change
    :returns: The steps
    """
    folder = Path(os.environ.get("XDG_CONFIG_HOME") or home / ".config") / "opencode"
    if not folder.is_dir():
        return []
    entry = {"type": "local", "command": command(), "enabled": True}
    return [
        _json_server(folder / "opencode.json", "mcp", entry, "opencode", dry),
        _write_skill(folder / "skill", "opencode", dry),
    ]


def gemini(home: Path, dry: bool) -> list[Step]:
    """
    Register the server for Gemini CLI.

    :param home: The home folder
    :param dry: Only say what would change
    :returns: The steps
    """
    if not (home / ".gemini").is_dir():
        return []
    cmd = command()
    entry = {"command": cmd[0], "args": cmd[1:]}
    return [_json_server(home / ".gemini" / "settings.json", "mcpServers", entry, "gemini", dry)]


def cursor(home: Path, dry: bool) -> list[Step]:
    """
    Register the server for Cursor.

    :param home: The home folder
    :param dry: Only say what would change
    :returns: The steps
    """
    if not (home / ".cursor").is_dir():
        return []
    cmd = command()
    entry = {"command": cmd[0], "args": cmd[1:]}
    return [_json_server(home / ".cursor" / "mcp.json", "mcpServers", entry, "cursor", dry)]


HARNESSES: dict[str, Callable[[Path, bool], list[Step]]] = {
    "claude": claude,
    "codex": codex,
    "opencode": opencode,
    "gemini": gemini,
    "cursor": cursor,
}


def run(names: list[str], dry: bool = False, home: Path | None = None) -> list[Step]:
    """
    Integrate with the named harnesses, or with every one installed.

    :param names: Harness names; empty or ``all`` for every one
    :param dry: Only say what would change
    :param home: The home folder; the user's when omitted
    :returns: The steps, empty when no harness was found
    """
    home = home or Path.home()
    wanted = list(HARNESSES) if not names or "all" in names else names
    steps: list[Step] = []
    for name in wanted:
        integrate = HARNESSES.get(name)
        if integrate is None:
            steps.append(Step(name, "-", "unknown harness", False, f"choose from {', '.join(HARNESSES)}"))
            continue
        steps.extend(integrate(home, dry))
    return steps
