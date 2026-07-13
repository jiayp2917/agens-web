"""Production runtime configuration must fail closed before app startup."""

from __future__ import annotations

import pytest

from web.backend.app import validate_runtime_config


def _valid_production_env(monkeypatch: pytest.MonkeyPatch) -> None:
    values = {
        "AGENS_ENV": "production",
        "DATABASE_URL": "postgresql+psycopg://agens_user:strong-password@postgres:5432/agens_web",
        "INVITE_ADMIN_CODE": "admin-bootstrap-code-2026",
        "AGENS_ALLOWED_ORIGINS": "https://game.jiayp2917.xyz",
        "MODEL_CONFIG_SECRET": "model-config-secret-with-more-than-32-characters",
        "SESSION_SECRET": "session-secret-with-more-than-32-characters",
        "SESSION_COOKIE_SECURE": "1",
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv("AGNES_API_KEY", raising=False)


def test_development_runtime_does_not_require_production_values(monkeypatch) -> None:
    monkeypatch.setenv("AGENS_ENV", "development")

    validate_runtime_config()


def test_valid_production_runtime_passes(monkeypatch) -> None:
    _valid_production_env(monkeypatch)

    validate_runtime_config()


def test_production_rejects_validation_seed(monkeypatch) -> None:
    _valid_production_env(monkeypatch)
    monkeypatch.setenv("AGENS_VALIDATION_SEED", "golden-route")

    with pytest.raises(RuntimeError, match="AGENS_VALIDATION_SEED"):
        validate_runtime_config()


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("DATABASE_URL", "postgresql+psycopg://agens_user:CHANGE_ME@postgres:5432/agens_web"),
        ("INVITE_ADMIN_CODE", "CHANGE_ME"),
        ("MODEL_CONFIG_SECRET", "CHANGE_ME_WITH_AT_LEAST_32_RANDOM_CHARACTERS"),
        ("SESSION_SECRET", "dev-session-secret-change-me"),
        ("AGNES_API_KEY", "CHANGE_ME"),
    ],
)
def test_production_rejects_placeholder_values(monkeypatch, name: str, value: str) -> None:
    _valid_production_env(monkeypatch)
    monkeypatch.setenv(name, value)

    with pytest.raises(RuntimeError, match="placeholder"):
        validate_runtime_config()


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("INVITE_ADMIN_CODE", "short"),
        ("MODEL_CONFIG_SECRET", "short-secret"),
        ("SESSION_SECRET", "short-secret"),
    ],
)
def test_production_rejects_weak_secrets(monkeypatch, name: str, value: str) -> None:
    _valid_production_env(monkeypatch)
    monkeypatch.setenv(name, value)

    with pytest.raises(RuntimeError, match="sufficiently long"):
        validate_runtime_config()


def test_production_rejects_insecure_cookie(monkeypatch) -> None:
    _valid_production_env(monkeypatch)
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "0")

    with pytest.raises(RuntimeError, match="SESSION_COOKIE_SECURE"):
        validate_runtime_config()


def test_production_rejects_non_https_origin(monkeypatch) -> None:
    _valid_production_env(monkeypatch)
    monkeypatch.setenv("AGENS_ALLOWED_ORIGINS", "http://game.jiayp2917.xyz")

    with pytest.raises(RuntimeError, match="HTTPS"):
        validate_runtime_config()
