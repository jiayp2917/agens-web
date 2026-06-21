"""PostgreSQL storage for production deployment."""

from __future__ import annotations

import os
import uuid
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from .database_common import dump_json, load_json, now_ts, safe_name
from .catalog_seed import seed_catalogs


class PostgresWebDatabase:
    """PostgreSQL implementation matching the SQLite web database API."""

    def __init__(self, database_url: str | None = None) -> None:
        self.database_url = database_url or os.environ.get("DATABASE_URL", "")
        if not self.database_url:
            raise RuntimeError("DATABASE_URL is required when DATABASE_BACKEND=postgresql")
        self.engine: Engine = create_engine(self.database_url, pool_pre_ping=True, future=True)
        if os.environ.get("AGENS_PG_AUTO_DDL", "").strip().lower() in ("1", "true", "yes"):
            self.initialize()
        else:
            seed_catalogs(self)

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
            conn.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS catalog_talents (
                        id TEXT PRIMARY KEY,
                        name TEXT NOT NULL UNIQUE,
                        rarity TEXT NOT NULL DEFAULT '普通',
                        description TEXT NOT NULL DEFAULT '',
                        attribute_mods JSONB NOT NULL DEFAULT '{}',
                        tags JSONB NOT NULL DEFAULT '[]',
                        created_at DOUBLE PRECISION NOT NULL
                    )
                    """
                )
            )
            conn.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS catalog_family_backgrounds (
                        id TEXT PRIMARY KEY,
                        name TEXT NOT NULL UNIQUE,
                        rarity TEXT NOT NULL DEFAULT '普通',
                        description TEXT NOT NULL DEFAULT '',
                        initial_resources JSONB NOT NULL DEFAULT '{}',
                        initial_risks JSONB NOT NULL DEFAULT '[]',
                        story_tags JSONB NOT NULL DEFAULT '[]',
                        created_at DOUBLE PRECISION NOT NULL
                    )
                    """
                )
            )
            conn.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS catalog_spirit_roots (
                        id TEXT PRIMARY KEY,
                        name TEXT NOT NULL UNIQUE,
                        element TEXT NOT NULL DEFAULT '',
                        grade TEXT NOT NULL DEFAULT '地',
                        cultivation_bonus DOUBLE PRECISION NOT NULL DEFAULT 1.0,
                        breakthrough_bonus DOUBLE PRECISION NOT NULL DEFAULT 0.0,
                        cultivation_tendency TEXT NOT NULL DEFAULT '',
                        event_tags JSONB NOT NULL DEFAULT '[]',
                        created_at DOUBLE PRECISION NOT NULL
                    )
                    """
                )
            )
            conn.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS catalog_difficulties (
                        id TEXT PRIMARY KEY,
                        name TEXT NOT NULL UNIQUE,
                        risk_multiplier DOUBLE PRECISION NOT NULL DEFAULT 1.0,
                        reward_multiplier DOUBLE PRECISION NOT NULL DEFAULT 1.0,
                        lifespan_modifier DOUBLE PRECISION NOT NULL DEFAULT 1.0,
                        luck_modifier DOUBLE PRECISION NOT NULL DEFAULT 0,
                        description TEXT NOT NULL DEFAULT '',
                        created_at DOUBLE PRECISION NOT NULL
                    )
                    """
                )
            )
            conn.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS catalog_story_seeds (
                        id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        category TEXT NOT NULL DEFAULT '',
                        description TEXT NOT NULL DEFAULT '',
                        tags JSONB NOT NULL DEFAULT '[]',
                        created_at DOUBLE PRECISION NOT NULL
                    )
                    """
                )
            )
            conn.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS run_achievements (
                        id TEXT PRIMARY KEY,
                        user_id TEXT NOT NULL REFERENCES users(id),
                        session_id TEXT NOT NULL,
                        achievement_key TEXT NOT NULL,
                        achievement_name TEXT NOT NULL,
                        description TEXT NOT NULL DEFAULT '',
                        death_cause TEXT NOT NULL DEFAULT '',
                        achieved_at DOUBLE PRECISION NOT NULL
                    )
                    """
                )
            )
            conn.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS account_rewards (
                        id TEXT PRIMARY KEY,
                        user_id TEXT NOT NULL REFERENCES users(id),
                        reward_type TEXT NOT NULL,
                        reward_value TEXT NOT NULL,
                        label TEXT NOT NULL DEFAULT '',
                        source_session_id TEXT NOT NULL DEFAULT '',
                        granted_at DOUBLE PRECISION NOT NULL
                    )
                    """
                )
            )
            conn.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS legacy_bonuses (
                        id TEXT PRIMARY KEY,
                        user_id TEXT NOT NULL REFERENCES users(id),
                        bonus_type TEXT NOT NULL,
                        bonus_value TEXT NOT NULL,
                        label TEXT NOT NULL DEFAULT '',
                        runs_remaining INTEGER NOT NULL DEFAULT 1,
                        source_session_id TEXT NOT NULL DEFAULT '',
                        granted_at DOUBLE PRECISION NOT NULL
                    )
                    """
                )
            )
            seed_catalogs(self)

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

    # ── Death rewards (P4) ──────────────────────────────────────────────────

    def save_run_achievement(
        self,
        user_id: str,
        session_id: str,
        achievement_key: str,
        achievement_name: str,
        description: str,
        death_cause: str,
    ) -> dict[str, Any]:
        achievement_id = str(uuid.uuid4())
        now = now_ts()
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO run_achievements
                        (id, user_id, session_id, achievement_key, achievement_name,
                         description, death_cause, achieved_at)
                    VALUES
                        (:id, :user_id, :session_id, :achievement_key, :achievement_name,
                         :description, :death_cause, :achieved_at)
                    """
                ),
                {
                    "id": achievement_id,
                    "user_id": user_id,
                    "session_id": session_id,
                    "achievement_key": achievement_key,
                    "achievement_name": achievement_name,
                    "description": description,
                    "death_cause": death_cause,
                    "achieved_at": now,
                },
            )
        return {
            "id": achievement_id,
            "user_id": user_id,
            "session_id": session_id,
            "achievement_key": achievement_key,
            "achievement_name": achievement_name,
            "description": description,
            "death_cause": death_cause,
            "achieved_at": now,
        }

    def list_run_achievements(self, user_id: str, session_id: str = "") -> list[dict[str, Any]]:
        with self.engine.begin() as conn:
            if session_id:
                rows = conn.execute(
                    text(
                        """
                        SELECT * FROM run_achievements
                        WHERE user_id = :user_id AND session_id = :session_id
                        ORDER BY achieved_at
                        """
                    ),
                    {"user_id": user_id, "session_id": session_id},
                ).mappings().all()
            else:
                rows = conn.execute(
                    text(
                        """
                        SELECT * FROM run_achievements
                        WHERE user_id = :user_id
                        ORDER BY achieved_at DESC
                        """
                    ),
                    {"user_id": user_id},
                ).mappings().all()
        return [dict(row) for row in rows]

    def save_account_reward(
        self,
        user_id: str,
        reward_type: str,
        reward_value: str,
        label: str,
        source_session_id: str,
    ) -> dict[str, Any]:
        reward_id = str(uuid.uuid4())
        now = now_ts()
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO account_rewards
                        (id, user_id, reward_type, reward_value, label,
                         source_session_id, granted_at)
                    VALUES
                        (:id, :user_id, :reward_type, :reward_value, :label,
                         :source_session_id, :granted_at)
                    """
                ),
                {
                    "id": reward_id,
                    "user_id": user_id,
                    "reward_type": reward_type,
                    "reward_value": str(reward_value),
                    "label": label,
                    "source_session_id": source_session_id,
                    "granted_at": now,
                },
            )
        return {
            "id": reward_id,
            "user_id": user_id,
            "reward_type": reward_type,
            "reward_value": str(reward_value),
            "label": label,
            "source_session_id": source_session_id,
            "granted_at": now,
        }

    def list_account_rewards(self, user_id: str) -> list[dict[str, Any]]:
        with self.engine.begin() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT * FROM account_rewards
                    WHERE user_id = :user_id
                    ORDER BY granted_at DESC
                    """
                ),
                {"user_id": user_id},
            ).mappings().all()
        return [dict(row) for row in rows]

    def save_legacy_bonus(
        self,
        user_id: str,
        bonus_type: str,
        bonus_value: str,
        label: str,
        source_session_id: str,
        runs_remaining: int = 1,
    ) -> dict[str, Any]:
        bonus_id = str(uuid.uuid4())
        now = now_ts()
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO legacy_bonuses
                        (id, user_id, bonus_type, bonus_value, label,
                         runs_remaining, source_session_id, granted_at)
                    VALUES
                        (:id, :user_id, :bonus_type, :bonus_value, :label,
                         :runs_remaining, :source_session_id, :granted_at)
                    """
                ),
                {
                    "id": bonus_id,
                    "user_id": user_id,
                    "bonus_type": bonus_type,
                    "bonus_value": str(bonus_value),
                    "label": label,
                    "runs_remaining": int(runs_remaining),
                    "source_session_id": source_session_id,
                    "granted_at": now,
                },
            )
        return {
            "id": bonus_id,
            "user_id": user_id,
            "bonus_type": bonus_type,
            "bonus_value": str(bonus_value),
            "label": label,
            "runs_remaining": int(runs_remaining),
            "source_session_id": source_session_id,
            "granted_at": now,
        }

    def list_legacy_bonuses(self, user_id: str) -> list[dict[str, Any]]:
        with self.engine.begin() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT * FROM legacy_bonuses
                    WHERE user_id = :user_id AND runs_remaining > 0
                    ORDER BY granted_at
                    """
                ),
                {"user_id": user_id},
            ).mappings().all()
        return [dict(row) for row in rows]

    def consume_legacy_bonuses(self, user_id: str) -> int:
        """Decrement runs_remaining for all bonuses owned by the user."""
        consumed = 0
        with self.engine.begin() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT id, runs_remaining FROM legacy_bonuses
                    WHERE user_id = :user_id AND runs_remaining > 0
                    """
                ),
                {"user_id": user_id},
            ).mappings().all()
            for row in rows:
                remaining = int(row["runs_remaining"]) - 1
                if remaining <= 0:
                    conn.execute(
                        text("UPDATE legacy_bonuses SET runs_remaining = 0 WHERE id = :id"),
                        {"id": row["id"]},
                    )
                    consumed += 1
                else:
                    conn.execute(
                        text(
                            "UPDATE legacy_bonuses SET runs_remaining = :r WHERE id = :id"
                        ),
                        {"r": remaining, "id": row["id"]},
                    )
        return consumed

    # ── Catalog read/write ──────────────────────────────────────────────────

    _CATALOG_TABLES = [
        "catalog_talents",
        "catalog_family_backgrounds",
        "catalog_spirit_roots",
        "catalog_difficulties",
        "catalog_story_seeds",
    ]

    def list_catalog(self, table: str) -> list[dict[str, Any]]:
        if table not in self._CATALOG_TABLES:
            raise ValueError(f"Unknown catalog table: {table}")
        with self.engine.begin() as conn:
            rows = conn.execute(
                text(f"SELECT * FROM {table} ORDER BY created_at")
            ).mappings().all()
        result = []
        for row in rows:
            item = dict(row)
            for field in ("attribute_mods", "tags", "initial_resources",
                          "initial_risks", "story_tags", "event_tags",
                          "snapshot", "events"):
                if field in item:
                    item[field] = load_json(item[field])
            result.append(item)
        return result

    def insert_catalog(self, table: str, row: dict[str, Any]) -> dict[str, Any]:
        if table not in self._CATALOG_TABLES:
            raise ValueError(f"Unknown catalog table: {table}")
        data = dict(row)
        for field in ("attribute_mods", "tags", "initial_resources",
                      "initial_risks", "story_tags", "event_tags"):
            if field in data and not isinstance(data[field], str):
                data[field] = dump_json(data[field])
        cols = ", ".join(data.keys())
        placeholders = ", ".join(f":{k}" for k in data.keys())
        with self.engine.begin() as conn:
            conn.execute(
                text(f"INSERT INTO {table} ({cols}) VALUES ({placeholders}) ON CONFLICT DO NOTHING"),
                data,
            )
        return dict(row)

    def _seed_catalogs_if_empty(self) -> None:
        """Seed catalog tables from seed data when they're empty."""
        from .catalog_seed import SEED_TALENTS, SEED_FAMILY_BACKGROUNDS, SEED_SPIRIT_ROOTS
        from .catalog_seed import SEED_DIFFICULTIES, SEED_STORY_SEEDS

        seeds = [
            ("catalog_talents", SEED_TALENTS),
            ("catalog_family_backgrounds", SEED_FAMILY_BACKGROUNDS),
            ("catalog_spirit_roots", SEED_SPIRIT_ROOTS),
            ("catalog_difficulties", SEED_DIFFICULTIES),
            ("catalog_story_seeds", SEED_STORY_SEEDS),
        ]
        for table, rows in seeds:
            with self.engine.begin() as conn:
                existing = conn.execute(
                    text(f"SELECT 1 FROM {table} LIMIT 1")
                ).first()
                if existing:
                    continue
                for row in rows:
                    data = dict(row)
                    data.setdefault("created_at", now_ts())
                    for field in ("attribute_mods", "tags", "initial_resources",
                                  "initial_risks", "story_tags", "event_tags"):
                        if field in data and not isinstance(data[field], str):
                            data[field] = dump_json(data[field])
                    cols = ", ".join(data.keys())
                    placeholders = ", ".join(f":{k}" for k in data.keys())
                    conn.execute(
                        text(f"INSERT INTO {table} ({cols}) VALUES ({placeholders}) ON CONFLICT DO NOTHING"),
                        data,
                    )
