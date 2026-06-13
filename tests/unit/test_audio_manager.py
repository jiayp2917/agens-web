"""AudioManager behavior without real audio assets."""

from __future__ import annotations

import sys
from pathlib import Path


def test_audio_manager_missing_assets_are_noop(monkeypatch):
    root = Path(__file__).resolve().parents[2]
    monkeypatch.syspath_prepend(str(root / "mobile"))
    sys.modules.pop("audio_manager", None)

    from audio_manager import AudioManager

    manager = AudioManager()
    assert manager.play_bgm(root / "missing.ogg") is False
    assert manager.play_sfx(root / "missing.wav") is False


def test_audio_manager_toggles_and_settings(monkeypatch):
    root = Path(__file__).resolve().parents[2]
    monkeypatch.syspath_prepend(str(root / "mobile"))

    from audio_manager import AudioManager

    manager = AudioManager()
    manager.apply_settings({"bgm_enabled": True, "sfx_enabled": False})
    assert manager.bgm_enabled is True
    assert manager.sfx_enabled is False
    assert manager.toggle_bgm() is False
    assert manager.to_settings()["bgm_enabled"] is False
    assert manager.toggle_sfx() is True
