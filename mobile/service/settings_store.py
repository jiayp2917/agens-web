"""Persistent settings storage for Android.

Android has no shell-style environment configuration. This module stores
non-secret settings as JSON in the app's internal storage, and injects them
into ``os.environ`` at startup so the game engine can read them.

Also supports model configuration persistence (user_model.json).
"""

from __future__ import annotations

import json
import os
from pathlib import Path


def _settings_path() -> Path:
    """Return the settings JSON path. Works on both desktop and Android."""
    try:
        from kivy.app import App
        app = App.get_running_app()
        if app is not None:
            return Path(app.user_data_dir) / "settings.json"
    except Exception:
        pass
    return Path.home() / ".agens_novel" / "settings.json"


def _model_config_path() -> Path:
    """Return the model config JSON path."""
    try:
        from kivy.app import App
        app = App.get_running_app()
        if app is not None:
            return Path(app.user_data_dir) / "user_model.json"
    except Exception:
        pass
    return Path.home() / ".agens_novel" / "user_model.json"


def load_settings() -> dict:
    """Load settings from disk. Returns empty dict if not found."""
    p = _settings_path()
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, ValueError):
            return {}
    return {}


def save_settings(data: dict) -> None:
    """Save non-secret settings to disk.

    API keys are intentionally not persisted. Call ``apply_settings_to_env``
    with the in-memory form data before or after this function when a user
    enters a key for the current process.
    """
    p = _settings_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    safe_data = dict(data)
    safe_data.pop("api_key", None)
    p.write_text(json.dumps(safe_data, ensure_ascii=False, indent=2), encoding="utf-8")


def apply_settings_to_env(data: dict) -> None:
    """Inject settings into os.environ so GameEngine/agents can read them."""
    if data.get("api_key"):
        os.environ["AGNES_API_KEY"] = data["api_key"]
    if data.get("base_url"):
        os.environ["AGNES_BASE_URL"] = data["base_url"]
    if data.get("model"):
        os.environ["AGNES_MODEL"] = data["model"]


def load_model_config() -> dict:
    """Load model configuration from user_model.json.

    Returns dict with keys:
        selected_model: str — the model chosen from spinner
        custom_model: str — user-typed custom model name (overrides selected)
    """
    p = _model_config_path()
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, ValueError):
            return {}
    return {}


def save_model_config(data: dict) -> None:
    """Save model configuration to user_model.json."""
    p = _model_config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def is_using_builtin_key() -> bool:
    """Check whether the app is using the built-in API key (no user key set)."""
    return not bool(os.environ.get("AGNES_API_KEY"))
