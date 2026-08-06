"""Pure unit tests for the destructive local PostgreSQL guard."""

from __future__ import annotations

import pytest
from sqlalchemy.engine import make_url

from web.backend.local_postgres_safety import require_loopback_postgres_url


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "[::1]"])
def test_loopback_postgres_urls_are_accepted(host: str) -> None:
    url = make_url(f"postgresql+psycopg://tester:password@{host}:5432/agens_web")

    assert require_loopback_postgres_url(url) is url


@pytest.mark.parametrize(
    "url",
    [
        "postgresql+psycopg://tester:password@db.internal:5432/agens_web",
        "sqlite:///agens_web.db",
    ],
)
def test_non_loopback_or_non_postgres_urls_are_rejected(url: str) -> None:
    with pytest.raises(RuntimeError):
        require_loopback_postgres_url(make_url(url))
