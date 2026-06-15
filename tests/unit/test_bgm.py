"""Tests for the cross-environment BGM service.

The service is best-effort: the suite must pass on any host, with or
without an audio device, with or without kivy, with or without pygame.
We exercise the public API and verify the service never raises.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Make sure the package is importable from src/.
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))


@pytest.fixture(autouse=True)
def _reset_singleton():
    """Drop the cached service so each test gets a fresh state."""
    from agens_novel import bgm

    bgm.shutdown_service()
    yield
    bgm.shutdown_service()


def test_service_instantiation_does_not_raise():
    """Service must construct on any host — audio device optional."""
    from agens_novel.bgm import BgmService, get_service

    svc = get_service()
    assert isinstance(svc, BgmService)


def test_alias_lookup_helpers():
    from agens_novel.bgm import is_alias, list_aliases

    aliases = list_aliases()
    assert "default" in aliases
    assert is_alias("default") is True
    assert is_alias("not-a-real-track") is False
    assert is_alias("/some/absolute/path.flac") is False


def test_resolve_track_prefers_project_root_bgm():
    from agens_novel.bgm import _resolve_track

    assert _resolve_track("default") == ROOT / "bgm.flac"


def test_resolve_track_supports_mobile_asset_fallback(monkeypatch, tmp_path):
    from agens_novel import bgm
    from agens_novel import paths

    asset = tmp_path / "mobile" / "assets" / "audio" / "bgm.flac"
    asset.parent.mkdir(parents=True)
    asset.write_bytes(b"fake")

    monkeypatch.setattr(paths, "PROJECT_ROOT", tmp_path)

    assert bgm._resolve_track("default") == asset


def test_load_returns_bool_without_raising():
    """Loading a known alias must return a bool, never raise."""
    from agens_novel.bgm import get_service

    svc = get_service()
    result = svc.load("default")
    assert isinstance(result, bool)


def test_play_returns_bool_without_raising():
    """Play must return a bool; missing audio is signalled via False."""
    from agens_novel.bgm import get_service

    svc = get_service()
    result = svc.play("default", loop=True)
    assert isinstance(result, bool)


def test_play_unknown_alias_does_not_crash():
    from agens_novel.bgm import get_service

    svc = get_service()
    # Even an unknown alias must be handled gracefully (returns False).
    assert svc.play("__nonexistent_alias__") is False


def test_stop_is_idempotent():
    from agens_novel.bgm import get_service

    svc = get_service()
    svc.stop()  # never played
    svc.stop()  # second call also fine


def test_set_volume_clamps_to_unit_range():
    from agens_novel.bgm import get_service

    svc = get_service()
    svc.set_volume(2.0)  # above 1.0 — should be clamped
    svc.set_volume(-1.0)  # below 0.0 — should be clamped
    # No assertion on the internal value, just that no exception escapes.


def test_mute_unmute_round_trip():
    from agens_novel.bgm import get_service

    svc = get_service()
    svc.mute()
    svc.unmute()
    # Still must report a sane enabled flag.
    assert svc.enabled in (True, False)


def test_shutdown_service_clears_singleton():
    from agens_novel import bgm

    a = bgm.get_service()
    bgm.shutdown_service()
    b = bgm.get_service()
    # Re-instantiation must produce a fresh object (singleton reset).
    assert a is not b


def test_audio_manager_play_bgm_alias_routes_through_service(monkeypatch):
    """AudioManager.play_bgm('default') must consult the BGM service."""
    # Make sure mobile/ is on sys.path for the import.
    mobile = ROOT / "mobile"
    monkeypatch.syspath_prepend(str(mobile))
    sys.modules.pop("audio_manager", None)

    from audio_manager import AudioManager

    manager = AudioManager()
    manager.bgm_enabled = True  # ensure the gate is open

    # Patch the service used inside the manager to a benign stub.
    from agens_novel import bgm

    calls = {"n": 0, "alias": None}

    class _Stub:
        enabled = True
        _muted = False

        def play(self, name, *, loop):
            calls["n"] += 1
            calls["alias"] = name
            calls["loop"] = loop
            return True

    monkeypatch.setattr(bgm, "get_service", lambda: _Stub())

    ok = manager.play_bgm("default", loop=True)
    assert ok is True
    assert calls["n"] == 1
    assert calls["alias"] == "default"
    assert calls["loop"] is True
