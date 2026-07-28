"""Fixtures for PostgreSQL integration and browser tests only."""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, Engine, make_url


@pytest.fixture(scope="session", name="_pg_test_url")
def postgres_test_url() -> Iterator[str | None]:
    """Create one disposable PostgreSQL database for this pytest invocation."""
    configured_url = os.environ.get("TEST_DATABASE_URL")
    if not configured_url:
        yield None
        return

    source_url = make_url(configured_url)
    _validate_local_test_database(source_url)
    test_url, admin = _create_test_database(source_url)
    previous_database_url = os.environ.get("DATABASE_URL")
    url = test_url.render_as_string(hide_password=False)
    os.environ["DATABASE_URL"] = url
    try:
        command.upgrade(Config(str(Path(__file__).resolve().parents[1] / "alembic.ini")), "head")
        yield url
    finally:
        if previous_database_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous_database_url
        _drop_test_database(admin, test_url.database)
        admin.dispose()


def _validate_local_test_database(url: URL) -> None:
    if not url.drivername.startswith("postgresql"):
        raise RuntimeError("TEST_DATABASE_URL must use PostgreSQL")
    if url.host != "127.0.0.1" or url.port != 55432:
        raise RuntimeError("TEST_DATABASE_URL must point to 127.0.0.1:55432")


def _create_test_database(source_url: URL) -> tuple[URL, Engine]:
    database_name = f"agens_web_test_{uuid.uuid4().hex[:12]}"
    admin = create_engine(source_url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{database_name}"'))
    return source_url.set(database=database_name), admin


def _drop_test_database(admin: Engine, database_name: str | None) -> None:
    if not database_name:
        return
    with admin.connect() as conn:
        conn.execute(
            text(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = :database_name AND pid <> pg_backend_pid()"
            ),
            {"database_name": database_name},
        )
        conn.execute(text(f'DROP DATABASE IF EXISTS "{database_name}"'))
