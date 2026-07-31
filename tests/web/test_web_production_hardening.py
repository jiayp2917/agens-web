"""Production-hardening tests restored during the test_web_api.py split — AGENS_ENV config, CORS/origin, openapi hiding, runtime DDL refusal."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.web.api_fixtures import _create_invite
from web.backend.app import create_app
from web.backend.security import InMemoryRateLimiter

pytestmark = pytest.mark.xdist_group("pg_test_db")


def _set_production_runtime_services(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENS_RATE_LIMIT_BACKEND", "redis")
    monkeypatch.setenv("AGENS_RATE_LIMIT_REDIS_URL", "redis://redis:6379/0")
    monkeypatch.setattr("web.backend.app.create_rate_limiter", InMemoryRateLimiter)


def test_production_rejects_default_session_secret(tmp_path: Path, monkeypatch) -> None:
    # Production mode is driven by AGENS_ENV (not DATABASE_BACKEND) since the
    # Option C consolidation made PostgreSQL the only backend.
    monkeypatch.setenv("AGENS_ENV", "production")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://agens_user:test@postgres:5432/agens_web")
    monkeypatch.setenv("INVITE_ADMIN_CODE", "admin-invite-123")
    monkeypatch.delenv("SESSION_SECRET", raising=False)
    _set_production_runtime_services(monkeypatch)

    with pytest.raises(RuntimeError, match="SESSION_SECRET"):
        create_app()

    monkeypatch.setenv("SESSION_SECRET", "dev-session-secret-change-me")
    with pytest.raises(RuntimeError, match="SESSION_SECRET"):
        create_app()


def test_production_requires_allowed_origins(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AGENS_ENV", "production")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://agens_user:test@postgres:5432/agens_web")
    monkeypatch.setenv("INVITE_ADMIN_CODE", "admin-invite-123")
    monkeypatch.setenv("SESSION_SECRET", "test-session-secret-with-more-than-32-characters")
    monkeypatch.setenv("MODEL_CONFIG_SECRET", "test-model-config-secret-with-more-than-32-characters")
    monkeypatch.delenv("AGENS_ALLOWED_ORIGINS", raising=False)
    _set_production_runtime_services(monkeypatch)

    with pytest.raises(RuntimeError, match="AGENS_ALLOWED_ORIGINS"):
        create_app()


def test_production_hides_openapi_and_rejects_untrusted_host(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AGENS_ENV", "production")
    monkeypatch.setenv("DATABASE_URL", os.environ["TEST_DATABASE_URL"])
    monkeypatch.setenv("INVITE_ADMIN_CODE", "admin-invite-123")
    monkeypatch.setenv("SESSION_SECRET", "test-session-secret-with-more-than-32-characters")
    monkeypatch.setenv("AGENS_ALLOWED_ORIGINS", "https://game.example.test")
    monkeypatch.setenv("MODEL_CONFIG_SECRET", "test-model-config-secret-with-more-than-32-characters")
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "1")
    _set_production_runtime_services(monkeypatch)
    app = create_app()

    client = TestClient(app, base_url="https://game.example.test")
    assert client.get("/api/health").status_code == 200
    assert client.get("/docs").status_code == 404
    assert client.get("/redoc").status_code == 404
    assert client.get("/openapi.json").status_code == 404

    blocked = TestClient(app, base_url="https://evil.example.test")
    assert blocked.get("/api/health").status_code == 400


@pytest.mark.parametrize("environment", ["prod", "production"])
def test_production_aliases_reject_runtime_auto_ddl(monkeypatch, environment: str) -> None:
    from web.backend.database_postgres import PostgresWebDatabase

    monkeypatch.setenv("AGENS_ENV", environment)
    monkeypatch.setenv("AGENS_PG_AUTO_DDL", "1")

    with pytest.raises(RuntimeError, match="prod/production"):
        PostgresWebDatabase(os.environ["TEST_DATABASE_URL"])


def test_origin_mismatch_is_rejected_for_state_changes(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "0")
    monkeypatch.setenv("AGENS_ALLOWED_ORIGINS", "https://game.example.test")
    app = create_app()
    client = TestClient(app, base_url="https://game.example.test")
    _create_invite(app)
    client.post(
        "/api/auth/register",
        json={"username": "player", "password": "password-123", "invite_code": "invite-code-123"},
        headers={"Origin": "https://game.example.test"},
    )

    blocked = client.post(
        "/api/sessions",
        json={},
        headers={"Origin": "https://evil.example.test"},
    )
    assert blocked.status_code == 403

    allowed = client.post(
        "/api/sessions",
        json={},
        headers={"Origin": "https://game.example.test"},
    )
    assert allowed.status_code == 200
