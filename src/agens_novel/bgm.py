"""Background music (BGM) service — cross-environment playback.

Single entry point used by the Kivy mobile app and demo scripts. The
service picks the best available backend at runtime and
falls back to a no-op if no audio device is available, so importing or
calling into this module never breaks the host application.

Backends, in preference order:
  1. ``kivy.core.audio.SoundLoader`` — used inside the Kivy app and demo.
  2. ``pygame.mixer`` — optional fallback for local audio checks.
  3. ``None`` — silent stub used when neither backend is importable or
     when audio initialisation fails. The game still runs.

All public methods are *best-effort*: a missing mixer, a busy audio
device, or a corrupt file is logged at INFO and swallowed. The game
treats ``BgmService`` as fire-and-forget.
"""

from __future__ import annotations

import logging
import os
import threading
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Default BGM track — relative to the project root.
DEFAULT_BGM_FILENAME = "bgm.flac"
DEFAULT_VOLUME = 0.4  # soft default; bgm should not drown narrative

# Tracks (future expansion; we ship only one file today).
# A future contributor can drop files in audio/ and reference them here.
_TRACK_ALIASES = {
    "default": DEFAULT_BGM_FILENAME,
    "main": DEFAULT_BGM_FILENAME,
    "cultivation": DEFAULT_BGM_FILENAME,
    "ascension": DEFAULT_BGM_FILENAME,
}


def _resolve_track(name: str) -> Path:
    """Resolve a track alias to an absolute path under the project root."""
    from .paths import PROJECT_ROOT  # late import to avoid cycle in tests

    filename = _TRACK_ALIASES.get(name, name)
    candidate = Path(filename)
    if candidate.is_absolute():
        return candidate

    search_paths = (
        PROJECT_ROOT / candidate,
        PROJECT_ROOT / "assets" / "audio" / candidate,
        PROJECT_ROOT / "mobile" / "assets" / "audio" / candidate,
    )
    for path in search_paths:
        if path.exists():
            return path
    return search_paths[0]


def is_alias(name: str) -> bool:
    """Return True if ``name`` is a known BGM alias understood by the service.

    Adapters (e.g. ``mobile.audio_manager``) call this to decide whether
    to route the request through :class:`BgmService` or to handle it as a
    raw filesystem path.
    """
    return name in _TRACK_ALIASES


def list_aliases() -> list[str]:
    """Return the list of known BGM aliases."""
    return list(_TRACK_ALIASES.keys())


# ─── Backend abstraction ──────────────────────────────────────────────────


class _BgmBackend:
    """Common interface for backend implementations."""

    def load(self, path: Path) -> bool:
        """Load ``path`` into memory. Returns True on success."""

    def play(self, loop: bool) -> None:
        """Start playback (does nothing if nothing is loaded)."""

    def stop(self) -> None:
        """Stop playback (idempotent)."""

    def set_volume(self, volume: float) -> None:
        """Set output volume in [0.0, 1.0]."""

    def is_playing(self) -> bool:
        """Return True if audio is currently playing."""


class _NullBackend(_BgmBackend):
    """Silent backend used when no audio is available."""

    def __init__(self) -> None:
        self._loaded: Optional[Path] = None
        self._volume = DEFAULT_VOLUME
        self._playing = False

    def load(self, path: Path) -> bool:
        if not path.exists():
            logger.info("BGM: file not found, audio disabled — %s", path)
            return False
        self._loaded = path
        logger.info("BGM: using null backend (no audio device) — %s", path.name)
        return True

    def play(self, loop: bool) -> None:
        self._playing = True

    def stop(self) -> None:
        self._playing = False

    def set_volume(self, volume: float) -> None:
        self._volume = max(0.0, min(1.0, volume))

    def is_playing(self) -> bool:
        return self._playing


