"""
Connect mothersauce to agent harnesses: register its MCP server and install its skill.

Each harness's own CLI is used when it is installed (``claude mcp add``, ``codex mcp add``), because those harnesses
rewrite their config files while they run. Otherwise the JSON file is edited, after a backup next to it.
"""

import json
import os
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


def command() -> list[str]:
    """
    Return the command a harness runs to start the server: the installed ``mothersauce``, else this interpreter.

    :returns: Program and arguments
    """
    installed = shutil.which(NAME)
    return [installed, "mcp"] if installed else [sys.executable, "-m", NAME, "mcp"]


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
        if path.is_file():
            shutil.copy2(path, path.with_name(path.name + ".mothersauce.bak"))
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
    Register the server and install the skill for Claude Code.

    :param home: The home folder
    :param dry: Only say what would change
    :returns: The steps
    """
    folder = Path(os.environ.get("CLAUDE_CONFIG_DIR") or home / ".claude")
    if not folder.is_dir():
        return []
    cmd, cli = command(), shutil.which("claude")
    if cli and not dry:
        _run([cli, "mcp", "remove", "--scope", "user", NAME])
        code, out = _run([cli, "mcp", "add", "--scope", "user", NAME, "--", *cmd])
        step = Step("claude", "mcp", "claude mcp add --scope user", code == 0, "" if code == 0 else out[:160])
    else:
        entry = {"type": "stdio", "command": cmd[0], "args": cmd[1:], "env": {}}
        step = _json_server(home / ".claude.json", "mcpServers", entry, "claude", dry)
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
    except tomllib.TOMLDecodeError, OSError:
        current = {}
    if NAME in (current.get("mcp_servers") or {}):
        step = Step("codex", "mcp", str(path), True, "already there")
    elif shutil.which("codex") and not dry:
        code, out = _run(["codex", "mcp", "add", NAME, "--", *cmd])
        step = Step("codex", "mcp", "codex mcp add", code == 0, "" if code == 0 else out[:160])
    else:
        if not dry:
            with path.open("a", encoding="utf-8") as handle:
                handle.write(f"\n[mcp_servers.{NAME}]\ncommand = {json.dumps(cmd[0])}\nargs = {json.dumps(cmd[1:])}\n")
        step = Step("codex", "mcp", str(path), not dry)
    return [step, _write_skill(folder / "skills", "codex", dry)]


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
    return [
        _json_server(
            home / ".gemini" / "settings.json", "mcpServers", {"command": cmd[0], "args": cmd[1:]}, "gemini", dry
        )
    ]


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
    return [
        _json_server(home / ".cursor" / "mcp.json", "mcpServers", {"command": cmd[0], "args": cmd[1:]}, "cursor", dry)
    ]


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
