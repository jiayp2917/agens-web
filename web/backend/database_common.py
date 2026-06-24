"""Shared database helpers for the web adapter."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from agens_novel import paths

CATALOG_TABLES = (
    "catalog_talents",
    "catalog_family_backgrounds",
    "catalog_spirit_roots",
    "catalog_difficulties",
    "catalog_story_seeds",
)

CATALOG_JSON_FIELDS = (
    "attribute_mods",
    "tags",
    "initial_resources",
    "initial_risks",
    "story_tags",
    "event_tags",
)


def catalog_seed_sources() -> tuple[tuple[str, list[dict[str, Any]]], ...]:
    from .catalog_seed import (
        SEED_DIFFICULTIES,
        SEED_FAMILY_BACKGROUNDS,
        SEED_SPIRIT_ROOTS,
        SEED_STORY_SEEDS,
        SEED_TALENTS,
    )

    return (
        ("catalog_talents", SEED_TALENTS),
        ("catalog_family_backgrounds", SEED_FAMILY_BACKGROUNDS),
        ("catalog_spirit_roots", SEED_SPIRIT_ROOTS),
        ("catalog_difficulties", SEED_DIFFICULTIES),
        ("catalog_story_seeds", SEED_STORY_SEEDS),
    )


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


def encode_json_fields(row: dict[str, Any], fields: tuple[str, ...] = CATALOG_JSON_FIELDS) -> dict[str, Any]:
    data = dict(row)
    for field in fields:
        if field in data and not isinstance(data[field], str):
            data[field] = dump_json(data[field])
    return data


def prepare_catalog_row(
    row: dict[str, Any],
    *,
    created_at: float | None = None,
    fields: tuple[str, ...] = CATALOG_JSON_FIELDS,
) -> dict[str, Any]:
    data = dict(row)
    if created_at is not None:
        data.setdefault("created_at", created_at)
    return encode_json_fields(data, fields)


def decode_json_fields(row: Any, fields: tuple[str, ...] = CATALOG_JSON_FIELDS) -> dict[str, Any]:
    data = dict(row)
    for field in fields:
        if field in data:
            try:
                data[field] = load_json(data[field])
            except (json.JSONDecodeError, TypeError, ValueError):
                pass
    return data


def row_with_json(row: Any) -> dict[str, Any]:
    data = dict(row)
    if "snapshot_json" in data:
        data["snapshot"] = load_json(data.pop("snapshot_json"))
    if "events_json" in data:
        data["events"] = load_json(data.pop("events_json"))
    if "snapshot" in data:
        data["snapshot"] = load_json(data["snapshot"])
    if "events" in data:
        data["events"] = load_json(data["events"])
    return data


def save_summary(row: Any) -> dict[str, Any]:
    item = row_with_json(row)
    snapshot = item.get("snapshot", {})
    char = snapshot.get("character", {}) if isinstance(snapshot, dict) else {}
    return {
        "id": item["id"],
        "name": item["name"],
        "char_name": char.get("name", "?"),
        "realm": char.get("realm", "?"),
        "turn_count": snapshot.get("turn_count", 0) if isinstance(snapshot, dict) else 0,
        "updated_at": item["updated_at"],
    }


def player_progress_summary(row: Any | None) -> dict[str, int]:
    if row is None:
        return {"runs_completed": 0, "ascension_count": 0}
    return {
        "runs_completed": int(row["runs_completed"]),
        "ascension_count": int(row["ascension_count"]),
    }


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
