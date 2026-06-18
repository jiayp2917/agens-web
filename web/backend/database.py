"""SQLite storage for the web adapter."""

from __future__ import annotations

import json
import os
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

from agens_novel import paths


def default_db_path() -> Path:
    configured = os.environ.get("AGENS_WEB_DB")
    if configured:
        return Path(configured)
    return paths.RUNTIME_DIR / "web" / "agens_web.sqlite3"


class WebDatabase:
    """Small SQLite wrapper for sessions, saves, users, and model summaries."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_db_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def initialize(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    username TEXT NOT NULL UNIQUE,
                    created_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    snapshot_json TEXT NOT NULL,
                    events_json TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS saves (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    snapshot_json TEXT NOT NULL,
                    events_json TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    UNIQUE(user_id, name)
                );

                CREATE TABLE IF NOT EXISTS model_config (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    provider TEXT NOT NULL,
                    base_url TEXT NOT NULL,
                    model TEXT NOT NULL,
                    api_key_masked TEXT NOT NULL,
                    api_key_set INTEGER NOT NULL,
                    updated_at REAL NOT NULL
                );
                """
            )

    def upsert_user(self, username: str) -> dict[str, Any]:
        username = (username or "local").strip() or "local"
        now = time.time()
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
            if row is None:
                user_id = str(uuid.uuid4())
                conn.execute(
                    "INSERT INTO users (id, username, created_at) VALUES (?, ?, ?)",
                    (user_id, username, now),
                )
                return {"id": user_id, "username": username, "created_at": now}
            return dict(row)

    def save_session(
        self,
        session_id: str,
        user_id: str,
        title: str,
        snapshot: dict[str, Any],
        events: list[dict[str, Any]],
    ) -> None:
        now = time.time()
        with self.connect() as conn:
            existing = conn.execute(
                "SELECT created_at FROM sessions WHERE id = ?", (session_id,)
            ).fetchone()
            created_at = float(existing["created_at"]) if existing else now
            conn.execute(
                """
                INSERT INTO sessions
                    (id, user_id, title, snapshot_json, events_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    user_id = excluded.user_id,
                    title = excluded.title,
                    snapshot_json = excluded.snapshot_json,
                    events_json = excluded.events_json,
                    updated_at = excluded.updated_at
                """,
                (
                    session_id,
                    user_id,
                    title,
                    _dump(snapshot),
                    _dump(events[-100:]),
                    created_at,
                    now,
                ),
            )

    def load_session(self, session_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
        return _row_with_json(row) if row else None

    def save_game_slot(
        self,
        user_id: str,
        name: str,
        snapshot: dict[str, Any],
        events: list[dict[str, Any]],
    ) -> dict[str, Any]:
        slot_name = _safe_name(name or "slot_1")
        now = time.time()
        with self.connect() as conn:
            row = conn.execute(
                "SELECT id, created_at FROM saves WHERE user_id = ? AND name = ?",
                (user_id, slot_name),
            ).fetchone()
            save_id = str(row["id"]) if row else str(uuid.uuid4())
            created_at = float(row["created_at"]) if row else now
            conn.execute(
                """
                INSERT INTO saves
                    (id, user_id, name, snapshot_json, events_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, name) DO UPDATE SET
                    snapshot_json = excluded.snapshot_json,
                    events_json = excluded.events_json,
                    updated_at = excluded.updated_at
                """,
                (
                    save_id,
                    user_id,
                    slot_name,
                    _dump(snapshot),
                    _dump(events[-100:]),
                    created_at,
                    now,
                ),
            )
        return {"id": save_id, "user_id": user_id, "name": slot_name, "updated_at": now}

    def list_saves(self, user_id: str) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM saves WHERE user_id = ? ORDER BY updated_at DESC", (user_id,)
            ).fetchall()
        result = []
        for row in rows:
            item = _row_with_json(row)
            snapshot = item.get("snapshot", {})
            char = snapshot.get("character", {}) if isinstance(snapshot, dict) else {}
            result.append(
                {
                    "id": item["id"],
                    "name": item["name"],
                    "char_name": char.get("name", "?"),
                    "realm": char.get("realm", "?"),
                    "turn_count": snapshot.get("turn_count", 0) if isinstance(snapshot, dict) else 0,
                    "updated_at": item["updated_at"],
                }
            )
        return result

    def load_save(self, user_id: str, name: str) -> dict[str, Any] | None:
        slot_name = _safe_name(name or "slot_1")
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM saves WHERE user_id = ? AND name = ?", (user_id, slot_name)
            ).fetchone()
        return _row_with_json(row) if row else None

    def save_model_config(self, config: dict[str, Any]) -> dict[str, Any]:
        now = time.time()
        data = {
            "provider": str(config.get("provider") or "Agens"),
            "base_url": str(config.get("base_url") or "https://apihub.agnes-ai.com/v1"),
            "model": str(config.get("model") or "agnes-2.0-flash"),
            "api_key_masked": str(config.get("api_key_masked") or "<unset>"),
            "api_key_set": 1 if config.get("api_key_set") else 0,
            "updated_at": now,
        }
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO model_config
                    (id, provider, base_url, model, api_key_masked, api_key_set, updated_at)
                VALUES (1, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    provider = excluded.provider,
                    base_url = excluded.base_url,
                    model = excluded.model,
                    api_key_masked = excluded.api_key_masked,
                    api_key_set = excluded.api_key_set,
                    updated_at = excluded.updated_at
                """,
                (
                    data["provider"],
                    data["base_url"],
                    data["model"],
                    data["api_key_masked"],
                    data["api_key_set"],
                    data["updated_at"],
                ),
            )
        return data

    def get_model_config(self) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM model_config WHERE id = 1").fetchone()
        return dict(row) if row else None


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _row_with_json(row: sqlite3.Row) -> dict[str, Any]:
    data = dict(row)
    if "snapshot_json" in data:
        data["snapshot"] = json.loads(data.pop("snapshot_json"))
    if "events_json" in data:
        data["events"] = json.loads(data.pop("events_json"))
    return data


def _safe_name(name: str) -> str:
    cleaned = "".join(ch for ch in name.strip() if ch.isalnum() or ch in ("-", "_"))
    return cleaned or "slot_1"

