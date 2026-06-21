"""Shared database helpers for the web adapter."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from agens_novel import paths


def default_db_path() -> Path:
    configured = os.environ.get("AGENS_WEB_DB")
    if configured:
        return Path(configured)
    return paths.RUNTIME_DIR / "web" / "agens_web.sqlite3"


def now_ts() -> float:
    return time.time()


def dump_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def load_json(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    if value in (None, ""):
        return None
    return json.loads(str(value))


def row_with_json(row: Any) -> dict[str, Any]:
    data = dict(row)
    if "snapshot_json" in data:
        data["snapshot"] = load_json(data.pop("snapshot_json"))
    if "events_json" in data:
        data["events"] = load_json(data.pop("events_json"))
    return data


def safe_name(name: str) -> str:
    cleaned = "".join(ch for ch in name.strip() if ch.isalnum() or ch in ("-", "_"))
    return cleaned or "slot_1"


def public_user(user: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": user["id"],
        "username": user["username"],
        "is_admin": bool(user.get("is_admin")),
        "created_at": user.get("created_at"),
    }
