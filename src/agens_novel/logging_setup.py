"""Logging setup with a SecretRedactor filter.

A redactor sits on the root logger and rewrites any token-shaped strings
(``sk-...``) so they never appear in stdout/stderr/files, even if a careless
caller logs the wrong thing.
"""

from __future__ import annotations

import logging
import re
import sys
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


def setup_logging(level: int = logging.INFO) -> None:
    """Configure the root logger once. Idempotent."""
    root = logging.getLogger()
    # Remove any pre-existing handlers to avoid double-logging.
    for h in list(root.handlers):
        root.removeHandler(h)

    handler = logging.StreamHandler(sys.stderr)
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
    """Public helper for ad-hoc redaction in CLI/JSON output."""
    return SecretRedactor._scrub(text)
