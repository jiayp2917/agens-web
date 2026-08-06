"""Fixtures for PostgreSQL integration and browser tests on the local database."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.engine import make_url

from web.backend.database import resolve_database_url
from web.backend.local_postgres_safety import require_loopback_postgres_url


@pytest.fixture(scope="session", name="_pg_url")
def postgres_database_url() -> Iterator[str]:
    """Use the one resolved local PostgreSQL database for database tests."""
    configured_url = resolve_database_url()

    require_loopback_postgres_url(make_url(configured_url))
    command.upgrade(Config(str(Path(__file__).resolve().parents[1] / "alembic.ini")), "head")
    yield configured_url
