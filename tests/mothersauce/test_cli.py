import io
import json
import sys
from pathlib import Path

import pytest

from mothersauce import __version__, integrate
from mothersauce.cli import PROG, demo, main


def run(capsys: pytest.CaptureFixture[str], *args: str) -> tuple[int, str, str]:
    code = main(list(args))
    out, err = capsys.readouterr()
    return code, out, err


def test_no_command_prints_the_menu(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _ = run(capsys)
    assert code == 0
    assert out.startswith("mothersauce: the base recipes of production Python")
    assert "\nMother sauces\n" in out and "26 recipes." in out


def test_version(capsys: pytest.CaptureFixture[str]) -> None:
    assert run(capsys, "--version")[1].strip() == f"{PROG} {__version__}"


def test_list_json_and_filters(capsys: pytest.CaptureFixture[str]) -> None:
    cards = json.loads(run(capsys, "list", "--json")[1])
    assert len(cards) == 26 and {"id", "section", "summary", "run"} <= set(cards[0])
    ids = run(capsys, "list", "--kind", "practice", "--ids")[1].split()
    assert ids == ["workflow", "layout", "style", "testing", "bdd"]
    service = json.loads(run(capsys, "list", "--section", "Service", "--json")[1])
    assert {c["id"] for c in service} == {"logging", "config", "concurrency", "performance", "cli", "mcp-server"}


def test_show(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _ = run(capsys, "show", "generators")
    assert code == 0 and out.startswith("# Generators\n") and "def read_lines" in out
    assert "def read_lines" not in run(capsys, "show", "generators", "--notes")[1]
    assert run(capsys, "show", "generators", "--code")[1].startswith("```python")


def test_show_json(capsys: pytest.CaptureFixture[str]) -> None:
    card = json.loads(run(capsys, "show", "context_managers", "--json")[1])
    assert card["id"] == "context-managers" and "ExitStack" in card["source"] and card["notes"]


def test_unknown_recipe_is_a_usage_error(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, err = run(capsys, "show", "generator")
    assert code == 2 and out == "" and "did you mean generators" in err
    assert run(capsys, "run", "nope")[0] == 2


def test_run_a_code_recipe(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _ = run(capsys, "run", "enums")
    assert code == 0 and out.startswith("Enums: Closed sets of names") and "fired -> paid: refused" in out


def test_practice_recipes_do_not_run(capsys: pytest.CaptureFixture[str]) -> None:
    code, _, err = run(capsys, "run", "style")
    assert code == 2 and "mothersauce show style" in err


def test_search(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _ = run(capsys, "search", "retry", "a", "flaky", "api", "call")
    assert code == 0 and out.startswith("1 recipe for 'retry a flaky api call': decorators")
    hits = json.loads(run(capsys, "search", "immutable", "value", "--json", "--limit", "2")[1])
    assert hits[0]["id"] == "dataclasses" and len(hits) <= 2


def test_search_without_hits(capsys: pytest.CaptureFixture[str]) -> None:
    code, _, err = run(capsys, "search", "zzzz")
    assert code == 1 and "no recipe matches" in err
    code, out, _ = run(capsys, "search", "zzzz", "--json")
    assert code == 1 and json.loads(out) == []


def test_style(capsys: pytest.CaptureFixture[str]) -> None:
    assert run(capsys, "style")[1].startswith("# House style")
    assert run(capsys, "style", "--agents")[1].startswith("## Python house style (mothersauce)")


def test_guide_prints_the_manual(capsys: pytest.CaptureFixture[str]) -> None:
    out = run(capsys, "guide")[1]
    assert out.startswith("# mothersauce\n") and "## FOR AI AGENTS" in out and "`search_recipes`" in out


def test_man_raw_is_roff(capsys: pytest.CaptureFixture[str]) -> None:
    out = run(capsys, "man", "--raw")[1]
    assert out.startswith(f".TH {PROG.upper()} 1") and ".SH NAME\nmothersauce \\- " in out


def test_man_install(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    assert run(capsys, "man", "--install")[0] == 0
    assert (tmp_path / "man" / "man1" / "mothersauce.1").read_text(encoding="utf-8").startswith(".TH MOTHERSAUCE 1")


def test_skill(capsys: pytest.CaptureFixture[str]) -> None:
    assert run(capsys, "skill")[1].startswith("---\nname: mothersauce\n")


def test_doctor(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _ = run(capsys, "doctor", "--json")
    checks = {c["check"]: c for c in json.loads(out)}
    assert code == 0 and checks["python"]["ok"] and checks["pydantic"]["ok"] and checks["recipes"]["ok"]
    assert "[ok] python" in run(capsys, "doctor")[1]


def test_integrate_dry_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / ".cursor").mkdir()
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    code, out, _ = run(capsys, "integrate", "--dry-run", "--json")
    steps = json.loads(out)
    assert code == 0 and steps[0]["harness"] == "cursor" and not steps[0]["done"]
    assert not (tmp_path / ".cursor" / "mcp.json").exists()


def test_integrate_with_nothing_installed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    monkeypatch.delenv("CODEX_HOME", raising=False)
    code, out, _ = run(capsys, "integrate")
    assert code == 1 and "add the server to any MCP client by hand" in out
    assert json.loads(out.splitlines()[-1])["mcpServers"]["mothersauce"]["args"][-1] == "mcp"
    assert integrate.command()[-1] == "mcp"


def test_mcp_command_serves_stdio(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(sys, "stdin", io.StringIO('{"jsonrpc": "2.0", "id": 1, "method": "ping"}\n'))
    code, out, _ = run(capsys, "mcp")
    assert code == 0 and json.loads(out) == {"jsonrpc": "2.0", "id": 1, "result": {}}


def test_bad_arguments_exit_2() -> None:
    with pytest.raises(SystemExit) as caught:
        main(["list", "--kind", "dessert"])
    assert caught.value.code == 2


def test_demo_runs(capsys: pytest.CaptureFixture[str]) -> None:
    demo()
    out = capsys.readouterr().out
    assert "integrate" in out and "reads: decorators" in out


@pytest.mark.parametrize("limit", ["0", "-1", "two"])
def test_search_limit_must_be_positive(limit: str) -> None:
    with pytest.raises(SystemExit) as caught:
        main(["search", "retry", "--limit", limit])
    assert caught.value.code == 2


def test_show_with_a_blank_name_is_a_usage_error(capsys: pytest.CaptureFixture[str]) -> None:
    code, _, err = run(capsys, "show", "")
    assert code == 2 and "a recipe id is required" in err
