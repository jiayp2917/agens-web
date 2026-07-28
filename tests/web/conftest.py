"""Web test DB isolation.

After the Option C consolidation the web layer is PostgreSQL-only, so every
web test runs against a single shared test database (TEST_DATABASE_URL).
This autouse fixture truncates all application tables before each test for
isolation; each test's ``create_app()`` then re-seeds catalogs on startup.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from tests.postgres_fixtures import postgres_test_url as _register_pg_test_url  # noqa: F401

_MUTATION_PATH = re.compile(
    r"^/api/sessions/(?P<session_id>[^/]+)/(?:start|choice|action|save|load|end)$"
)
_ORIGINAL_POST = TestClient.post


def _response_version(response: Any) -> int | None:
    if getattr(response, "status_code", 500) >= 400:
        return None
    try:
        body = response.json()
    except (TypeError, ValueError):
        return None
    if not isinstance(body, dict):
        return None
    session = body.get("session")
    source = session if isinstance(session, dict) else body
    version = source.get("version")
    return int(version) if isinstance(version, int) else None


def _mutation_aware_post(self: TestClient, url: Any, *args: Any, **kwargs: Any):
    match = _MUTATION_PATH.match(str(url))
    if match:
        payload = dict(kwargs.get("json") or {})
        versions = getattr(self, "_agens_session_versions", {})
        session_id = match.group("session_id")
        payload.setdefault("request_id", str(uuid.uuid4()))
        payload.setdefault("expected_version", int(versions.get(session_id, 0)))
        kwargs["json"] = payload
    response = _ORIGINAL_POST(self, url, *args, **kwargs)
    version = _response_version(response)
    if version is not None:
        body = response.json()
        session = body.get("session") if isinstance(body, dict) else None
        source = session if isinstance(session, dict) else body
        session_id = source.get("session_id") if isinstance(source, dict) else None
        if session_id:
            versions = dict(getattr(self, "_agens_session_versions", {}))
            versions[str(session_id)] = version
            self._agens_session_versions = versions
    return response


@pytest.fixture(autouse=True)
def _mutation_metadata_client(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep API tests concise while production mutation fields stay required."""
    monkeypatch.setattr(TestClient, "post", _mutation_aware_post)

# All application tables (alembic_version is intentionally excluded).
_TEST_TABLES = (
    "users",
    "invite_codes",
    "sessions",
    "session_mutations",
    "saves",
    "model_config",
    "user_model_configs",
    "catalog_talents",
    "catalog_family_backgrounds",
    "catalog_spirit_roots",
    "catalog_difficulties",
    "catalog_story_seeds",
    "run_achievements",
    "account_rewards",
    "legacy_bonuses",
    "game_runs",
    "game_turns",
    "player_progress",
)


@pytest.fixture(autouse=True)
def _isolated_pg_db(_pg_test_url, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Point create_app() at the shared test DB and truncate before each test."""
    url = _pg_test_url
    if url is None:
        raise RuntimeError("tests/web requires TEST_DATABASE_URL for 127.0.0.1:55432")
    monkeypatch.setenv("DATABASE_URL", url)
    engine = create_engine(url)
    try:
        table_list = ", ".join(_TEST_TABLES)
        with engine.begin() as conn:
            conn.execute(text(f"TRUNCATE TABLE {table_list} RESTART IDENTITY CASCADE"))
    finally:
        engine.dispose()
    yield
