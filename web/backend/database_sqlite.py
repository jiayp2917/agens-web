"""SQLite storage for local development and tests."""

from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path
from typing import Any

from .database_common import default_db_path, dump_json, load_json, now_ts, row_with_json, safe_name


class SQLiteWebDatabase:
    """SQLite wrapper for users, invites, sessions, saves, and model summaries."""

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
                    password_hash TEXT,
                    is_admin INTEGER NOT NULL DEFAULT 0,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS invite_codes (
                    id TEXT PRIMARY KEY,
                    code_hash TEXT NOT NULL UNIQUE,
                    role TEXT NOT NULL DEFAULT 'user',
                    max_uses INTEGER NOT NULL DEFAULT 1,
                    uses INTEGER NOT NULL DEFAULT 0,
                    expires_at REAL,
                    disabled INTEGER NOT NULL DEFAULT 0,
                    created_at REAL NOT NULL,
                    created_by TEXT
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

                CREATE TABLE IF NOT EXISTS catalog_talents (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL UNIQUE,
                    rarity TEXT NOT NULL DEFAULT '普通',
                    description TEXT NOT NULL DEFAULT '',
                    attribute_mods TEXT NOT NULL DEFAULT '{}',
                    tags TEXT NOT NULL DEFAULT '[]',
                    created_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS catalog_family_backgrounds (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL UNIQUE,
                    rarity TEXT NOT NULL DEFAULT '普通',
                    description TEXT NOT NULL DEFAULT '',
                    initial_resources TEXT NOT NULL DEFAULT '{}',
                    initial_risks TEXT NOT NULL DEFAULT '[]',
                    story_tags TEXT NOT NULL DEFAULT '[]',
                    created_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS catalog_spirit_roots (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL UNIQUE,
                    element TEXT NOT NULL DEFAULT '',
                    grade TEXT NOT NULL DEFAULT '地',
                    cultivation_bonus REAL NOT NULL DEFAULT 1.0,
                    breakthrough_bonus REAL NOT NULL DEFAULT 0.0,
                    cultivation_tendency TEXT NOT NULL DEFAULT '',
                    event_tags TEXT NOT NULL DEFAULT '[]',
                    created_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS catalog_difficulties (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL UNIQUE,
                    risk_multiplier REAL NOT NULL DEFAULT 1.0,
                    reward_multiplier REAL NOT NULL DEFAULT 1.0,
                    lifespan_modifier REAL NOT NULL DEFAULT 1.0,
                    luck_modifier REAL NOT NULL DEFAULT 0,
                    description TEXT NOT NULL DEFAULT '',
                    created_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS catalog_story_seeds (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    category TEXT NOT NULL DEFAULT '',
                    description TEXT NOT NULL DEFAULT '',
                    tags TEXT NOT NULL DEFAULT '[]',
                    created_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS run_achievements (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    achievement_key TEXT NOT NULL,
                    achievement_name TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    death_cause TEXT NOT NULL DEFAULT '',
                    achieved_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS account_rewards (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    reward_type TEXT NOT NULL,
                    reward_value TEXT NOT NULL,
                    label TEXT NOT NULL DEFAULT '',
                    source_session_id TEXT NOT NULL DEFAULT '',
                    granted_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS legacy_bonuses (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    bonus_type TEXT NOT NULL,
                    bonus_value TEXT NOT NULL,
                    label TEXT NOT NULL DEFAULT '',
                    runs_remaining INTEGER NOT NULL DEFAULT 1,
                    source_session_id TEXT NOT NULL DEFAULT '',
                    granted_at REAL NOT NULL
                );
                """
            )
            self._ensure_user_columns(conn)
            self._seed_catalogs_if_empty(conn)

    def _ensure_user_columns(self, conn: sqlite3.Connection) -> None:
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(users)").fetchall()}
        if "password_hash" not in columns:
            conn.execute("ALTER TABLE users ADD COLUMN password_hash TEXT")
        if "is_admin" not in columns:
            conn.execute("ALTER TABLE users ADD COLUMN is_admin INTEGER NOT NULL DEFAULT 0")
        if "updated_at" not in columns:
            conn.execute("ALTER TABLE users ADD COLUMN updated_at REAL")
            conn.execute("UPDATE users SET updated_at = created_at WHERE updated_at IS NULL")

    def upsert_user(self, username: str) -> dict[str, Any]:
        username = (username or "local").strip() or "local"
        now = now_ts()
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
            if row is None:
                user_id = str(uuid.uuid4())
                conn.execute(
                    """
                    INSERT INTO users (id, username, password_hash, is_admin, created_at, updated_at)
                    VALUES (?, ?, NULL, 0, ?, ?)
                    """,
                    (user_id, username, now, now),
                )
                return {
                    "id": user_id,
                    "username": username,
                    "password_hash": None,
                    "is_admin": 0,
                    "created_at": now,
                    "updated_at": now,
                }
            return dict(row)

    def create_user(
        self,
        username: str,
        password_hash: str,
        is_admin: bool = False,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        now = now_ts()
        user_id = user_id or str(uuid.uuid4())
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO users (id, username, password_hash, is_admin, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (user_id, username, password_hash, 1 if is_admin else 0, now, now),
            )
        return {
            "id": user_id,
            "username": username,
            "password_hash": password_hash,
            "is_admin": 1 if is_admin else 0,
            "created_at": now,
            "updated_at": now,
        }

    def get_user_by_username(self, username: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        return dict(row) if row else None

    def get_user_by_id(self, user_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return dict(row) if row else None

    def has_admin_user(self) -> bool:
        with self.connect() as conn:
            row = conn.execute("SELECT 1 FROM users WHERE is_admin = 1 LIMIT 1").fetchone()
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
        invite_id = str(uuid.uuid4())
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO invite_codes
                    (id, code_hash, role, max_uses, uses, expires_at, disabled, created_at, created_by)
                VALUES (?, ?, ?, ?, 0, ?, 0, ?, ?)
                """,
                (invite_id, code_hash, role, int(max_uses), expires_at, now, created_by),
            )
        return {
            "id": invite_id,
            "code_hash": code_hash,
            "role": role,
            "max_uses": int(max_uses),
            "uses": 0,
            "expires_at": expires_at,
            "created_at": now,
            "created_by": created_by,
        }

    def get_invite_code(self, code_hash: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM invite_codes WHERE code_hash = ?", (code_hash,)).fetchone()
        return dict(row) if row else None

    def consume_invite_code(self, code_hash: str) -> dict[str, Any] | None:
        now = now_ts()
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM invite_codes WHERE code_hash = ?", (code_hash,)).fetchone()
            if row is None:
                return None
            invite = dict(row)
            expired = invite.get("expires_at") is not None and float(invite["expires_at"]) < now
            exhausted = int(invite.get("uses") or 0) >= int(invite.get("max_uses") or 1)
            if invite.get("disabled") or expired or exhausted:
                return None
            conn.execute(
                "UPDATE invite_codes SET uses = uses + 1 WHERE code_hash = ?",
                (code_hash,),
            )
        invite["uses"] = int(invite.get("uses") or 0) + 1
        return invite

    def save_session(
        self,
        session_id: str,
        user_id: str,
        title: str,
        snapshot: dict[str, Any],
        events: list[dict[str, Any]],
    ) -> None:
        now = now_ts()
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
                    dump_json(snapshot),
                    dump_json(events[-100:]),
                    created_at,
                    now,
                ),
            )

    def load_session(self, session_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
        return row_with_json(row) if row else None

    def save_game_slot(
        self,
        user_id: str,
        name: str,
        snapshot: dict[str, Any],
        events: list[dict[str, Any]],
    ) -> dict[str, Any]:
        slot_name = safe_name(name or "slot_1")
        now = now_ts()
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
                    dump_json(snapshot),
                    dump_json(events[-100:]),
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
            item = row_with_json(row)
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
        slot_name = safe_name(name or "slot_1")
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM saves WHERE user_id = ? AND name = ?", (user_id, slot_name)
            ).fetchone()
        return row_with_json(row) if row else None

    def save_model_config(self, config: dict[str, Any]) -> dict[str, Any]:
        now = now_ts()
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
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO run_achievements
                    (id, user_id, session_id, achievement_key, achievement_name,
                     description, death_cause, achieved_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    achievement_id,
                    user_id,
                    session_id,
                    achievement_key,
                    achievement_name,
                    description,
                    death_cause,
                    now,
                ),
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
        with self.connect() as conn:
            if session_id:
                rows = conn.execute(
                    """
                    SELECT * FROM run_achievements
                    WHERE user_id = ? AND session_id = ?
                    ORDER BY achieved_at
                    """,
                    (user_id, session_id),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM run_achievements
                    WHERE user_id = ?
                    ORDER BY achieved_at DESC
                    """,
                    (user_id,),
                ).fetchall()
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
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO account_rewards
                    (id, user_id, reward_type, reward_value, label,
                     source_session_id, granted_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    reward_id,
                    user_id,
                    reward_type,
                    str(reward_value),
                    label,
                    source_session_id,
                    now,
                ),
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
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM account_rewards
                WHERE user_id = ?
                ORDER BY granted_at DESC
                """,
                (user_id,),
            ).fetchall()
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
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO legacy_bonuses
                    (id, user_id, bonus_type, bonus_value, label,
                     runs_remaining, source_session_id, granted_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    bonus_id,
                    user_id,
                    bonus_type,
                    str(bonus_value),
                    label,
                    int(runs_remaining),
                    source_session_id,
                    now,
                ),
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
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM legacy_bonuses
                WHERE user_id = ? AND runs_remaining > 0
                ORDER BY granted_at
                """,
                (user_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def consume_legacy_bonuses(self, user_id: str) -> int:
        """Decrement runs_remaining for all bonuses owned by the user.

        Returns the count of bonuses that were fully consumed (set to 0).
        """
        now = now_ts()
        consumed = 0
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT id, runs_remaining FROM legacy_bonuses
                WHERE user_id = ? AND runs_remaining > 0
                """,
                (user_id,),
            ).fetchall()
            for row in rows:
                remaining = int(row["runs_remaining"]) - 1
                if remaining <= 0:
                    conn.execute(
                        "UPDATE legacy_bonuses SET runs_remaining = 0 WHERE id = ?",
                        (row["id"],),
                    )
                    consumed += 1
                else:
                    conn.execute(
                        "UPDATE legacy_bonuses SET runs_remaining = ? WHERE id = ?",
                        (remaining, row["id"]),
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
        with self.connect() as conn:
            rows = conn.execute(f"SELECT * FROM {table} ORDER BY created_at").fetchall()
        json_fields = {
            "attribute_mods", "tags", "initial_resources", "initial_risks",
            "story_tags", "event_tags",
        }
        result = []
        for row in rows:
            item = dict(row)
            for field in json_fields:
                if field in item and isinstance(item[field], str):
                    try:
                        item[field] = load_json(item[field])
                    except (json.JSONDecodeError, TypeError):
                        pass
            result.append(item)
        return result

    def insert_catalog(self, table: str, row: dict[str, Any]) -> dict[str, Any]:
        if table not in self._CATALOG_TABLES:
            raise ValueError(f"Unknown catalog table: {table}")
        json_fields = {
            "attribute_mods", "tags", "initial_resources", "initial_risks",
            "story_tags", "event_tags",
        }
        data = dict(row)
        for field in json_fields:
            if field in data and not isinstance(data[field], str):
                data[field] = dump_json(data[field])
        with self.connect() as conn:
            conn.execute(
                f"INSERT OR IGNORE INTO {table} ({', '.join(data.keys())}) "
                f"VALUES ({', '.join('?' for _ in data)})",
                tuple(data.values()),
            )
        return dict(row)

    def _seed_catalogs_if_empty(self, conn: sqlite3.Connection) -> None:
        """Seed catalog tables from seed data when they're empty.
        Called during initialize() — runs inside the existing transaction."""
        from .catalog_seed import SEED_TALENTS, SEED_FAMILY_BACKGROUNDS, SEED_SPIRIT_ROOTS
        from .catalog_seed import SEED_DIFFICULTIES, SEED_STORY_SEEDS

        now = now_ts()
        seeds = [
            ("catalog_talents", SEED_TALENTS),
            ("catalog_family_backgrounds", SEED_FAMILY_BACKGROUNDS),
            ("catalog_spirit_roots", SEED_SPIRIT_ROOTS),
            ("catalog_difficulties", SEED_DIFFICULTIES),
            ("catalog_story_seeds", SEED_STORY_SEEDS),
        ]
        json_fields = {
            "attribute_mods", "tags", "initial_resources", "initial_risks",
            "story_tags", "event_tags",
        }
        for table, rows in seeds:
            existing = conn.execute(f"SELECT 1 FROM {table} LIMIT 1").fetchone()
            if existing:
                continue
            for row in rows:
                row_with_ts = dict(row)
                row_with_ts.setdefault("created_at", now)
                # Serialize JSON fields to strings for SQLite
                for field in json_fields:
                    if field in row_with_ts and not isinstance(row_with_ts[field], str):
                        row_with_ts[field] = dump_json(row_with_ts[field])
                conn.execute(
                    f"INSERT OR IGNORE INTO {table} ({', '.join(row_with_ts.keys())}) "
                    f"VALUES ({', '.join('?' for _ in row_with_ts)})",
                    tuple(row_with_ts.values()),
                )
