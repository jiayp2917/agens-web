"""PostgreSQL storage for production deployment."""

from __future__ import annotations

import os
import uuid
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

from agens_novel.settings import Settings

from .catalog_seed import seed_catalogs
from .database_common import (
    dump_json,
    encode_game_turn_json,
    now_ts,
    player_progress_summary,
    row_with_json,
    safe_name,
    save_summary,
)
from .database_postgres_catalog import CatalogRepository
from .database_postgres_rewards import RewardsRepository
from .database_postgres_schema import POSTGRES_SCHEMA_STATEMENTS, schema_comment_statements
from .database_postgres_session import SessionMutationRepository
from .service_errors import DuplicateUsername, InvalidInvite


class PostgresWebDatabase:
    """PostgreSQL implementation matching the SQLite web database API."""

    def __init__(self, database_url: str | None = None) -> None:
        self.database_url = database_url or os.environ.get("DATABASE_URL", "")
        if not self.database_url:
            raise RuntimeError("DATABASE_URL is required (PostgreSQL-only since the Option C consolidation).")
        self.engine: Engine = create_engine(self.database_url, pool_pre_ping=True, future=True)
        self._catalog = CatalogRepository(self.engine)
        self._rewards = RewardsRepository(self.engine)
        self._session_mutation = SessionMutationRepository(self.engine)
        auto_ddl_requested = os.environ.get("AGENS_PG_AUTO_DDL", "").strip().lower() in ("1", "true", "yes")
        # Production is indicated by AGENS_ENV — the same variable
        # security.is_production_mode() reads. This previously read APP_ENV,
        # which silently desynced from the security checks when only AGENS_ENV
        # was set (as deploy/production.env.example does), leaving the DDL guard
        # bypassed in production. Keep both guards on one variable.
        env = os.environ.get("AGENS_ENV", "").strip().lower()
        # P3 DDL demotion: production runtime must never auto-DDL. The schema is
        # owned by alembic (revision 20260622_0004_ddl_disallow_production and later).
        # Fail closed instead of silently mutating the production schema.
        if env in ("prod", "production"):
            if auto_ddl_requested:
                raise RuntimeError(
                    "AGENS_PG_AUTO_DDL=1 is not allowed when AGENS_ENV is prod/production. "
                    "Run `alembic upgrade head` against the production database instead."
                )
            seed_catalogs(self)
        elif auto_ddl_requested:
            self.initialize()
        else:
            seed_catalogs(self)

    def initialize(self) -> None:
        with self.engine.begin() as conn:
            for statement in POSTGRES_SCHEMA_STATEMENTS:
                conn.execute(text(statement))
            for statement in schema_comment_statements():
                conn.execute(text(statement))
        # Seed AFTER the DDL transaction commits. seed_catalogs() opens its own
        # connection via list_catalog(); running it inside the ``begin()`` block
        # above would hit UndefinedTable on an empty DB (the new connection
        # cannot see the uncommitted CREATE TABLE results).
        seed_catalogs(self)

    def ping(self) -> bool:
        with self.engine.connect() as conn:
            return conn.execute(text("SELECT 1")).scalar_one() == 1

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

    def register_user_atomic(
        self,
        username: str,
        password_hash: str,
        *,
        invite_code_hash: str | None = None,
        bootstrap_admin: bool = False,
    ) -> dict[str, Any]:
        now = now_ts()
        user = {
            "id": str(uuid.uuid4()),
            "username": username,
            "password_hash": password_hash,
            "is_admin": False,
            "created_at": now,
            "updated_at": now,
        }
        try:
            with self.engine.begin() as conn:
                if bootstrap_admin:
                    conn.execute(
                        text(
                            "SELECT pg_advisory_xact_lock(hashtext('agens-web-bootstrap-admin'))"
                        )
                    )
                    if conn.execute(
                        text("SELECT 1 FROM users WHERE is_admin = TRUE LIMIT 1")
                    ).first():
                        raise InvalidInvite("首个管理员已存在。")
                    user["is_admin"] = True
                else:
                    invite = conn.execute(
                        text(
                            """
                            UPDATE invite_codes
                            SET uses = uses + 1
                            WHERE code_hash = :code_hash
                              AND disabled = FALSE
                              AND uses < max_uses
                              AND (expires_at IS NULL OR expires_at >= :now)
                            RETURNING role
                            """
                        ),
                        {"code_hash": invite_code_hash or "", "now": now},
                    ).mappings().first()
                    if invite is None:
                        raise InvalidInvite("邀请码无效或已用完。")
                    user["is_admin"] = str(invite["role"] or "user").lower() == "admin"
                conn.execute(
                    text(
                        """
                        INSERT INTO users
                            (id, username, password_hash, is_admin, created_at, updated_at)
                        VALUES
                            (:id, :username, :password_hash, :is_admin, :created_at, :updated_at)
                        """
                    ),
                    user,
                )
        except IntegrityError as exc:
            raise DuplicateUsername("用户名已存在。") from exc
        return user

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
        user_id: str | None,
        title: str,
        snapshot: dict[str, Any],
        events: list[dict[str, Any]],
        *,
        guest_token_hash: str = "",
        expires_at: float | None = None,
    ) -> int:
        now = now_ts()
        with self.engine.begin() as conn:
            existing = conn.execute(
                text("SELECT created_at, version FROM sessions WHERE id = :id"),
                {"id": session_id},
            ).mappings().first()
            created_at = float(existing["created_at"]) if existing else now
            version = int(existing["version"]) if existing else 0
            row = conn.execute(
                text(
                    """
                    INSERT INTO sessions
                        (id, user_id, guest_token_hash, expires_at, version, title,
                         snapshot, events, created_at, updated_at)
                    VALUES
                        (:id, :user_id, :guest_token_hash, :expires_at, :version, :title,
                         CAST(:snapshot AS jsonb), CAST(:events AS jsonb), :created_at, :updated_at)
                    ON CONFLICT(id) DO UPDATE SET
                        user_id = excluded.user_id,
                        guest_token_hash = excluded.guest_token_hash,
                        expires_at = excluded.expires_at,
                        title = excluded.title,
                        snapshot = excluded.snapshot,
                        events = excluded.events,
                        updated_at = excluded.updated_at
                    RETURNING version
                    """
                ),
                {
                    "id": session_id,
                    "user_id": user_id,
                    "guest_token_hash": guest_token_hash or None,
                    "expires_at": expires_at,
                    "version": version,
                    "title": title,
                    "snapshot": dump_json(snapshot),
                    "events": dump_json(events[-100:]),
                    "created_at": created_at,
                    "updated_at": now,
                },
            ).mappings().one()
        return int(row["version"])

    def load_session(self, session_id: str) -> dict[str, Any] | None:
        with self.engine.begin() as conn:
            row = conn.execute(text("SELECT * FROM sessions WHERE id = :id"), {"id": session_id}).mappings().first()
        return row_with_json(row) if row else None

    def load_guest_session(
        self,
        session_id: str,
        guest_token_hash: str,
    ) -> dict[str, Any] | None:
        with self.engine.begin() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT * FROM sessions
                    WHERE id = :id
                      AND user_id IS NULL
                      AND guest_token_hash = :guest_token_hash
                      AND (expires_at IS NULL OR expires_at >= :now)
                    """
                ),
                {
                    "id": session_id,
                    "guest_token_hash": guest_token_hash,
                    "now": now_ts(),
                },
            ).mappings().first()
        return row_with_json(row) if row else None

    def delete_guest_session(self, guest_token_hash: str) -> int:
        if not guest_token_hash:
            return 0
        with self.engine.begin() as conn:
            result = conn.execute(
                text(
                    "DELETE FROM sessions WHERE user_id IS NULL AND guest_token_hash = :token"
                ),
                {"token": guest_token_hash},
            )
        return int(result.rowcount or 0)

    def get_session_mutation(
        self,
        session_id: str,
        request_id: str,
    ) -> dict[str, Any] | None:
        return self._session_mutation.get_session_mutation(session_id, request_id)

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
    ) -> dict[str, Any]:
        return self._session_mutation.commit_session_mutation(
            session_id=session_id,
            user_id=user_id,
            title=title,
            snapshot=snapshot,
            events=events,
            expected_version=expected_version,
            request_id=request_id,
            operation=operation,
            response=response,
            guest_token_hash=guest_token_hash,
            expires_at=expires_at,
            turn=turn,
            start_run=start_run,
            consume_legacy_bonuses=consume_legacy_bonuses,
            terminal=terminal,
            save_slot=save_slot,
            rewind_run=rewind_run,
        )

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
        return [save_summary(row) for row in rows]

    def load_save(self, user_id: str, name: str) -> dict[str, Any] | None:
        slot_name = safe_name(name or "slot_1")
        with self.engine.begin() as conn:
            row = conn.execute(
                text("SELECT * FROM saves WHERE user_id = :user_id AND name = :name"),
                {"user_id": user_id, "name": slot_name},
            ).mappings().first()
        return row_with_json(row) if row else None

    def _model_config_data(self, config: dict[str, Any], *, updated_at: float | None = None) -> dict[str, Any]:
        return {
            "provider": str(config.get("provider") or "Agens"),
            "base_url": str(config.get("base_url") or Settings().base_url),
            "model": str(config.get("model") or Settings().model),
            "api_key_masked": str(config.get("api_key_masked") or "<unset>"),
            "api_key_set": bool(config.get("api_key_set")),
            "api_key_encrypted": str(config.get("api_key_encrypted") or ""),
            "updated_at": updated_at if updated_at is not None else now_ts(),
        }

    def save_model_config(self, config: dict[str, Any]) -> dict[str, Any]:
        data = self._model_config_data(config)
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO model_config
                        (id, provider, base_url, model, api_key_masked, api_key_set, api_key_encrypted, updated_at)
                    VALUES
                        (1, :provider, :base_url, :model, :api_key_masked, :api_key_set, :api_key_encrypted, :updated_at)
                    ON CONFLICT(id) DO UPDATE SET
                        provider = excluded.provider,
                        base_url = excluded.base_url,
                        model = excluded.model,
                        api_key_masked = excluded.api_key_masked,
                        api_key_set = excluded.api_key_set,
                        api_key_encrypted = excluded.api_key_encrypted,
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

    def save_user_model_config(self, user_id: str, config: dict[str, Any]) -> dict[str, Any]:
        data = self._model_config_data(config)
        data["user_id"] = user_id
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO user_model_configs
                        (user_id, provider, base_url, model, api_key_masked, api_key_set, api_key_encrypted, updated_at)
                    VALUES
                        (:user_id, :provider, :base_url, :model, :api_key_masked, :api_key_set, :api_key_encrypted, :updated_at)
                    ON CONFLICT(user_id) DO UPDATE SET
                        provider = excluded.provider,
                        base_url = excluded.base_url,
                        model = excluded.model,
                        api_key_masked = excluded.api_key_masked,
                        api_key_set = excluded.api_key_set,
                        api_key_encrypted = excluded.api_key_encrypted,
                        updated_at = excluded.updated_at
                    """
                ),
                data,
            )
        return data

    def get_user_model_config(self, user_id: str) -> dict[str, Any] | None:
        with self.engine.begin() as conn:
            row = conn.execute(
                text("SELECT * FROM user_model_configs WHERE user_id = :user_id"),
                {"user_id": user_id},
            ).mappings().first()
        return dict(row) if row else None

    def delete_user_model_config(self, user_id: str) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                text("DELETE FROM user_model_configs WHERE user_id = :user_id"),
                {"user_id": user_id},
            )

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
        return self._rewards.save_run_achievement(
            user_id, session_id, achievement_key, achievement_name, description, death_cause
        )

    def list_run_achievements(self, user_id: str, session_id: str = "") -> list[dict[str, Any]]:
        return self._rewards.list_run_achievements(user_id, session_id)

    def save_account_reward(
        self,
        user_id: str,
        reward_type: str,
        reward_value: str,
        label: str,
        source_session_id: str,
    ) -> dict[str, Any]:
        return self._rewards.save_account_reward(
            user_id, reward_type, reward_value, label, source_session_id
        )

    def list_account_rewards(self, user_id: str) -> list[dict[str, Any]]:
        return self._rewards.list_account_rewards(user_id)

    def save_legacy_bonus(
        self,
        user_id: str,
        bonus_type: str,
        bonus_value: str,
        label: str,
        source_session_id: str,
        runs_remaining: int = 1,
    ) -> dict[str, Any]:
        return self._rewards.save_legacy_bonus(
            user_id, bonus_type, bonus_value, label, source_session_id, runs_remaining
        )

    def list_legacy_bonuses(self, user_id: str) -> list[dict[str, Any]]:
        return self._rewards.list_legacy_bonuses(user_id)

    def consume_legacy_bonuses(self, user_id: str) -> int:
        return self._rewards.consume_legacy_bonuses(user_id)

    # ── Game-mode v5: run / turn / progress tracking ─────────────────────────
    # Spec §8.3 — game_turns JSONB + §11 rarity unlock gates.

    def record_game_run(self, user_id: str, *, session_id: str = "", char_name: str = "",
                        realm: str = "", death_cause: str = "", ascended: bool = False,
                        turn_count: int = 0, run_id: str | None = None) -> str:
        """Persist a finished run and bump player progress counters.

        Drives the rarity unlock gates (§11): 紫 needs 1 run, 橙 needs 1
        ascension, 红 needs 2 ascensions + 1 run.
        """
        now = now_ts()
        run_id = run_id or str(uuid.uuid4())
        with self.engine.begin() as conn:
            existing = conn.execute(
                text("SELECT id FROM game_runs WHERE id = :id"),
                {"id": run_id},
            ).mappings().first()
            if existing is not None:
                return str(existing["id"])
            conn.execute(
                text(
                    """
                    INSERT INTO game_runs
                        (id, user_id, session_id, char_name, realm, death_cause,
                         ascended, turn_count, started_at, finished_at, completed)
                    VALUES (:id, :user_id, :session_id, :char_name, :realm,
                            :death_cause, :ascended, :turn_count, :started_at,
                            :finished_at, TRUE)
                    """
                ),
                {
                    "id": run_id, "user_id": user_id, "session_id": session_id,
                    "char_name": char_name, "realm": realm, "death_cause": death_cause,
                    "ascended": bool(ascended), "turn_count": turn_count,
                    "started_at": now, "finished_at": now,
                },
            )
            row = conn.execute(
                text(
                    "SELECT runs_completed, ascension_count FROM player_progress WHERE user_id = :u"
                ),
                {"u": user_id},
            ).mappings().first()
            if row is None:
                conn.execute(
                    text(
                        """
                        INSERT INTO player_progress
                            (user_id, runs_completed, ascension_count, updated_at)
                        VALUES (:u, 1, :a, :now)
                        """
                    ),
                    {"u": user_id, "a": 1 if ascended else 0, "now": now},
                )
            else:
                conn.execute(
                    text(
                        """
                        UPDATE player_progress
                        SET runs_completed = runs_completed + 1,
                            ascension_count = ascension_count + :a,
                            updated_at = :now
                        WHERE user_id = :u
                        """
                    ),
                    {"a": 1 if ascended else 0, "now": now, "u": user_id},
                )
        return run_id

    def record_game_turn(self, run_id: str, turn_no: int, *, start_age: int,
                         elapsed_years: int, end_age: int, lifespan: int,
                         remaining_lifespan: int, choice_taken: str | None,
                         choices: list, state_delta: dict, state_after: dict,
                         calendar_summary: str, narrative: str, event_kind: str,
                         end_reason: str | None = None) -> str:
        """Append one settled turn to the game_turns log (spec §8.3)."""
        turn_id = str(uuid.uuid4())
        choices_json, delta_json, after_json = encode_game_turn_json(
            choices, state_delta, state_after,
        )
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO game_turns
                        (id, run_id, turn_no, start_age, elapsed_years, end_age, lifespan,
                         remaining_lifespan, choice_taken, choices, state_delta,
                         state_after, calendar_summary, narrative, event_kind,
                         end_reason)
                    VALUES (:id, :run_id, :turn_no, :start_age, :elapsed_years, :end_age,
                            :lifespan, :remaining_lifespan, :choice_taken,
                            CAST(:choices AS JSONB), CAST(:state_delta AS JSONB),
                            CAST(:state_after AS JSONB), :calendar_summary, :narrative,
                            :event_kind, :end_reason)
                    """
                ),
                {
                    "id": turn_id, "run_id": run_id, "turn_no": turn_no,
                    "start_age": start_age, "elapsed_years": elapsed_years,
                    "end_age": end_age, "lifespan": lifespan,
                    "remaining_lifespan": remaining_lifespan,
                    "choice_taken": choice_taken, "choices": choices_json,
                    "state_delta": delta_json, "state_after": after_json,
                    "calendar_summary": calendar_summary, "narrative": narrative,
                    "event_kind": event_kind, "end_reason": end_reason,
                },
            )
        return turn_id
    def get_player_progress(self, user_id: str) -> dict[str, Any]:
        """Return {runs_completed, ascension_count} for the rarity unlock gates."""
        with self.engine.begin() as conn:
            row = conn.execute(
                text(
                    "SELECT runs_completed, ascension_count FROM player_progress WHERE user_id = :u"
                ),
                {"u": user_id},
            ).mappings().first()
        return player_progress_summary(row)

    # ── Catalog read/write ──────────────────────────────────────────────────
    # SQL/row shaping lives in CatalogRepository; these preserve the public
    # WebDatabaseProtocol surface as a thin facade.

    def list_catalog(self, table: str) -> list[dict[str, Any]]:
        return self._catalog.list_catalog(table)

    def insert_catalog(self, table: str, row: dict[str, Any]) -> dict[str, Any]:
        return self._catalog.insert_catalog(table, row)

    def supplement_catalog_metadata(
        self,
        table: str,
        name: str,
        metadata: dict[str, Any],
    ) -> bool:
        return self._catalog.supplement_catalog_metadata(table, name, metadata)
