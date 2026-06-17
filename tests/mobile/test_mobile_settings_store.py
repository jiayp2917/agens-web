"""Mobile settings persistence keeps secrets out of ordinary settings."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def _reload_settings_store(tmp_path, monkeypatch):
    root = Path(__file__).resolve().parents[2]
    monkeypatch.syspath_prepend(str(root / "mobile"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path))
    sys.modules.pop("service.settings_store", None)
    import service.settings_store as store

    return store


def test_save_settings_does_not_persist_api_key(tmp_path, monkeypatch):
    store = _reload_settings_store(tmp_path, monkeypatch)

    data = {
        "api_key": "sk-do-not-save",
        "base_url": "https://example.test/v1",
        "model": "model-x",
        "game_mode": "mid",
    }
    store.apply_settings_to_env(data)
    store.save_settings(data)

    settings_path = tmp_path / ".agens_novel" / "settings.json"
    saved = json.loads(settings_path.read_text(encoding="utf-8"))
    assert "api_key" not in saved
    assert "game_mode" not in saved


def test_api_key_persists_in_private_secret_file_and_reloads(tmp_path, monkeypatch):
    store = _reload_settings_store(tmp_path, monkeypatch)
    monkeypatch.delenv("AGNES_API_KEY", raising=False)

    store.save_api_key("sk-private-mobile-key")
    store.apply_settings_to_env({"base_url": "https://example.test/v1", "model": "model-x"})

    settings_path = tmp_path / ".agens_novel" / "settings.json"
    secrets_path = tmp_path / ".agens_novel" / "secrets.json"

    assert not settings_path.exists()
    assert json.loads(secrets_path.read_text(encoding="utf-8")) == {"api_key": "sk-private-mobile-key"}
    assert store.has_saved_api_key() is True
    assert store.is_missing_api_key() is False
    assert "AGNES_API_KEY" in os.environ


def test_empty_settings_key_keeps_saved_key(tmp_path, monkeypatch):
    store = _reload_settings_store(tmp_path, monkeypatch)
    store.save_api_key("sk-existing-key")
    monkeypatch.delenv("AGNES_API_KEY", raising=False)

    store.apply_settings_to_env({"api_key": "", "base_url": "https://example.test/v1"})

    assert os.environ["AGNES_API_KEY"] == "sk-existing-key"


def test_mask_api_key_never_exposes_full_key(tmp_path, monkeypatch):
    store = _reload_settings_store(tmp_path, monkeypatch)
    key = "sk-private-mobile-key"

    masked = store.mask_api_key(key)

    assert masked == "sk-p****-key"
    assert key not in masked


def test_active_model_summary_defaults_to_agens_without_key(tmp_path, monkeypatch):
    store = _reload_settings_store(tmp_path, monkeypatch)
    monkeypatch.delenv("AGNES_API_KEY", raising=False)
    monkeypatch.delenv("AGNES_BASE_URL", raising=False)
    monkeypatch.delenv("AGNES_MODEL", raising=False)

    summary = store.active_model_summary({})

    assert "Agens" in summary
    assert "agnes-2.0-flash" in summary
    assert "未配置" in summary


def test_active_model_summary_shows_deepseek_and_masked_key(tmp_path, monkeypatch):
    store = _reload_settings_store(tmp_path, monkeypatch)
    key = "sk-private-mobile-key"

    summary = store.active_model_summary({
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-chat",
        "api_key": key,
    })

    assert "DeepSeek" in summary
    assert "deepseek-chat" in summary
    assert "sk-p****-key" in summary
    assert key not in summary


def test_active_model_summary_uses_saved_key_when_field_is_blank(tmp_path, monkeypatch):
    store = _reload_settings_store(tmp_path, monkeypatch)
    store.save_api_key("sk-existing-mobile-key")
    monkeypatch.delenv("AGNES_API_KEY", raising=False)

    summary = store.active_model_summary({
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-chat",
        "api_key": "",
    })

    assert "DeepSeek" in summary
    assert "deepseek-chat" in summary
    assert "sk-e****-key" in summary
    assert "sk-existing-mobile-key" not in summary