class _KivyBackend(_BgmBackend):
    """Kivy ``SoundLoader`` backend — used inside the Kivy app and demo."""

    def __init__(self) -> None:
        self._sound = None
        self._loaded: Optional[Path] = None

    def load(self, path: Path) -> bool:
        if not path.exists():
            logger.info("BGM: file not found — %s", path)
            return False
        try:
            from kivy.core.audio import SoundLoader  # type: ignore

            self._sound = SoundLoader.load(str(path))
        except Exception as exc:  # noqa: BLE001 — audio init is best-effort
            logger.info("BGM: Kivy loader unavailable — %s", exc)
            self._sound = None
            return False
        if self._sound is None:
            logger.info("BGM: Kivy could not decode — %s", path)
            return False
        self._sound.volume = DEFAULT_VOLUME
        self._loaded = path
        logger.info("BGM: loaded via Kivy — %s (%.1fs)", path.name, self._sound.length or 0)
        return True

    def play(self, loop: bool) -> None:
        if self._sound is None:
            return
        try:
            self._sound.loop = loop
            self._sound.play()
        except Exception as exc:  # noqa: BLE001
            logger.info("BGM: Kivy play failed — %s", exc)

    def stop(self) -> None:
        if self._sound is None:
            return
        try:
            self._sound.stop()
        except Exception:  # noqa: BLE001
            pass

    def set_volume(self, volume: float) -> None:
        if self._sound is None:
            return
        try:
            self._sound.volume = max(0.0, min(1.0, volume))
        except Exception:  # noqa: BLE001
            pass

    def is_playing(self) -> bool:
        if self._sound is None:
            return False
        try:
            return self._sound.state == "play"
        except Exception:  # noqa: BLE001
            return False


class _PygameBackend(_BgmBackend):
    """``pygame.mixer`` backend used as a local fallback."""

    def __init__(self) -> None:
        self._mixer = None
        self._sound = None
        self._channel = None
        self._loaded: Optional[Path] = None

    def _ensure_mixer(self) -> bool:
        if self._mixer is not None:
            return True
        try:
            from pygame import mixer  # type: ignore

            mixer.init()
            self._mixer = mixer
            return True
        except Exception as exc:  # noqa: BLE001
            logger.info("BGM: pygame mixer init failed — %s", exc)
            return False

    def load(self, path: Path) -> bool:
        if not path.exists():
            logger.info("BGM: file not found — %s", path)
            return False
        if not self._ensure_mixer():
            return False
        try:
            # FLAC support depends on SDL_image codecs shipped with pygame.
            # If the bundled SDL can't decode FLAC, fall through.
            self._sound = self._mixer.Sound(str(path))
        except Exception as exc:  # noqa: BLE001
            logger.info("BGM: pygame failed to decode %s — %s", path.name, exc)
            self._sound = None
            return False
        self._loaded = path
        self._mixer.music.set_volume(DEFAULT_VOLUME)
        # Channel-based playback is the only way to call .play(loops=...) with
        # a Sound object; reserve a dedicated channel.
        self._channel = self._mixer.Channel(0)
        logger.info("BGM: loaded via pygame — %s", path.name)
        return True

    def play(self, loop: bool) -> None:
        if self._sound is None or self._mixer is None:
            return
        try:
            # pygame: loops=-1 means loop forever
            self._channel.play(self._sound, loops=-1 if loop else 0)
        except Exception as exc:  # noqa: BLE001
            logger.info("BGM: pygame play failed — %s", exc)

    def stop(self) -> None:
        if self._mixer is None:
            return
        try:
            if self._channel is not None:
                self._channel.stop()
        except Exception:  # noqa: BLE001
            pass

    def set_volume(self, volume: float) -> None:
        if self._mixer is None:
            return
        try:
            self._mixer.music.set_volume(max(0.0, min(1.0, volume)))
            if self._channel is not None:
                self._channel.set_volume(max(0.0, min(1.0, volume)))
        except Exception:  # noqa: BLE001
            pass

    def is_playing(self) -> bool:
        if self._mixer is None:
            return False
        try:
            return bool(self._mixer.get_busy())
        except Exception:  # noqa: BLE001
            return False


