"""Mobile settings persistence keeps secrets out of disk."""

from __future__ import annotations

import json
import sys
from pathlib import Path


def test_save_settings_does_not_persist_api_key(tmp_path, monkeypatch):
    root = Path(__file__).resolve().parents[2]
    monkeypatch.syspath_prepend(str(root / "mobile"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path))
    sys.modules.pop("service.settings_store", None)

    from service.settings_store import apply_settings_to_env, save_settings

    data = {
        "api_key": "sk-do-not-save",
        "base_url": "https://example.test/v1",
        "model": "model-x",
        "game_mode": "mid",
    }
    apply_settings_to_env(data)
    save_settings(data)

    settings_path = tmp_path / ".agens_novel" / "settings.json"
    saved = json.loads(settings_path.read_text(encoding="utf-8"))
    assert "api_key" not in saved
    assert "game_mode" not in saved
