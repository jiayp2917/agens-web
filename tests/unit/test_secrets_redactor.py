"""SecretRedactor: sk-... tokens must be scrubbed from log output."""

from __future__ import annotations

import logging

from agens_novel.logging_setup import SafeStreamHandler, SecretRedactor, redact, setup_logging


SAMPLE_SECRET = "sk-oDA3g9FPycylI24SIIQXwlkqB3WGEWwtU0TkpTFpkWemurQW"


def test_redact_replaces_sk_token() -> None:
    out = redact(f"hello {SAMPLE_SECRET} world")
    assert SAMPLE_SECRET not in out
    assert "sk-***" in out


def test_redact_handles_env_ref() -> None:
    out = redact("AGNES_API_KEY=sk-secret-value-12345xyz")
    assert "sk-secret-value-12345xyz" not in out
    assert "AGNES_API_KEY=***" in out


def test_redact_passthrough_normal_text() -> None:
    s = "this is a normal log line"
    assert redact(s) == s


def test_logging_filter_scrubs_message(caplog) -> None:
    setup_logging(level=logging.INFO)
    log = logging.getLogger("test_redact")
    log.setLevel(logging.INFO)
    # Attach caplog handler + a SecretRedactor filter to it, so the same
    # scrub step the production logger applies is exercised here.
    from agens_novel.logging_setup import SecretRedactor
    caplog.handler.addFilter(SecretRedactor())
    log.addHandler(caplog.handler)
    log.propagate = False
    try:
        log.info("calling with key %s", SAMPLE_SECRET)
    finally:
        log.removeHandler(caplog.handler)
        caplog.handler.filters.clear()
    text = caplog.text
    assert SAMPLE_SECRET not in text, f"Secret leaked in caplog: {text}"
    assert "sk-***" in text


class BrokenStream:
    def write(self, text: str) -> None:
        raise OSError(22, "Invalid argument")

    def flush(self) -> None:
        raise OSError(22, "Invalid argument")


def test_logging_broken_stream_does_not_raise() -> None:
    setup_logging(level=logging.INFO, stream=BrokenStream())
    log = logging.getLogger("test_broken_stream")

    log.info("this must not surface a logging stream failure")


def test_later_broken_stream_handler_does_not_raise() -> None:
    setup_logging(level=logging.INFO)
    root = logging.getLogger()
    handler = logging.StreamHandler(BrokenStream())
    root.addHandler(handler)
    try:
        logging.getLogger("test_later_broken_stream").info("safe")
    finally:
        root.removeHandler(handler)


def test_setup_logging_installs_safe_redacting_handler() -> None:
    setup_logging(level=logging.INFO)
    root = logging.getLogger()

    assert logging.raiseExceptions is False
    assert any(isinstance(handler, SafeStreamHandler) for handler in root.handlers)
    assert any(
        isinstance(filter_, SecretRedactor)
        for handler in root.handlers
        for filter_ in handler.filters
    )
