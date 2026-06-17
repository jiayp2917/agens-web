"""Persistent settings storage for Android.

Android has no shell-style environment configuration. This module stores
ordinary settings as JSON in the app's internal storage, stores API keys in a
separate app-private JSON file, and injects them into ``os.environ`` at startup
so the game engine can read them.

Also supports model configuration persistence (user_model.json).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

DEFAULT_BASE_URL = "https://apihub.agnes-ai.com/v1"
DEFAULT_MODEL = "agnes-2.0-flash"


def _settings_path() -> Path:
    """Return the settings JSON path. Works in Android and local tests."""
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


def _secrets_path() -> Path:
    """Return the app-private secrets JSON path."""
    try:
        from kivy.app import App
        app = App.get_running_app()
        if app is not None:
            return Path(app.user_data_dir) / "secrets.json"
    except Exception:
        pass
    return Path.home() / ".agens_novel" / "secrets.json"


def load_settings() -> dict:
    """Load settings from disk. Returns empty dict if not found."""
    p = _settings_path()
    if p.exists():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                data.pop("api_key", None)
                data.pop("AGNES_API_KEY", None)
                return data
        except (json.JSONDecodeError, ValueError):
            return {}
    return {}


def save_settings(data: dict) -> None:
    """Save non-secret settings to disk."""
    p = _settings_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    safe_data = dict(data)
    safe_data.pop("api_key", None)
    safe_data.pop("AGNES_API_KEY", None)
    safe_data.pop("game_mode", None)
    p.write_text(json.dumps(safe_data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_api_key() -> str:
    """Load the saved API key from app-private storage."""
    p = _secrets_path()
    if not p.exists():
        return ""
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, ValueError):
        return ""
    if not isinstance(data, dict):
        return ""
    key = data.get("api_key") or data.get("AGNES_API_KEY") or ""
    return key.strip() if isinstance(key, str) else ""


def save_api_key(api_key: str) -> None:
    """Persist an API key in app-private storage."""
    key = api_key.strip()
    if not key:
        return
    p = _secrets_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"api_key": key}, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        os.chmod(p, 0o600)
    except OSError:
        pass


def has_saved_api_key() -> bool:
    """Return whether a saved or environment API key is available."""
    return bool(os.environ.get("AGNES_API_KEY") or load_api_key())


def mask_api_key(api_key: str | None) -> str:
    """Return a short API key preview that is safe to show in UI."""
    key = (api_key or "").strip()
    if not key:
        return "未配置"
    if len(key) <= 8:
        return "****"
    return f"{key[:4]}****{key[-4:]}"


def active_model_summary(data: dict | None = None) -> str:
    """Return a UI-safe summary of the currently effective model settings."""
    settings = data or load_settings()
    base_url = str(settings.get("base_url") or os.environ.get("AGNES_BASE_URL") or DEFAULT_BASE_URL).strip()
    model = str(settings.get("model") or os.environ.get("AGNES_MODEL") or DEFAULT_MODEL).strip()
    key = str(settings.get("api_key") or os.environ.get("AGNES_API_KEY") or load_api_key()).strip()
    provider = "自定义"
    lowered = base_url.lower()
    if "deepseek" in lowered:
        provider = "DeepSeek"
    elif "agnes" in lowered:
        provider = "Agens"
    elif "localhost" in lowered or "10.0.2.2" in lowered or "ollama" in lowered:
        provider = "Ollama"
    return f"当前生效：{provider} / {model} / Key {mask_api_key(key)}"


def apply_settings_to_env(data: dict) -> None:
    """Inject settings into os.environ so GameEngine/agents can read them."""
    api_key = str(data.get("api_key") or "").strip()
    if api_key:
        os.environ["AGNES_API_KEY"] = api_key
    elif not os.environ.get("AGNES_API_KEY"):
        saved_key = load_api_key()
        if saved_key:
            os.environ["AGNES_API_KEY"] = saved_key
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


def is_missing_api_key() -> bool:
    """Check whether the current process has no API key configured."""
    return not has_saved_api_key()
