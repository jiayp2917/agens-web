"""Logging setup with a SecretRedactor filter.

A redactor sits on the root logger and rewrites any token-shaped strings
(``sk-...``) so they never appear in stdout/stderr/files, even if a careless
caller logs the wrong thing.
"""

from __future__ import annotations

import logging
import re
import sys
from typing import IO
from typing import Final

# Matches: sk-XXXX (any non-whitespace chars, common API key shape)
# Tuned to be conservative — match tokens that are at least 8 chars long.
_SECRET_PATTERN: Final[re.Pattern[str]] = re.compile(r"sk-[A-Za-z0-9_\-]{8,}")

# Also redact env-style references: "AGNES_API_KEY=..." even if value is missing
_ENV_REF_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"(AGNES_API_KEY\s*=\s*)([^\s,;'\"]+)", re.IGNORECASE
)


class SecretRedactor(logging.Filter):
    """Logging filter that replaces secret-shaped strings with '***'."""

    def filter(self, record: logging.LogRecord) -> bool:
        # Redact in the message itself.
        if isinstance(record.msg, str):
            record.msg = self._scrub(record.msg)
        # Redact in any formatted args.
        if record.args:
            scrubbed_args = tuple(
                self._scrub(a) if isinstance(a, str) else a for a in record.args
            )
            record.args = scrubbed_args
        return True

    @staticmethod
    def _scrub(text: str) -> str:
        text = _SECRET_PATTERN.sub("sk-***", text)
        text = _ENV_REF_PATTERN.sub(r"\1***", text)
        return text


_DEFAULT_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"


class SafeStreamHandler(logging.StreamHandler):
    """Stream handler that never lets a broken stderr/stdout break gameplay."""

    def handleError(self, record: logging.LogRecord) -> None:  # noqa: N802
        # Python's default handleError writes another traceback to sys.stderr
        # when logging.raiseExceptions is true. On Windows that can
        # recurse if stderr itself is the broken stream, so this is deliberately
        # silent.
        return None


def _default_stream() -> IO[str] | None:
    return sys.__stderr__ or sys.stderr


def setup_logging(
    level: int = logging.INFO,
    *,
    stream: IO[str] | None = None,
) -> None:
    """Configure the root logger once. Idempotent."""
    logging.raiseExceptions = False
    root = logging.getLogger()
    # Remove any pre-existing handlers to avoid double-logging.
    for h in list(root.handlers):
        root.removeHandler(h)

    handler = SafeStreamHandler(stream if stream is not None else _default_stream())
    handler.setFormatter(logging.Formatter(_DEFAULT_FORMAT))
    handler.addFilter(SecretRedactor())
    root.addHandler(handler)
    root.setLevel(level)

    # Tame noisy third-party loggers.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("langchain").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)


def redact(text: str) -> str:
    """Public helper for ad-hoc redaction in JSON output."""
    return SecretRedactor._scrub(text)
