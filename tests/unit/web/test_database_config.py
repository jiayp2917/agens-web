"""Local and production database URL resolution."""

from __future__ import annotations

import pytest

from web.backend.database import resolve_database_url


def test_local_database_url_defaults_to_the_established_local_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("AGENS_ENV", raising=False)

    assert resolve_database_url() == "postgresql+psycopg://jiayp2917@127.0.0.1:5432/agens_web"


def test_explicit_database_url_overrides_the_local_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://configured@127.0.0.1/example")

    assert resolve_database_url() == "postgresql+psycopg://configured@127.0.0.1/example"


def test_production_requires_an_explicit_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("AGENS_ENV", "production")

    with pytest.raises(RuntimeError, match="DATABASE_URL is required"):
        resolve_database_url()
