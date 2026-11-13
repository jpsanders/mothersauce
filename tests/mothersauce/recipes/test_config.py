from pathlib import Path

import pytest
from pydantic import ValidationError

from mothersauce.recipes.config import UNSET, Settings, demo, from_env, load_settings, merge


def test_from_env_reads_prefixed_nested_variables() -> None:
    environ = {"KITCHEN_BATCH_SIZE": "9", "KITCHEN_DATABASE__POOL_SIZE": "3", "PATH": "/bin", "KITCHENER": "no"}
    assert from_env(environ) == {"batch_size": "9", "database": {"pool_size": "3"}}


def test_merge_later_layers_win_and_sections_merge() -> None:
    merged, origin = merge(
        [
            ("file", {"a": 1, "db": {"url": "x", "pool": 2}}),
            ("env", {"db": {"pool": 5}}),
            ("cli", {"a": UNSET, "b": False}),
        ]
    )
    assert merged == {"a": 1, "db": {"url": "x", "pool": 5}, "b": False}
    assert origin == {"a": "file", "db.url": "file", "db.pool": "env", "b": "cli"}


def test_defaults_only() -> None:
    settings, origin = load_settings(None, {})
    assert settings == Settings()
    assert origin == {}


def test_every_layer_in_precedence_order(tmp_path: Path) -> None:
    path = tmp_path / "k.toml"
    path.write_text('batch_size = 10\nlog_level = "DEBUG"\n[database]\nurl = "sqlite:///t.db"\n', encoding="utf-8")
    environ = {"KITCHEN_BATCH_SIZE": "20", "KITCHEN_JSON_LOGS": "false"}
    settings, origin = load_settings(path, environ, batch_size=30)
    assert (settings.batch_size, settings.log_level, settings.json_logs) == (30, "DEBUG", False)
    assert settings.database.url == "sqlite:///t.db"
    assert origin["batch_size"] == "command line" and origin["json_logs"] == "environment"
    assert origin["database.url"] == str(path)


def test_unset_flags_do_not_override() -> None:
    settings, _ = load_settings(None, {"KITCHEN_LOG_LEVEL": "ERROR"}, log_level=UNSET)
    assert settings.log_level == "ERROR"


def test_reads_os_environ_when_not_given(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KITCHEN_KITCHEN", "From Env")
    assert load_settings()[0].kitchen == "From Env"


def test_all_problems_reported_together() -> None:
    with pytest.raises(ValueError) as caught:
        load_settings(None, {"KITCHEN_BATCH_SIZE": "0", "KITCHEN_LOG_LEVEL": "LOUD", "KITCHEN_TYPO": "1"})
    message = str(caught.value)
    assert "batch_size" in message and "log_level" in message and "typo: Extra inputs" in message


def test_settings_are_frozen_and_secrets_hidden() -> None:
    settings, _ = load_settings(None, {"KITCHEN_DATABASE__PASSWORD": "hunter2"})
    assert "hunter2" not in repr(settings)
    assert settings.database.password is not None and settings.database.password.get_secret_value() == "hunter2"
    with pytest.raises(ValidationError, match="frozen"):
        settings.batch_size = 1  # type: ignore[misc]


def test_demo_runs(capsys: pytest.CaptureFixture[str]) -> None:
    demo()
    out = capsys.readouterr().out
    assert "batch_size 250 from the command line" in out
    assert "database.pool_size 8 from the environment" in out
