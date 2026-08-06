"""Database factory and shared protocol for the web adapter (PostgreSQL only).

Option C consolidation: the SQLite backend was removed. Dev and test use the
established local PostgreSQL default when DATABASE_URL is unset; production
requires an explicit DATABASE_URL.
"""

from __future__ import annotations

import os
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
    def ping(self) -> bool: ...

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
    def register_user_atomic(
        self,
        username: str,
        password_hash: str,
        *,
        invite_code_hash: str | None = None,
        bootstrap_admin: bool = False,
    ) -> dict[str, Any]: ...

    # ── invites ───────────────────────────────────────────────────────────
    def create_invite_code(
        self,
        code_hash: str,
        role: str = "user",
        max_uses: int = 1,
        expires_at: float | None = None,
        created_by: str | None = None,
    ) -> dict[str, Any]: ...
    def consume_invite_code(self, code_hash: str) -> dict[str, Any] | None: ...

    # ── sessions / saves ─────────────────────────────────────────────────
    def save_session(
        self,
        session_id: str,
        user_id: str | None,
        title: str,
        snapshot: dict[str, Any],
        events: list[dict[str, Any]],
        *,
        guest_token_hash: str = "",
        expires_at: float | None = None,
    ) -> int: ...
    def load_session(self, session_id: str) -> dict[str, Any] | None: ...
    def load_guest_session(
        self, session_id: str, guest_token_hash: str
    ) -> dict[str, Any] | None: ...
    def delete_guest_session(self, guest_token_hash: str) -> int: ...
    def get_session_mutation(
        self, session_id: str, request_id: str
    ) -> dict[str, Any] | None: ...
    def commit_session_mutation(
        self,
        *,
        session_id: str,
        user_id: str | None,
        title: str,
        snapshot: dict[str, Any],
        events: list[dict[str, Any]],
        expected_version: int,
        request_id: str,
        operation: str,
        response: dict[str, Any],
        guest_token_hash: str = "",
        expires_at: float | None = None,
        turn: dict[str, Any] | None = None,
        start_run: dict[str, Any] | None = None,
        consume_legacy_bonuses: bool = False,
        terminal: dict[str, Any] | None = None,
        save_slot: dict[str, Any] | None = None,
        rewind_run: dict[str, Any] | None = None,
    ) -> dict[str, Any]: ...
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
    def save_user_model_config(self, user_id: str, config: dict[str, Any]) -> dict[str, Any]: ...
    def get_user_model_config(self, user_id: str) -> dict[str, Any] | None: ...
    def delete_user_model_config(self, user_id: str) -> None: ...

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


_LOCAL_DATABASE_URL = "postgresql+psycopg://jiayp2917@127.0.0.1:5432/agens_web"


def resolve_database_url() -> str:
    """Use an explicit URL, or the established local development database."""
    configured = os.environ.get("DATABASE_URL", "").strip()
    if configured:
        return configured
    if os.environ.get("AGENS_ENV", "").strip().lower() in {"prod", "production"}:
        raise RuntimeError("DATABASE_URL is required in production.")
    return _LOCAL_DATABASE_URL


def create_database():
    """Create the PostgreSQL web database."""
    from .database_postgres import PostgresWebDatabase

    return PostgresWebDatabase(resolve_database_url())
