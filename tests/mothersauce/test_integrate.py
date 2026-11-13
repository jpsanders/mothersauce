import json
import shutil
import sys
import tomllib
from pathlib import Path

import pytest

from mothersauce import integrate
from mothersauce.integrate import Step, command, run, skill_text


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """
    Make a home folder where every harness is installed but none of their command line tools are.

    :param tmp_path: pytest's temporary folder
    :param monkeypatch: pytest's patcher
    :returns: The home folder
    """
    for folder in (".claude", ".codex", ".config/opencode", ".gemini", ".cursor"):
        (tmp_path / folder).mkdir(parents=True)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / ".config"))
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    monkeypatch.delenv("CODEX_HOME", raising=False)
    monkeypatch.setattr(shutil, "which", lambda name: None)
    return tmp_path


def test_command_prefers_the_installed_program(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda name: "/usr/local/bin/mothersauce")
    assert command() == ["/usr/local/bin/mothersauce", "mcp"]
    monkeypatch.setattr(shutil, "which", lambda name: None)
    assert command() == [sys.executable, "-m", "mothersauce", "mcp"]


def test_dry_run_changes_nothing(home: Path) -> None:
    steps = run([], dry=True, home=home)
    assert {s.harness for s in steps} == {"claude", "codex", "opencode", "gemini", "cursor"}
    assert not any(s.done for s in steps)
    assert not (home / ".claude.json").exists() and not (home / ".claude/skills").exists()


def test_every_harness_gets_the_server_and_the_skill(home: Path) -> None:
    steps = run(["all"], home=home)
    claude_mcp = next(s for s in steps if (s.harness, s.what) == ("claude", "mcp"))
    assert not claude_mcp.done and claude_mcp.target.startswith("claude mcp add --scope user mothersauce -- ")
    assert not (home / ".claude.json").exists()  # Claude Code's live state is never edited from outside
    others = [s for s in steps if s is not claude_mcp]
    assert all(s.done for s in others), [s.line() for s in others if not s.done]
    assert tomllib.loads((home / ".codex/config.toml").read_text(encoding="utf-8"))["mcp_servers"]["mothersauce"]
    assert json.loads((home / ".config/opencode/opencode.json").read_text(encoding="utf-8"))["mcp"]["mothersauce"]
    assert json.loads((home / ".gemini/settings.json").read_text(encoding="utf-8"))["mcpServers"]["mothersauce"]
    assert json.loads((home / ".cursor/mcp.json").read_text(encoding="utf-8"))["mcpServers"]["mothersauce"]
    for skill in (".claude/skills", ".codex/skills", ".config/opencode/skill"):
        assert (home / skill / "mothersauce" / "SKILL.md").read_text(encoding="utf-8") == skill_text()


def test_running_twice_changes_nothing_more(home: Path) -> None:
    run([], home=home)
    again = {(s.harness, s.what): s for s in run([], home=home)}
    assert again[("cursor", "mcp")].note == "already there"
    assert again[("codex", "mcp")].note == "already there"


def test_existing_config_is_kept_and_backed_up(home: Path) -> None:
    config = home / ".cursor" / "mcp.json"
    config.write_text('{"mcpServers": {"other": {"command": "x"}}}', encoding="utf-8")
    run(["cursor"], home=home)
    servers = json.loads(config.read_text(encoding="utf-8"))["mcpServers"]
    assert set(servers) == {"other", "mothersauce"}
    assert json.loads(config.with_name("mcp.json.mothersauce.bak").read_text(encoding="utf-8")) == {
        "mcpServers": {"other": {"command": "x"}}
    }


@pytest.mark.parametrize("content", ["// comments are not JSON\n{}", "[1, 2]", '{"mcpServers": []}'])
def test_unreadable_config_is_left_alone(home: Path, content: str) -> None:
    config = home / ".gemini" / "settings.json"
    config.write_text(content, encoding="utf-8")
    (step,) = run(["gemini"], home=home)
    assert not step.done and "by hand" in step.note
    assert config.read_text(encoding="utf-8") == content


def test_harness_command_lines_are_used_when_installed(home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr(shutil, "which", lambda name: f"/bin/{name}" if name in ("claude", "codex") else None)

    def fake_run(args: list[str], env: dict[str, str] | None = None) -> tuple[int, str]:
        calls.append(args)
        return 0, ""

    monkeypatch.setattr(integrate, "_run", fake_run)
    steps = run(["claude", "codex"], home=home)
    assert all(s.done for s in steps)
    assert ["/bin/claude", "mcp", "add", "--scope", "user", "mothersauce", "--"] == calls[1][:7]
    assert calls[2][:4] == ["codex", "mcp", "add", "mothersauce"]


def test_a_failing_harness_command_is_reported(home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda name: "/bin/claude" if name == "claude" else None)
    monkeypatch.setattr(integrate, "_run", lambda args, env=None: (1, "claude: not logged in"))
    mcp_step = run(["claude"], home=home)[0]
    assert not mcp_step.done and mcp_step.note == "claude: not logged in"


def test_run_reports_real_command_failures(home: Path) -> None:
    code, out = integrate._run(["/nonexistent/program"])
    assert code == 1 and out


def test_unknown_harness_and_missing_harnesses(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / ".config"))
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    monkeypatch.delenv("CODEX_HOME", raising=False)
    (step,) = run(["vim"], home=tmp_path)
    assert not step.done and "choose from claude" in step.note
    assert run([], home=tmp_path) == []


def test_step_line() -> None:
    assert Step("cursor", "mcp", "/x/mcp.json", True).line() == "[ok] cursor   mcp   /x/mcp.json"
    assert Step("gemini", "mcp", "/y", False, "why").line().endswith("(why)")


def test_dry_run_reports_the_commands_a_real_run_would_use(home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr(shutil, "which", lambda name: f"/bin/{name}" if name in ("claude", "codex") else None)

    def fake_run(args: list[str], env: dict[str, str] | None = None) -> tuple[int, str]:
        calls.append(args)
        return 0, ""

    monkeypatch.setattr(integrate, "_run", fake_run)
    steps = {(s.harness, s.what): s for s in run(["claude", "codex"], dry=True, home=home)}
    assert steps[("claude", "mcp")].note == "would run" and steps[("codex", "mcp")].note == "would run"
    assert steps[("codex", "mcp")].target.startswith("codex mcp add mothersauce -- ")
    assert calls == []


def test_codex_config_is_backed_up_before_the_append(home: Path) -> None:
    config = home / ".codex" / "config.toml"
    config.write_text('model = "o4"\n', encoding="utf-8")
    run(["codex"], home=home)
    assert config.with_name("config.toml.mothersauce.bak").read_text(encoding="utf-8") == 'model = "o4"\n'
    assert "[mcp_servers.mothersauce]" in config.read_text(encoding="utf-8")


def test_a_broken_codex_config_is_left_alone(home: Path) -> None:
    config = home / ".codex" / "config.toml"
    config.write_text("model = [", encoding="utf-8")
    (step,) = run(["codex"], home=home)
    assert not step.done and "does not parse" in step.note
    assert config.read_text(encoding="utf-8") == "model = ["


def test_a_throwaway_uvx_copy_registers_uvx_itself(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda name: "/home/u/.cache/uv/archive-v0/abc/bin/mothersauce")
    assert command() == ["uvx", "mothersauce", "mcp"]
