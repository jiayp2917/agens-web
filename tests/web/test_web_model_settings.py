"""Model-settings tests extracted from test_web_api.py — per-user key encrypt/read/clear/isolate."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from tests.web.api_fixtures import (
    _create_invite,
    _login_user,
    _model_payload,
    _use_public_model_dns,
)
from web.backend.app import create_app

pytestmark = pytest.mark.xdist_group("pg_test_db")


def test_user_model_settings_save_read_clear_and_encrypts_key(tmp_path: Path, monkeypatch) -> None:
    _use_public_model_dns(monkeypatch)
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "0")
    monkeypatch.setenv("MODEL_CONFIG_SECRET", "test-model-config-secret")
    app = create_app()
    client = TestClient(app)
    _create_invite(app)
    user = _login_user(client, "player", "invite-code-123")

    initial = client.get("/api/settings/model")
    assert initial.status_code == 200
    assert initial.json()["source"] == "system"

    raw_key = "test-user-key-123456789"
    saved = client.post("/api/settings/model", json=_model_payload(raw_key))
    assert saved.status_code == 200
    body = saved.json()
    assert body["source"] == "user"
    assert body["provider"] == "DeepSeek"
    assert body["api_key_set"] is True
    assert body["api_key_masked"] != raw_key
    assert raw_key not in json.dumps(body, ensure_ascii=False)

    read_back = client.get("/api/settings/model").json()
    assert read_back["source"] == "user"
    assert raw_key not in json.dumps(read_back, ensure_ascii=False)

    with app.state.service.db.engine.connect() as conn:
        row = conn.execute(
            text("SELECT user_id, api_key_encrypted, api_key_masked FROM user_model_configs")
        ).mappings().one()
    assert row["user_id"] == user["id"]
    assert row["api_key_encrypted"].startswith("fernet:")
    assert raw_key not in row["api_key_encrypted"]
    assert raw_key not in row["api_key_masked"]

    cleared = client.delete("/api/settings/model")
    assert cleared.status_code == 200
    assert cleared.json()["source"] == "system"
    assert app.state.service.db.get_user_model_config(user["id"]) is None


def test_model_settings_are_isolated_per_user(tmp_path: Path, monkeypatch) -> None:
    _use_public_model_dns(monkeypatch)
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "0")
    monkeypatch.setenv("MODEL_CONFIG_SECRET", "test-model-config-secret")
    app = create_app()
    _create_invite(app, "invite-a-123")
    _create_invite(app, "invite-b-123")

    client_a = TestClient(app)
    user_a = _login_user(client_a, "player_a", "invite-a-123")
    client_a.post("/api/settings/model", json=_model_payload("test-user-a-key-123456"))

    client_b = TestClient(app)
    user_b = _login_user(client_b, "player_b", "invite-b-123")
    assert client_b.get("/api/settings/model").json()["source"] == "system"
    client_b.post("/api/settings/model", json=_model_payload("test-user-b-key-123456"))

    assert client_a.get("/api/settings/model").json()["source"] == "user"
    assert client_b.get("/api/settings/model").json()["source"] == "user"
    assert app.state.service.db.get_user_model_config(user_a["id"])["api_key_encrypted"] != app.state.service.db.get_user_model_config(user_b["id"])["api_key_encrypted"]


def test_user_model_settings_reject_empty_initial_key_and_keep_existing_key(tmp_path: Path, monkeypatch) -> None:
    _use_public_model_dns(monkeypatch)
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "0")
    monkeypatch.setenv("MODEL_CONFIG_SECRET", "test-model-config-secret")
    monkeypatch.setenv("AGNES_API_KEY", "test-system-key-123456")
    app = create_app()
    client = TestClient(app)
    _create_invite(app)
    user = _login_user(client, "player_empty_key", "invite-code-123")

    rejected = client.post("/api/settings/model", json=_model_payload(""))
    assert rejected.status_code == 400
    assert client.get("/api/settings/model").json()["source"] == "system"
    assert app.state.service.db.get_user_model_config(user["id"]) is None

    saved = client.post("/api/settings/model", json=_model_payload("test-user-key-123456"))
    assert saved.status_code == 200
    encrypted = app.state.service.db.get_user_model_config(user["id"])["api_key_encrypted"]

    updated = client.post(
        "/api/settings/model",
        json={
            "provider": "Qwen",
            "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "model": "qwen-plus",
            "api_key": "",
        },
    )
    assert updated.status_code == 200
    assert updated.json()["source"] == "user"
    assert updated.json()["api_key_set"] is True
    assert app.state.service.db.get_user_model_config(user["id"])["api_key_encrypted"] == encrypted
    runtime = app.state.service._model_config.runtime(user["id"])
    assert runtime["api_key"] == "test-user-key-123456"
    assert runtime["provider"] == "Qwen"


def test_guest_model_settings_rejected_and_admin_system_endpoint_is_admin_only(tmp_path: Path, monkeypatch) -> None:
    _use_public_model_dns(monkeypatch)
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "0")
    monkeypatch.setenv("MODEL_CONFIG_SECRET", "test-model-config-secret")
    monkeypatch.setenv("INVITE_ADMIN_CODE", "admin-invite-123")
    app = create_app()
    guest = TestClient(app)
    assert guest.get("/api/settings/model").status_code == 401
    assert guest.post("/api/settings/model", json=_model_payload("test-guest-key-123456")).status_code == 401
    assert guest.delete("/api/settings/model").status_code == 401
    assert guest.get("/api/admin/settings/model").status_code == 401

    _create_invite(app, "normal-invite-123")
    user_client = TestClient(app)
    _login_user(user_client, "normal_user", "normal-invite-123")
    assert user_client.get("/api/admin/settings/model").status_code == 403
    assert user_client.post("/api/admin/settings/model", json=_model_payload("test-user-key-123456")).status_code == 403

    admin_client = TestClient(app)
    admin_client.post(
        "/api/auth/register",
        json={"username": "admin", "password": "password-123", "invite_code": "admin-invite-123"},
    )
    saved = admin_client.post("/api/admin/settings/model", json=_model_payload("test-admin-key-123456"))
    assert saved.status_code == 200
    assert saved.json()["source"] == "system"
    assert saved.json()["api_key_set"] is True
    assert "test-admin-key" not in json.dumps(saved.json(), ensure_ascii=False)


def test_model_settings_missing_secret_fails_closed(tmp_path: Path, monkeypatch) -> None:
    _use_public_model_dns(monkeypatch)
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "0")
    monkeypatch.setenv("MODEL_CONFIG_SECRET", "test-model-config-secret")
    monkeypatch.setenv("AGNES_API_KEY", "test-env-key-must-not-be-used")
    app = create_app()
    client = TestClient(app)
    _create_invite(app)
    user = _login_user(client, "player", "invite-code-123")
    client.post("/api/settings/model", json=_model_payload("test-user-key-123456"))

    monkeypatch.delenv("MODEL_CONFIG_SECRET", raising=False)
    runtime = app.state.service._model_config.runtime(user["id"])
    assert runtime["source"] == "user"
    assert runtime["api_key"] == ""
    assert runtime["api_key_set"] is False
    assert runtime["key_error"]

    rejected = client.post("/api/settings/model", json=_model_payload("test-new-user-key-123456"))
    assert rejected.status_code == 400


def test_runtime_model_config_uses_current_user_without_env_pollution(tmp_path: Path, monkeypatch) -> None:
    _use_public_model_dns(monkeypatch)
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "0")
    monkeypatch.setenv("MODEL_CONFIG_SECRET", "test-model-config-secret")
    monkeypatch.setenv("AGNES_API_KEY", "test-env-key-should-not-win")
    app = create_app()
    _create_invite(app, "invite-a-123")
    _create_invite(app, "invite-b-123")

    client_a = TestClient(app)
    user_a = _login_user(client_a, "player_a", "invite-a-123")
    client_a.post("/api/settings/model", json=_model_payload("test-user-a-key-123456"))

    client_b = TestClient(app)
    user_b = _login_user(client_b, "player_b", "invite-b-123")
    client_b.post("/api/settings/model", json=_model_payload("test-user-b-key-123456"))

    config_a = app.state.service._model_config.runtime(user_a["id"])
    config_b = app.state.service._model_config.runtime(user_b["id"])
    assert config_a["api_key"] == "test-user-a-key-123456"
    assert config_b["api_key"] == "test-user-b-key-123456"
    assert os.environ["AGNES_API_KEY"] == "test-env-key-should-not-win"
    assert config_a["api_key"] != config_b["api_key"]


def test_legacy_system_model_config_without_encrypted_key_uses_env_key(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "0")
    monkeypatch.setenv("MODEL_CONFIG_SECRET", "test-model-config-secret")
    monkeypatch.setenv("AGNES_API_KEY", "test-env-key-legacy-system")
    app = create_app()
    app.state.service.db.save_model_config({
        "provider": "Agens",
        "base_url": "https://apihub.agnes-ai.com/v1",
        "model": "agnes-2.0-flash",
        "api_key_set": True,
        "api_key_masked": "<legacy>",
        "api_key_encrypted": "",
    })

    runtime = app.state.service._model_config.runtime(None)

    assert runtime["source"] == "system"
    assert runtime["api_key"] == "test-env-key-legacy-system"
    assert runtime["api_key_set"] is True


def test_post_model_settings_rejects_oversized_field(tmp_path: Path, monkeypatch) -> None:
    """F-002: four fields have max_length constraints and oversized values return 422."""
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "0")
    monkeypatch.setenv("MODEL_CONFIG_SECRET", "test-model-config-secret")
    app = create_app()
    client = TestClient(app)
    _create_invite(app)
    _login_user(client, "player", "invite-code-123")
    cases = [
        ("provider", "x" * 200),
        ("base_url", "https://" + "a" * 600),
        ("model", "m" * 300),
        ("api_key", "k" * 1024),
    ]
    for field, oversize_value in cases:
        payload = _model_payload("")
        payload[field] = oversize_value
        resp = client.post("/api/settings/model", json=payload)
        assert resp.status_code == 422, f"{field}: expected 422, got {resp.status_code}"
        body = resp.text
        assert field in body or "too_long" in body or "max_length" in body or "longer than" in body
