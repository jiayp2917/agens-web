"""Shared database helpers for the web adapter."""

from __future__ import annotations

import json
import time
from typing import Any

from .catalog_structure import CATALOG_JSON_FIELDS


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


def encode_game_turn_json(
    choices: list,
    state_delta: dict,
    state_after: dict,
) -> tuple[str, str, str]:
    """Return (choices, state_delta, state_after) as compact JSON strings.

    Postgres casts these to JSONB; the encoded string is the canonical form.
    """
    return (
        dump_json(choices),
        dump_json(state_delta),
        dump_json(state_after),
    )


def public_user(user: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": user["id"],
        "username": user["username"],
        "is_admin": bool(user.get("is_admin")),
        "created_at": user.get("created_at"),
    }