def _select_backend() -> _BgmBackend:
    """Pick the best backend available in this process."""
    # 1. Prefer Kivy when we are already inside a Kivy app.
    in_kivy = bool(os.environ.get("KIVY_WINDOW") or "kivy" in os.environ.get("PYTHONPATH", ""))
    # We can't import kivy lazily for detection — try-import is cheaper.
    try:
        import kivy.core.audio  # type: ignore  # noqa: F401

        return _KivyBackend()
    except Exception:  # noqa: BLE001
        if in_kivy:
            logger.info("BGM: Kivy present but unusable, falling back")

    # 2. Try pygame for local audio checks.
    try:
        import pygame  # type: ignore  # noqa: F401

        backend = _PygameBackend()
        return backend
    except Exception:  # noqa: BLE001
        pass

    # 3. Nothing works — null backend, no errors raised.
    return _NullBackend()


# ─── Public service ───────────────────────────────────────────────────────


class BgmService:
    """High-level BGM controller.

    Thread-safety: the service is safe to call from any thread; all state
    transitions are guarded by ``_lock`` so the Kivy main thread and a
    worker thread can both poke it.
    """

    def __init__(self, backend: Optional[_BgmBackend] = None) -> None:
        self._backend: _BgmBackend = backend or _select_backend()
        self._lock = threading.Lock()
        self._track: Optional[Path] = None
        self._loop = True
        self._volume = DEFAULT_VOLUME
        self._enabled = True
        self._muted = False
        logger.info("BGM service initialised — backend=%s", type(self._backend).__name__)

    # ── public API ────────────────────────────────────────────────────────

    def load(self, name: str = "default") -> bool:
        """Pre-load a track by alias. Idempotent."""
        with self._lock:
            path = _resolve_track(name)
            ok = self._backend.load(path)
            if ok:
                self._track = path
            return ok

    def play(self, name: str = "default", *, loop: bool = True) -> bool:
        """Load (if needed) and start playback. Returns True if audio is up."""
        with self._lock:
            if not self._enabled or self._muted:
                return False
            if self._track is None or self._track != _resolve_track(name):
                path = _resolve_track(name)
                if not self._backend.load(path):
                    return False
                self._track = path
            self._loop = loop
            self._backend.play(loop=loop)
            self._backend.set_volume(self._volume)
            return True

    def stop(self) -> None:
        """Stop playback (idempotent)."""
        with self._lock:
            self._backend.stop()

    def pause(self) -> None:
        """Pause without unloading. Backends that lack pause fall back to stop."""
        with self._lock:
            self._backend.stop()

    def set_volume(self, volume: float) -> None:
        """Set volume in [0.0, 1.0]."""
        with self._lock:
            self._volume = max(0.0, min(1.0, volume))
            if not self._muted:
                self._backend.set_volume(self._volume)

    def mute(self) -> None:
        """Mute without forgetting the volume level."""
        with self._lock:
            self._muted = True
            self._backend.set_volume(0.0)

    def unmute(self) -> None:
        with self._lock:
            self._muted = False
            self._backend.set_volume(self._volume)

    def is_playing(self) -> bool:
        with self._lock:
            return self._backend.is_playing()

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def track_name(self) -> Optional[str]:
        return self._track.name if self._track else None

    def shutdown(self) -> None:
        """Stop and release resources. Safe to call multiple times."""
        with self._lock:
            self._backend.stop()
            self._enabled = False


# Module-level singleton — ``import bgm; bgm.service.play()``.
# Lazy-instantiated so test environments that never touch audio don't pay
# the cost of importing kivy/pygame at import time.
_service: Optional[BgmService] = None
_service_lock = threading.Lock()


def get_service() -> BgmService:
    """Return the process-wide BGM service, instantiating it on first call."""
    global _service
    if _service is None:
        with _service_lock:
            if _service is None:
                _service = BgmService()
    return _service


def reset_service_for_tests() -> None:
    """Drop the cached singleton — for tests only.

    Equivalent to :func:`shutdown_service`. Kept under the legacy name so
    existing test suites continue to work; new callers should prefer
    :func:`shutdown_service` for clarity.
    """
    shutdown_service()


def shutdown_service() -> None:
    """Stop the BGM service and drop the cached singleton.

    Safe to call when the service was never instantiated. Use this from
    application teardown paths (e.g. Kivy ``App.on_stop``) so SDL audio
    resources are released cleanly.
    """
    global _service
    with _service_lock:
        if _service is not None:
            _service.shutdown()
        _service = None
