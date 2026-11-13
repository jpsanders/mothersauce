"""
Logging: structured, contextual, and configured in one place.

Libraries log; applications decide where the log goes. A module asks for ``logging.getLogger(__name__)`` and never
calls ``basicConfig``, which belongs to the program's entry point, once. Pass values as arguments,
``logger.info("loaded %d rows", n)``, instead of building the message yourself: the formatting is then skipped when
the level is off, and log tools can group every "loaded %d rows" event together.

For machines, write JSON lines: one object per event with stable keys, so a search can filter on ``run_id`` instead
of parsing prose. Context such as the run id lives in a ``ContextVar`` and a ``Filter`` stamps it on every record,
including records from code that has never heard of it. Each asyncio task sees its own value; a new thread starts
with an empty context, so submit work to a pool with ``contextvars.copy_context().run`` when its logs need the run id.
``extra=`` adds fields to a single event. A second filter masks the usual shapes of a secret in the message, in the
extra fields and in the traceback; no filter catches every secret, so never log one on purpose.
"""

import io
import json
import logging
import logging.config
import re
import sys
from collections.abc import Generator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any, TextIO

__all__ = ["ContextFilter", "JsonFormatter", "RedactSecrets", "configure", "demo", "log_context", "run_id", "source"]

run_id: ContextVar[str] = ContextVar("run_id", default="-")
source: ContextVar[str] = ContextVar("source", default="-")

# Every attribute a plain LogRecord has; anything else on a record came from extra= and belongs in the JSON.
_STANDARD = set(vars(logging.LogRecord("", 0, "", 0, "", None, None))) | {"message", "asctime", "run_id", "source"}


class ContextFilter(logging.Filter):
    """Stamp the current run id and source on every record that passes through the handler."""

    def filter(self, record: logging.LogRecord) -> bool:
        """
        Add the context to a record.

        :param record: The record
        :returns: Always True: this filter adds, it never drops
        """
        record.run_id = run_id.get()
        record.source = source.get()
        return True


_SECRET = r"password|passwd|pwd|secret|token|api[_ -]?key|credential"  # nosec B105  # names to look for, no secret


class RedactSecrets(logging.Filter):
    """
    Mask secrets before any handler writes them: ``db_password=x``, ``"token": "x"``, ``API_KEY: x`` and the like.

    A key counts as secret when it contains a secret word anywhere, quoted or not; its value is masked up to the next
    space, quote or separator. ``extra=`` fields with such names are masked whole.
    """

    PATTERN = re.compile(r"""(?i)(["']?)([\w.-]*(?:""" + _SECRET + r""")[\w.-]*)\1(\s*[=:]\s*)(["']?)[^\s"',;}]+""")
    SECRET_KEY = re.compile(_SECRET, re.I)

    @classmethod
    def scrub(cls, text: str) -> str:
        """
        Mask every secret value in a text.

        >>> RedactSecrets.scrub('db_password=hunter2 {"token": "abc"}')
        'db_password=*** {"token": "***"}'

        :param text: Any text, such as a message or a traceback
        :returns: The text with secret values replaced by ``***``
        """
        return cls.PATTERN.sub(r"\1\2\1\3\4***", text)

    def filter(self, record: logging.LogRecord) -> bool:
        """
        Redact the message and any secret ``extra=`` field in place.

        :param record: The record
        :returns: Always True: the record is kept, minus the secrets
        """
        message = record.getMessage()
        redacted = self.scrub(message)
        if redacted != message:
            record.msg, record.args = redacted, None
        for name in [n for n in vars(record) if n not in _STANDARD and self.SECRET_KEY.search(n)]:
            setattr(record, name, "***")
        return True


class JsonFormatter(logging.Formatter):
    """One JSON object per line, with stable keys first and any ``extra=`` fields after them."""

    def format(self, record: logging.LogRecord) -> str:
        """
        Render a record as one line of JSON.

        :param record: The record
        :returns: The JSON text
        """
        event: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname.lower(),
            "logger": record.name,
            "msg": record.getMessage(),
            "run_id": getattr(record, "run_id", "-"),
            "source": getattr(record, "source", "-"),
        }
        event.update({k: v for k, v in vars(record).items() if k not in _STANDARD})
        if record.exc_info:
            event["exc"] = RedactSecrets.scrub(self.formatException(record.exc_info))
        return json.dumps(event, default=str)


def configure(level: str = "INFO", json_lines: bool = True, stream: TextIO | None = None, logger: str = "") -> None:
    """
    Configure logging once, at the program's entry point, with ``dictConfig``.

    ``disable_existing_loggers`` is False, because the default silences every logger created before this call,
    which is how libraries' warnings go missing.

    :param level: The lowest level to emit
    :param json_lines: JSON for machines, or plain text for a terminal
    :param stream: Where to write; standard error by default
    :param logger: The logger to configure; the root logger by default
    """
    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "filters": {"context": {"()": ContextFilter}, "redact": {"()": RedactSecrets}},
            "formatters": {
                "json": {"()": JsonFormatter},
                "text": {"format": "%(asctime)s %(levelname)-7s %(name)s [%(run_id)s] %(message)s"},
            },
            "handlers": {
                "main": {
                    "class": "logging.StreamHandler",
                    "stream": stream or sys.stderr,
                    "formatter": "json" if json_lines else "text",
                    "filters": ["redact", "context"],
                }
            },
            "loggers": {logger: {"handlers": ["main"], "level": level, "propagate": not logger}},
        }
    )


@contextmanager
def log_context(run: str | None = None, src: str | None = None) -> Generator[None]:
    """
    Set the run id and the source for everything logged inside the block, then put the old values back.

    :param run: The run id
    :param src: The source being processed
    :yields: Nothing; log inside the block
    """
    tokens = [var.set(value) for var, value in ((run_id, run), (source, src)) if value is not None]
    try:
        yield
    finally:
        for token in reversed(tokens):
            token.var.reset(token)


def demo() -> None:
    """Log a short load as JSON lines: context from a ContextVar, extra fields, a redacted secret, an error."""
    stream = io.StringIO()
    configure(stream=stream, logger="kitchen")
    log = logging.getLogger("kitchen.loader")
    with log_context(run="run-0042", src="lunch.csv"):
        log.info("loaded %d rows", 120, extra={"rows": 120, "seconds": 0.084})
        log.warning("connecting with password=hunter2 to the till")
        try:
            1 / 0
        except ZeroDivisionError:
            log.exception("could not compute the average ticket")
    log.debug("not shown: below the configured level")
    for line in stream.getvalue().splitlines():
        event = json.loads(line)
        shown = {k: event[k] for k in ("level", "msg", "run_id", "source", "rows") if k in event}
        print(json.dumps(shown) + (" + a traceback in 'exc'" if "exc" in event else ""))
    logging.getLogger("kitchen").handlers.clear()
