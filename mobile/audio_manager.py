"""Small audio facade for the Kivy mobile app.

The prototype requires BGM/SFX switches, but actual audio files are optional.
This manager therefore treats missing files as a no-op instead of an error.
"""

from __future__ import annotations

from pathlib import Path
from typing import Union

BgmPath = Union[str, Path]


class AudioManager:
    """Singleton-style BGM/SFX controller."""

    _instance: AudioManager | None = None

    def __new__(cls) -> AudioManager:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        self.bgm_enabled = True
        self.sfx_enabled = True
        self._current_bgm = None
        self._current_path = ""
        self._initialized = True

    def play_bgm(self, path: BgmPath, loop: bool = True) -> bool:
        """Play BGM if enabled and the asset exists.

        ``path`` can be an absolute filesystem path (legacy) or an alias
        resolved through :mod:`agens_novel.bgm` (e.g. ``"default"``).
        Aliases allow the same call site to work on Android, local tests, and
        in tests without hard-coding file paths.
        """
        if not self.bgm_enabled:
            return False
        # ── Alias path: defer to the shared BGM service ────────────────
        if isinstance(path, str):
            try:
                from agens_novel.bgm import get_service, is_alias

                if is_alias(path):
                    ok = get_service().play(path, loop=loop)
                    if ok:
                        # Drop any legacy direct-loaded track; record alias.
                        if self._current_bgm is not None:
                            try:
                                self._current_bgm.stop()
                            except Exception:
                                pass
                            self._current_bgm = None
                        self._current_path = path
                    return ok
            except Exception:
                return False
        # ── Legacy absolute path: direct SoundLoader ───────────────────
        asset = Path(path)
        if not asset.exists():
            return False
        if str(asset) == self._current_path and self._current_bgm is not None:
            return True
        self.stop_bgm()
        try:
            from kivy.core.audio import SoundLoader
            sound = SoundLoader.load(str(asset))
        except Exception:
            sound = None
        if sound is None:
            return False
        sound.loop = loop
        sound.play()
        self._current_bgm = sound
        self._current_path = str(asset)
        return True

    def stop_bgm(self) -> None:
        """Stop current BGM if one is loaded."""
        try:
            from agens_novel.bgm import get_service

            get_service().stop()
        except Exception:
            pass
        if self._current_bgm is not None:
            try:
                self._current_bgm.stop()
            except Exception:
                pass
        self._current_bgm = None
        self._current_path = ""

    def toggle_bgm(self) -> bool:
        """Toggle BGM and stop current music when disabling."""
        self.bgm_enabled = not self.bgm_enabled
        if not self.bgm_enabled:
            self.stop_bgm()
        return self.bgm_enabled

    def play_sfx(self, path: str | Path) -> bool:
        """Play a sound effect if enabled and present."""
        if not self.sfx_enabled:
            return False
        asset = Path(path)
        if not asset.exists():
            return False
        try:
            from kivy.core.audio import SoundLoader
            sound = SoundLoader.load(str(asset))
            if sound is None:
                return False
            sound.play()
            return True
        except Exception:
            return False

    def toggle_sfx(self) -> bool:
        """Toggle sound effects."""
        self.sfx_enabled = not self.sfx_enabled
        return self.sfx_enabled

    def apply_settings(self, data: dict) -> None:
        """Load audio switch state from settings data."""
        self.bgm_enabled = bool(data.get("bgm_enabled", self.bgm_enabled))
        self.sfx_enabled = bool(data.get("sfx_enabled", self.sfx_enabled))
        if not self.bgm_enabled:
            self.stop_bgm()

    def to_settings(self) -> dict:
        """Return serializable audio settings."""
        return {
            "bgm_enabled": self.bgm_enabled,
            "sfx_enabled": self.sfx_enabled,
        }
