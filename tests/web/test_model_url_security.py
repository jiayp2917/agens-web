from __future__ import annotations

import socket

import pytest
from fastapi.testclient import TestClient

from web.backend.app import create_app
from web.backend.auth import hash_invite_code

pytestmark = pytest.mark.xdist_group("pg_test_db")


def _registered_client(monkeypatch) -> tuple[TestClient, object]:
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "0")
    monkeypatch.setenv("MODEL_CONFIG_SECRET", "local-test-model-secret")
    app = create_app()
    app.state.service.db.create_invite_code(hash_invite_code("model-url-invite-123"))
    client = TestClient(app)
    response = client.post(
        "/api/auth/register",
        json={
            "username": "model_user",
            "password": "password-123",
            "invite_code": "model-url-invite-123",
        },
    )
    assert response.status_code == 200
    return client, app


@pytest.mark.parametrize(
    "base_url",
    [
        "http://api.deepseek.com/v1",
        "https://127.0.0.1/v1",
        "https://[::1]/v1",
        "https://metadata.google.internal/v1",
        "https://unapproved.example/v1",
    ],
)
def test_user_model_settings_reject_unsafe_base_url(monkeypatch, base_url: str) -> None:
    client, _app = _registered_client(monkeypatch)

    response = client.post(
        "/api/settings/model",
        json={
            "provider": "Custom",
            "base_url": base_url,
            "model": "custom-model",
            "api_key": "secret-user-key-123",
        },
    )

    assert response.status_code == 400
    assert "secret-user-key-123" not in response.text


def test_allowlisted_custom_model_url_is_saved_without_raw_key(monkeypatch) -> None:
    monkeypatch.setenv("AGENS_MODEL_BASE_URL_ALLOWLIST", "models.example.com")
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443))
        ],
    )
    client, app = _registered_client(monkeypatch)

    response = client.post(
        "/api/settings/model",
        json={
            "provider": "Custom",
            "base_url": "https://models.example.com/openai/v1/",
            "model": "custom-model",
            "api_key": "secret-user-key-123",
        },
    )

    assert response.status_code == 200
    assert response.json()["base_url"] == "https://models.example.com/openai/v1"
    assert "secret-user-key-123" not in response.text
    user = app.state.service.db.get_user_by_username("model_user")
    stored = app.state.service.db.get_user_model_config(user["id"])
    assert stored["api_key_encrypted"]
    assert stored["api_key_encrypted"] != "secret-user-key-123"


def test_allowlisted_custom_model_url_rejects_private_dns_on_save(monkeypatch) -> None:
    monkeypatch.setenv("AGENS_MODEL_BASE_URL_ALLOWLIST", "models.example.com")
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("169.254.169.254", 443))
        ],
    )
    client, _app = _registered_client(monkeypatch)

    response = client.post(
        "/api/settings/model",
        json={
            "provider": "Custom",
            "base_url": "https://models.example.com/openai/v1",
            "model": "custom-model",
            "api_key": "secret-user-key-123",
        },
    )

    assert response.status_code == 400
    assert "secret-user-key-123" not in response.text
