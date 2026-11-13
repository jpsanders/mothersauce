"""
Configuration: one frozen, validated settings object, built from layers.

Settings arrive from several places, and the precedence should be the same in every program you write: defaults,
then a TOML file, then environment variables, then command line flags. Merge the layers, validate once, and hand the
rest of the program a frozen object. Nothing reads ``os.environ`` deep inside the code, and a typo in a setting
fails at start up instead of at three in the morning.

- ``tomllib`` reads TOML from the standard library.
- ``SecretStr`` keeps a password out of ``repr``, logs and dumps.
- ``sentinel()``, new in Python 3.15, marks "not given", so an omitted flag never looks like an empty or false one.
- mypy narrows a sentinel with ``is``, so ``int | UNSET`` type checks the way ``int | None`` does.
- Recording which layer set each value turns "why is the batch size 50?" into a one line answer.
"""

import os
import tempfile
import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError

__all__ = ["ENV_PREFIX", "UNSET", "DatabaseSettings", "Settings", "demo", "from_env", "load_settings", "merge"]

ENV_PREFIX = "KITCHEN_"
UNSET = sentinel("UNSET")


class DatabaseSettings(BaseModel):
    """
    Where the loader writes.

    :param url: The database URL
    :param password: Never printed: ``SecretStr`` shows asterisks
    :param pool_size: Connections to keep open
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    url: str = "sqlite:///kitchen.db"
    password: SecretStr | None = None
    pool_size: int = Field(default=5, ge=1, le=50)


class Settings(BaseModel):
    """
    Everything the program can be told. Frozen and strict about unknown keys.

    :param kitchen: The kitchen's name, for logs and reports
    :param batch_size: Rows per insert
    :param log_level: The lowest level logged
    :param json_logs: JSON lines for machines, or text for a terminal
    :param database: The database section
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    kitchen: str = "Le Pass"
    batch_size: int = Field(default=500, ge=1, le=100_000)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    json_logs: bool = True
    database: DatabaseSettings = DatabaseSettings()


def from_env(environ: Mapping[str, str], prefix: str = ENV_PREFIX) -> dict[str, Any]:
    """
    Read prefixed variables into nested settings: ``KITCHEN_DATABASE__POOL_SIZE=8`` sets ``database.pool_size``.

    :param environ: Usually ``os.environ``
    :param prefix: Only variables with this prefix count
    :returns: The settings they describe, as nested dicts of strings
    :raises ValueError: When one variable names a value and another a section at the same place
    """
    found: dict[str, Any] = {}
    for name, value in environ.items():
        if not name.startswith(prefix):
            continue
        *parents, leaf = name.removeprefix(prefix).lower().split("__")
        section = found
        for parent in parents:
            section = section.setdefault(parent, {})
            if not isinstance(section, dict):
                raise ValueError(f"{name} puts a key inside {prefix}{parent.upper()}, which is a value, not a section")
        if isinstance(section.get(leaf), dict):
            raise ValueError(f"{name} sets a value where other variables already define a section")
        section[leaf] = value
    return found


def merge(layers: list[tuple[str, Mapping[str, Any]]]) -> tuple[dict[str, Any], dict[str, str]]:
    """
    Merge named layers, later ones winning, nested sections merged key by key. Values that are ``UNSET`` are skipped.

    :param layers: (name, settings) pairs, lowest priority first
    :returns: The merged settings, and for each dotted key the name of the layer that set it
    """
    merged: dict[str, Any] = {}
    origin: dict[str, str] = {}

    def apply(target: dict[str, Any], values: Mapping[str, Any], layer: str, path: str) -> None:
        for key, value in values.items():
            dotted = f"{path}{key}"
            if value is UNSET:
                continue
            if isinstance(value, Mapping):
                apply(target.setdefault(key, {}), value, layer, f"{dotted}.")
            else:
                target[key] = value
                origin[dotted] = layer

    for layer, values in layers:
        apply(merged, values, layer, "")
    return merged, origin


def load_settings(
    path: Path | None = None,
    environ: Mapping[str, str] | None = None,
    *,
    batch_size: int | UNSET = UNSET,
    log_level: str | UNSET = UNSET,
) -> tuple[Settings, dict[str, str]]:
    """
    Build the settings from every layer and validate them once.

    :param path: A TOML file, if there is one
    :param environ: The environment; ``os.environ`` when omitted
    :param batch_size: A command line override, or ``UNSET``
    :param log_level: A command line override, or ``UNSET``
    :returns: The settings, and which layer set each value
    :raises ValueError: Listing every invalid setting at once
    """
    layers: list[tuple[str, Mapping[str, Any]]] = []
    if path is not None:
        layers.append((str(path), tomllib.loads(path.read_text(encoding="utf-8"))))
    layers.append(("environment", from_env(os.environ if environ is None else environ)))
    layers.append(("command line", {"batch_size": batch_size, "log_level": log_level}))
    merged, origin = merge(layers)
    try:
        settings = Settings.model_validate(merged)
    except ValidationError as error:
        problems = [f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in error.errors()]
        raise ValueError("invalid settings: " + "; ".join(problems)) from None
    return settings, origin


def demo() -> None:
    """Load settings from a file, the environment and a flag, and show where each value came from."""
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "kitchen.toml"
        path.write_text('kitchen = "Chez Nous"\nbatch_size = 1000\n\n[database]\npool_size = 10\n', encoding="utf-8")
        environ = {"KITCHEN_DATABASE__PASSWORD": "hunter2", "KITCHEN_DATABASE__POOL_SIZE": "8"}  # nosec B105  # demo
        settings, origin = load_settings(path, environ, batch_size=250)
    print(f"kitchen {settings.kitchen!r} from {origin['kitchen'].rsplit('/', 1)[-1]}")
    print(f"batch_size {settings.batch_size} from the {origin['batch_size']}; log_level {settings.log_level} (default)")
    print(f"database.pool_size {settings.database.pool_size} from the {origin['database.pool_size']}")
    dumped = settings.model_dump(mode="json")["database"]["password"]
    print(f"the password prints as {settings.database.password}, and dumps as {dumped}")
    try:
        load_settings(None, {"KITCHEN_BATCH_SIZE": "0", "KITCHEN_COLOUR": "blue"})
    except ValueError as error:
        print(error)
