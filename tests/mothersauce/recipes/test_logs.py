import io
import json
import logging
from collections.abc import Iterator
from typing import Any

import pytest

from mothersauce.recipes.logs import RedactSecrets, configure, demo, log_context, run_id, source

NAME = "mothersauce.test.logs"


@pytest.fixture
def stream() -> Iterator[io.StringIO]:
    out = io.StringIO()
    configure(stream=out, logger=NAME, level="DEBUG")
    yield out
    logging.getLogger(NAME).handlers.clear()


def events(stream: io.StringIO) -> list[dict[str, Any]]:
    return [json.loads(line) for line in stream.getvalue().splitlines()]


def test_json_lines_with_stable_keys(stream: io.StringIO) -> None:
    logging.getLogger(f"{NAME}.child").info("loaded %d rows", 3)
    (event,) = events(stream)
    assert list(event)[:6] == ["ts", "level", "logger", "msg", "run_id", "source"]
    assert event["msg"] == "loaded 3 rows" and event["logger"] == f"{NAME}.child"
    assert event["ts"].endswith("+00:00")


def test_context_is_stamped_and_reset(stream: io.StringIO) -> None:
    log = logging.getLogger(NAME)
    with log_context(run="r1", src="a.csv"):
        with log_context(src="b.csv"):
            log.info("inner")
        log.info("outer")
    log.info("after")
    assert [(e["run_id"], e["source"]) for e in events(stream)] == [("r1", "b.csv"), ("r1", "a.csv"), ("-", "-")]
    assert run_id.get() == "-" and source.get() == "-"


def test_extra_fields_are_kept(stream: io.StringIO) -> None:
    logging.getLogger(NAME).info("done", extra={"rows": 5, "table": "tickets"})
    (event,) = events(stream)
    assert event["rows"] == 5 and event["table"] == "tickets"


def test_exceptions_carry_the_traceback(stream: io.StringIO) -> None:
    try:
        raise KeyError("dish")
    except KeyError:
        logging.getLogger(NAME).exception("lookup failed")
    (event,) = events(stream)
    assert event["level"] == "error" and "KeyError: 'dish'" in event["exc"]


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("password=hunter2", "password=***"),
        ("API_KEY: abc123 and more", "API_KEY: *** and more"),
        ("token = xyz", "token = ***"),
        ("the secret sauce is butter", "the secret sauce is butter"),
    ],
)
def test_redact_secrets(message: str, expected: str) -> None:
    record = logging.LogRecord("t", logging.INFO, __file__, 1, message, None, None)
    assert RedactSecrets().filter(record)
    assert record.getMessage() == expected


def test_redaction_applies_to_formatted_arguments(stream: io.StringIO) -> None:
    logging.getLogger(NAME).warning("login with %s", "password=hunter2")
    assert events(stream)[0]["msg"] == "login with password=***"


def test_text_format_for_terminals() -> None:
    out = io.StringIO()
    configure(stream=out, logger=f"{NAME}.text", json_lines=False)
    with log_context(run="r9"):
        logging.getLogger(f"{NAME}.text").warning("hot pass")
    logging.getLogger(f"{NAME}.text").handlers.clear()
    assert out.getvalue().rstrip().endswith(f"WARNING {NAME}.text [r9] hot pass")


def test_level_filters_before_formatting(stream: io.StringIO) -> None:
    logging.getLogger(NAME).setLevel(logging.WARNING)
    logging.getLogger(NAME).info("hidden %s", object())
    assert events(stream) == []


def test_demo_runs(capsys: pytest.CaptureFixture[str]) -> None:
    demo()
    out = capsys.readouterr().out
    assert '"msg": "connecting with password=*** to the till"' in out
    assert "+ a traceback in 'exc'" in out
