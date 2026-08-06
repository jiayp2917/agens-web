"""Fixtures for PostgreSQL integration and browser tests on the local database."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.engine import make_url

from web.backend.local_postgres_safety import require_loopback_postgres_url


@pytest.fixture(scope="session", name="_pg_url")
def postgres_database_url() -> Iterator[str]:
    """Use the one configured local PostgreSQL database for database tests."""
    configured_url = os.environ.get("DATABASE_URL", "").strip()
    if not configured_url:
        raise RuntimeError("PostgreSQL tests require DATABASE_URL")

    require_loopback_postgres_url(make_url(configured_url))
    command.upgrade(Config(str(Path(__file__).resolve().parents[1] / "alembic.ini")), "head")
    yield configured_url
