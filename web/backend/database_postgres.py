"""PostgreSQL storage for production deployment."""

from __future__ import annotations

import os
import uuid
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from .database_common import dump_json, load_json, now_ts, safe_name


class PostgresWebDatabase:
    """PostgreSQL implementation matching the SQLite web database API."""

    def __init__(self, database_url: str | None = None) -> None:
        self.database_url = database_url or os.environ.get("DATABASE_URL", "")
        if not self.database_url:
            raise RuntimeError("DATABASE_URL is required when DATABASE_BACKEND=postgresql")
        self.engine: Engine = create_engine(self.database_url, pool_pre_ping=True, future=True)
        if os.environ.get("AGENS_PG_AUTO_DDL", "").strip().lower() in ("1", "true", "yes"):
            self.initialize()

    def initialize(self) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS users (
                        id TEXT PRIMARY KEY,
                        username TEXT NOT NULL UNIQUE,
                        password_hash TEXT,
                        is_admin BOOLEAN NOT NULL DEFAULT FALSE,
                        created_at DOUBLE PRECISION NOT NULL,
                        updated_at DOUBLE PRECISION NOT NULL
                    )
                    """
                )
            )
            conn.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS invite_codes (
                        id TEXT PRIMARY KEY,
                        code_hash TEXT NOT NULL UNIQUE,
                        role TEXT NOT NULL DEFAULT 'user',
                        max_uses INTEGER NOT NULL DEFAULT 1,
                        uses INTEGER NOT NULL DEFAULT 0,
                        expires_at DOUBLE PRECISION,
                        disabled BOOLEAN NOT NULL DEFAULT FALSE,
                        created_at DOUBLE PRECISION NOT NULL,
                        created_by TEXT REFERENCES users(id)
                    )
                    """
                )
            )
            conn.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS sessions (
                        id TEXT PRIMARY KEY,
                        user_id TEXT NOT NULL REFERENCES users(id),
                        title TEXT NOT NULL,
                        snapshot JSONB NOT NULL,
                        events JSONB NOT NULL,
                        created_at DOUBLE PRECISION NOT NULL,
                        updated_at DOUBLE PRECISION NOT NULL
                    )
                    """
                )
            )
            conn.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS saves (
                        id TEXT PRIMARY KEY,
                        user_id TEXT NOT NULL REFERENCES users(id),
                        name TEXT NOT NULL,
                        snapshot JSONB NOT NULL,
                        events JSONB NOT NULL,
                        created_at DOUBLE PRECISION NOT NULL,
                        updated_at DOUBLE PRECISION NOT NULL,
                        UNIQUE(user_id, name)
                    )
                    """
                )
            )
            conn.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS model_config (
                        id INTEGER PRIMARY KEY CHECK (id = 1),
                        provider TEXT NOT NULL,
                        base_url TEXT NOT NULL,
                        model TEXT NOT NULL,
                        api_key_masked TEXT NOT NULL,
                        api_key_set BOOLEAN NOT NULL,
                        updated_at DOUBLE PRECISION NOT NULL
                    )
                    """
                )
            )

    def upsert_user(self, username: str) -> dict[str, Any]:
        username = (username or "local").strip() or "local"
        existing = self.get_user_by_username(username)
        if existing is not None:
            return existing
        now = now_ts()
        user = {
            "id": str(uuid.uuid4()),
            "username": username,
            "password_hash": None,
            "is_admin": False,
            "created_at": now,
            "updated_at": now,
        }
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO users (id, username, password_hash, is_admin, created_at, updated_at)
                    VALUES (:id, :username, :password_hash, :is_admin, :created_at, :updated_at)
                    """
                ),
                user,
            )
        return user

    def create_user(
        self,
        username: str,
        password_hash: str,
        is_admin: bool = False,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        now = now_ts()
        user = {
            "id": user_id or str(uuid.uuid4()),
            "username": username,
            "password_hash": password_hash,
            "is_admin": bool(is_admin),
            "created_at": now,
            "updated_at": now,
        }
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO users (id, username, password_hash, is_admin, created_at, updated_at)
                    VALUES (:id, :username, :password_hash, :is_admin, :created_at, :updated_at)
                    """
                ),
                user,
            )
        return user

    def get_user_by_username(self, username: str) -> dict[str, Any] | None:
        with self.engine.begin() as conn:
            row = conn.execute(text("SELECT * FROM users WHERE username = :username"), {"username": username}).mappings().first()
        return dict(row) if row else None

    def get_user_by_id(self, user_id: str) -> dict[str, Any] | None:
        with self.engine.begin() as conn:
            row = conn.execute(text("SELECT * FROM users WHERE id = :id"), {"id": user_id}).mappings().first()
        return dict(row) if row else None

    def has_admin_user(self) -> bool:
        with self.engine.begin() as conn:
            row = conn.execute(text("SELECT 1 FROM users WHERE is_admin = TRUE LIMIT 1")).first()
        return row is not None

    def create_invite_code(
        self,
        code_hash: str,
        role: str = "user",
        max_uses: int = 1,
        expires_at: float | None = None,
        created_by: str | None = None,
    ) -> dict[str, Any]:
        now = now_ts()
        invite = {
            "id": str(uuid.uuid4()),
            "code_hash": code_hash,
            "role": role,
            "max_uses": int(max_uses),
            "uses": 0,
            "expires_at": expires_at,
            "disabled": False,
            "created_at": now,
            "created_by": created_by,
        }
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO invite_codes
                        (id, code_hash, role, max_uses, uses, expires_at, disabled, created_at, created_by)
                    VALUES
                        (:id, :code_hash, :role, :max_uses, :uses, :expires_at, :disabled, :created_at, :created_by)
                    """
                ),
                invite,
            )
        return invite

    def get_invite_code(self, code_hash: str) -> dict[str, Any] | None:
        with self.engine.begin() as conn:
            row = conn.execute(text("SELECT * FROM invite_codes WHERE code_hash = :code_hash"), {"code_hash": code_hash}).mappings().first()
        return dict(row) if row else None

    def consume_invite_code(self, code_hash: str) -> dict[str, Any] | None:
        now = now_ts()
        with self.engine.begin() as conn:
            row = conn.execute(
                text(
                    """
                    UPDATE invite_codes
                    SET uses = uses + 1
                    WHERE code_hash = :code_hash
                      AND disabled = FALSE
                      AND uses < max_uses
                      AND (expires_at IS NULL OR expires_at >= :now)
                    RETURNING *
                    """
                ),
                {"code_hash": code_hash, "now": now},
            ).mappings().first()
        return dict(row) if row else None

    def save_session(
        self,
        session_id: str,
        user_id: str,
        title: str,
        snapshot: dict[str, Any],
        events: list[dict[str, Any]],
    ) -> None:
        now = now_ts()
        with self.engine.begin() as conn:
            existing = conn.execute(
                text("SELECT created_at FROM sessions WHERE id = :id"), {"id": session_id}
            ).mappings().first()
            created_at = float(existing["created_at"]) if existing else now
            conn.execute(
                text(
                    """
                    INSERT INTO sessions
                        (id, user_id, title, snapshot, events, created_at, updated_at)
                    VALUES
                        (:id, :user_id, :title, CAST(:snapshot AS jsonb), CAST(:events AS jsonb), :created_at, :updated_at)
                    ON CONFLICT(id) DO UPDATE SET
                        user_id = excluded.user_id,
                        title = excluded.title,
                        snapshot = excluded.snapshot,
                        events = excluded.events,
                        updated_at = excluded.updated_at
                    """
                ),
                {
                    "id": session_id,
                    "user_id": user_id,
                    "title": title,
                    "snapshot": dump_json(snapshot),
                    "events": dump_json(events[-100:]),
                    "created_at": created_at,
                    "updated_at": now,
                },
            )

    def load_session(self, session_id: str) -> dict[str, Any] | None:
        with self.engine.begin() as conn:
            row = conn.execute(text("SELECT * FROM sessions WHERE id = :id"), {"id": session_id}).mappings().first()
        if row is None:
            return None
        data = dict(row)
        data["snapshot"] = load_json(data.pop("snapshot"))
        data["events"] = load_json(data.pop("events"))
        return data

    def save_game_slot(
        self,
        user_id: str,
        name: str,
        snapshot: dict[str, Any],
        events: list[dict[str, Any]],
    ) -> dict[str, Any]:
        slot_name = safe_name(name or "slot_1")
        now = now_ts()
        with self.engine.begin() as conn:
            row = conn.execute(
                text("SELECT id, created_at FROM saves WHERE user_id = :user_id AND name = :name"),
                {"user_id": user_id, "name": slot_name},
            ).mappings().first()
            save_id = str(row["id"]) if row else str(uuid.uuid4())
            created_at = float(row["created_at"]) if row else now
            conn.execute(
                text(
                    """
                    INSERT INTO saves
                        (id, user_id, name, snapshot, events, created_at, updated_at)
                    VALUES
                        (:id, :user_id, :name, CAST(:snapshot AS jsonb), CAST(:events AS jsonb), :created_at, :updated_at)
                    ON CONFLICT(user_id, name) DO UPDATE SET
                        snapshot = excluded.snapshot,
                        events = excluded.events,
                        updated_at = excluded.updated_at
                    """
                ),
                {
                    "id": save_id,
                    "user_id": user_id,
                    "name": slot_name,
                    "snapshot": dump_json(snapshot),
                    "events": dump_json(events[-100:]),
                    "created_at": created_at,
                    "updated_at": now,
                },
            )
        return {"id": save_id, "user_id": user_id, "name": slot_name, "updated_at": now}

    def list_saves(self, user_id: str) -> list[dict[str, Any]]:
        with self.engine.begin() as conn:
            rows = conn.execute(
                text("SELECT * FROM saves WHERE user_id = :user_id ORDER BY updated_at DESC"),
                {"user_id": user_id},
            ).mappings().all()
        result = []
        for row in rows:
            item = dict(row)
            snapshot = load_json(item.get("snapshot")) or {}
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
        slot_name = safe_name(name or "slot_1")
        with self.engine.begin() as conn:
            row = conn.execute(
                text("SELECT * FROM saves WHERE user_id = :user_id AND name = :name"),
                {"user_id": user_id, "name": slot_name},
            ).mappings().first()
        if row is None:
            return None
        data = dict(row)
        data["snapshot"] = load_json(data.pop("snapshot"))
        data["events"] = load_json(data.pop("events"))
        return data

    def save_model_config(self, config: dict[str, Any]) -> dict[str, Any]:
        now = now_ts()
        data = {
            "provider": str(config.get("provider") or "Agens"),
            "base_url": str(config.get("base_url") or "https://apihub.agnes-ai.com/v1"),
            "model": str(config.get("model") or "agnes-2.0-flash"),
            "api_key_masked": str(config.get("api_key_masked") or "<unset>"),
            "api_key_set": bool(config.get("api_key_set")),
            "updated_at": now,
        }
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO model_config
                        (id, provider, base_url, model, api_key_masked, api_key_set, updated_at)
                    VALUES
                        (1, :provider, :base_url, :model, :api_key_masked, :api_key_set, :updated_at)
                    ON CONFLICT(id) DO UPDATE SET
                        provider = excluded.provider,
                        base_url = excluded.base_url,
                        model = excluded.model,
                        api_key_masked = excluded.api_key_masked,
                        api_key_set = excluded.api_key_set,
                        updated_at = excluded.updated_at
                    """
                ),
                data,
            )
        return data

    def get_model_config(self) -> dict[str, Any] | None:
        with self.engine.begin() as conn:
            row = conn.execute(text("SELECT * FROM model_config WHERE id = 1")).mappings().first()
        return dict(row) if row else None
