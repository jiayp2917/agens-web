"""Database factory and shared protocol for the web adapter (PostgreSQL only).

Option C consolidation: the SQLite backend was removed. Dev, test, and
production all use PostgreSQL via DATABASE_URL.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Protocol


class WebDatabaseProtocol(Protocol):
    """Surface every public method exposed by the PostgreSQL backend.

    The backend normalizes JSON columns (``snapshot`` / ``events`` /
    ``attribute_mods`` / ``tags`` / ``initial_resources`` /
    ``initial_risks`` / ``story_tags`` / ``event_tags`` / ``choices`` /
    ``state_delta`` / ``state_after``) through ``database_common.load_json``
    before returning, so consumers can treat them as decoded structures.

    Not ``@runtime_checkable`` — the concrete classes are duck-typed and we
    want static type narrowing without forcing nominal imports everywhere.
    """

    # ── lifecycle ─────────────────────────────────────────────────────────
    def initialize(self) -> None: ...

    # ── users ─────────────────────────────────────────────────────────────
    def upsert_user(self, username: str) -> dict[str, Any]: ...
    def create_user(
        self,
        username: str,
        password_hash: str,
        is_admin: bool = False,
        user_id: str | None = None,
    ) -> dict[str, Any]: ...
    def get_user_by_username(self, username: str) -> dict[str, Any] | None: ...
    def get_user_by_id(self, user_id: str) -> dict[str, Any] | None: ...
    def has_admin_user(self) -> bool: ...

    # ── invites ───────────────────────────────────────────────────────────
    def create_invite_code(
        self,
        code_hash: str,
        role: str = "user",
        max_uses: int = 1,
        expires_at: float | None = None,
        created_by: str | None = None,
    ) -> dict[str, Any]: ...
    def get_invite_code(self, code_hash: str) -> dict[str, Any] | None: ...
    def consume_invite_code(self, code_hash: str) -> dict[str, Any] | None: ...

    # ── sessions / saves ─────────────────────────────────────────────────
    def save_session(
        self,
        session_id: str,
        user_id: str,
        title: str,
        snapshot: dict[str, Any],
        events: list[dict[str, Any]],
    ) -> None: ...
    def load_session(self, session_id: str) -> dict[str, Any] | None: ...
    def save_game_slot(
        self,
        user_id: str,
        name: str,
        snapshot: dict[str, Any],
        events: list[dict[str, Any]],
    ) -> dict[str, Any]: ...
    def list_saves(self, user_id: str) -> list[dict[str, Any]]: ...
    def load_save(self, user_id: str, name: str) -> dict[str, Any] | None: ...

    # ── model_config ──────────────────────────────────────────────────────
    def save_model_config(self, config: dict[str, Any]) -> dict[str, Any]: ...
    def get_model_config(self) -> dict[str, Any] | None: ...

    # ── death rewards (P4) ───────────────────────────────────────────────
    def save_run_achievement(
        self,
        user_id: str,
        session_id: str,
        achievement_key: str,
        achievement_name: str,
        description: str,
        death_cause: str,
    ) -> dict[str, Any]: ...
    def list_run_achievements(
        self, user_id: str, session_id: str = ""
    ) -> list[dict[str, Any]]: ...
    def save_account_reward(
        self,
        user_id: str,
        reward_type: str,
        reward_value: str,
        label: str,
        source_session_id: str,
    ) -> dict[str, Any]: ...
    def list_account_rewards(self, user_id: str) -> list[dict[str, Any]]: ...
    def save_legacy_bonus(
        self,
        user_id: str,
        bonus_type: str,
        bonus_value: str,
        label: str,
        source_session_id: str,
        runs_remaining: int = 1,
    ) -> dict[str, Any]: ...
    def list_legacy_bonuses(self, user_id: str) -> list[dict[str, Any]]: ...
    def consume_legacy_bonuses(self, user_id: str) -> int: ...

    # ── game-mode v5 run / turn / progress ────────────────────────────────
    def record_game_run(
        self,
        user_id: str,
        *,
        session_id: str = "",
        char_name: str = "",
        realm: str = "",
        death_cause: str = "",
        ascended: bool = False,
        turn_count: int = 0,
        run_id: str | None = None,
    ) -> str: ...
    def record_game_turn(
        self,
        run_id: str,
        turn_no: int,
        *,
        start_age: int,
        elapsed_years: int,
        end_age: int,
        lifespan: int,
        remaining_lifespan: int,
        choice_taken: str | None,
        choices: list,
        state_delta: dict,
        state_after: dict,
        calendar_summary: str,
        narrative: str,
        event_kind: str,
        end_reason: str | None = None,
    ) -> str: ...
    def get_player_progress(self, user_id: str) -> dict[str, Any]: ...

    # ── catalog read/write ───────────────────────────────────────────────
    def list_catalog(self, table: str) -> list[dict[str, Any]]: ...
    def insert_catalog(self, table: str, row: dict[str, Any]) -> dict[str, Any]: ...


def create_database(db_path: Path | None = None):
    """Create the PostgreSQL web database.

    ``db_path`` is accepted for backward compatibility with ``create_app()``
    callers but ignored — the connection always comes from ``DATABASE_URL``.
    """
    from .database_postgres import PostgresWebDatabase

    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "DATABASE_URL is required (PostgreSQL-only since the Option C consolidation)."
        )
    return PostgresWebDatabase(url)
