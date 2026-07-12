"""Session-mutation repository extracted from PostgresWebDatabase.

Holds the CAS/idempotent mutation path (``get_session_mutation``,
``commit_session_mutation``) and its transaction-bound helpers.
``PostgresWebDatabase`` delegates the two public methods here; its API
(``WebDatabaseProtocol``) and on-disk schema are unchanged.

All helpers take a ``conn: Connection`` so they run inside the caller's
transaction — they do not open their own ``engine.begin()``. The terminal
settlement path (``_finalize_terminal``) keeps its inline idempotent writes
to the reward tables because they commit atomically with the rest of the
session mutation.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine

from .database_common import (
    dump_json,
    encode_game_turn_json,
    now_ts,
    row_with_json,
    safe_name,
)
from .service_errors import SessionVersionConflict


def _response_with_version(response: dict[str, Any], version: int) -> dict[str, Any]:
    result = dict(response)
    if isinstance(result.get("session"), dict):
        result["session"] = {**result["session"], "version": version}
    else:
        result["version"] = version
    return result


class SessionMutationRepository:
    """CAS-protected session persistence: idempotency, turn/run, terminal writes."""

    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def get_session_mutation(
        self,
        session_id: str,
        request_id: str,
    ) -> dict[str, Any] | None:
        if not request_id:
            return None
        with self.engine.begin() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT response FROM session_mutations
                    WHERE session_id = :session_id AND request_id = :request_id
                    """
                ),
                {"session_id": session_id, "request_id": request_id},
            ).mappings().first()
        if row is None:
            return None
        response = row["response"]
        return response if isinstance(response, dict) else row_with_json({"snapshot": response})["snapshot"]

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
        now = now_ts()
        with self.engine.begin() as conn:
            existing = self._mutation_response(conn, session_id, request_id)
            if existing is not None:
                return existing

            updated = conn.execute(
                text(
                    """
                    UPDATE sessions
                    SET user_id = :user_id,
                        guest_token_hash = :guest_token_hash,
                        expires_at = :expires_at,
                        title = :title,
                        snapshot = CAST(:snapshot AS JSONB),
                        events = CAST(:events AS JSONB),
                        version = version + 1,
                        updated_at = :updated_at
                    WHERE id = :session_id AND version = :expected_version
                    RETURNING version
                    """
                ),
                {
                    "session_id": session_id,
                    "user_id": user_id,
                    "guest_token_hash": guest_token_hash or None,
                    "expires_at": expires_at,
                    "title": title,
                    "snapshot": dump_json(snapshot),
                    "events": dump_json(events[-100:]),
                    "updated_at": now,
                    "expected_version": expected_version,
                },
            ).mappings().first()
            if updated is None:
                existing = self._mutation_response(conn, session_id, request_id)
                if existing is not None:
                    return existing
                raise SessionVersionConflict("局面已更新，请刷新后重试。")

            result_version = int(updated["version"])
            result_response = _response_with_version(response, result_version)
            if start_run and user_id:
                self._ensure_active_run(conn, session_id, user_id, start_run, now)
            if rewind_run and user_id:
                self._rewind_active_run(conn, session_id, user_id, rewind_run, now)
            if turn and user_id:
                self._insert_turn(conn, session_id, request_id, turn)
            if consume_legacy_bonuses and user_id:
                conn.execute(
                    text(
                        """
                        UPDATE legacy_bonuses
                        SET runs_remaining = GREATEST(0, runs_remaining - 1)
                        WHERE user_id = :user_id AND runs_remaining > 0
                        """
                    ),
                    {"user_id": user_id},
                )
            if terminal and user_id:
                self._finalize_terminal(conn, session_id, user_id, terminal, now)
            if save_slot and user_id:
                result_response["save"] = self._save_slot_conn(
                    conn,
                    user_id,
                    save_slot,
                    now,
                )

            conn.execute(
                text(
                    """
                    INSERT INTO session_mutations
                        (session_id, request_id, operation, expected_version,
                         result_version, response, created_at)
                    VALUES
                        (:session_id, :request_id, :operation, :expected_version,
                         :result_version, CAST(:response AS JSONB), :created_at)
                    """
                ),
                {
                    "session_id": session_id,
                    "request_id": request_id,
                    "operation": operation,
                    "expected_version": expected_version,
                    "result_version": result_version,
                    "response": dump_json(result_response),
                    "created_at": now,
                },
            )
        return result_response

    def _rewind_active_run(
        self,
        conn: Connection,
        session_id: str,
        user_id: str,
        data: dict[str, Any],
        now: float,
    ) -> None:
        run = conn.execute(
            text("SELECT completed FROM game_runs WHERE id = :run_id FOR UPDATE"),
            {"run_id": session_id},
        ).mappings().first()
        if run is not None and bool(run["completed"]):
            raise SessionVersionConflict("终局已结算，不能在原会话覆盖历史；请新建会话后读取存档。")
        if run is None:
            self._ensure_active_run(conn, session_id, user_id, data, now)
        turn_count = max(0, int(data.get("turn_count") or 0))
        conn.execute(
            text("DELETE FROM game_turns WHERE run_id = :run_id AND turn_no > :turn_count"),
            {"run_id": session_id, "turn_count": turn_count},
        )
        conn.execute(
            text(
                """
                UPDATE game_runs
                SET turn_count = :turn_count,
                    char_name = :char_name,
                    realm = :realm
                WHERE id = :run_id AND completed = FALSE
                """
            ),
            {
                "run_id": session_id,
                "turn_count": turn_count,
                "char_name": str(data.get("char_name") or ""),
                "realm": str(data.get("realm") or ""),
            },
        )
        conn.execute(
            text("DELETE FROM session_mutations WHERE session_id = :session_id"),
            {"session_id": session_id},
        )

    def _mutation_response(
        self,
        conn: Connection,
        session_id: str,
        request_id: str,
    ) -> dict[str, Any] | None:
        row = conn.execute(
            text(
                """
                SELECT response FROM session_mutations
                WHERE session_id = :session_id AND request_id = :request_id
                """
            ),
            {"session_id": session_id, "request_id": request_id},
        ).mappings().first()
        if row is None:
            return None
        response = row["response"]
        if isinstance(response, dict):
            return response
        return row_with_json({"snapshot": response})["snapshot"]

    def _ensure_active_run(
        self,
        conn: Connection,
        session_id: str,
        user_id: str,
        data: dict[str, Any],
        now: float,
    ) -> None:
        conn.execute(
            text(
                """
                INSERT INTO game_runs
                    (id, user_id, session_id, char_name, realm, death_cause,
                     ascended, turn_count, started_at, finished_at, completed)
                VALUES
                    (:id, :user_id, :session_id, :char_name, :realm, '', FALSE,
                     :turn_count, :started_at, NULL, FALSE)
                ON CONFLICT(id) DO NOTHING
                """
            ),
            {
                "id": session_id,
                "user_id": user_id,
                "session_id": session_id,
                "char_name": str(data.get("char_name") or ""),
                "realm": str(data.get("realm") or ""),
                "turn_count": int(data.get("turn_count") or 0),
                "started_at": now,
            },
        )

    def _insert_turn(
        self,
        conn: Connection,
        run_id: str,
        request_id: str,
        turn: dict[str, Any],
    ) -> None:
        choices_json, delta_json, after_json = encode_game_turn_json(
            list(turn.get("choices") or []),
            dict(turn.get("state_delta") or {}),
            dict(turn.get("state_after") or {}),
        )
        conn.execute(
            text(
                """
                INSERT INTO game_turns
                    (id, run_id, request_id, turn_no, start_age, elapsed_years,
                     end_age, lifespan, remaining_lifespan, choice_taken, choices,
                     state_delta, state_after, calendar_summary, narrative,
                     event_kind, end_reason)
                VALUES
                    (:id, :run_id, :request_id, :turn_no, :start_age,
                     :elapsed_years, :end_age, :lifespan, :remaining_lifespan,
                     :choice_taken, CAST(:choices AS JSONB),
                     CAST(:state_delta AS JSONB), CAST(:state_after AS JSONB),
                     :calendar_summary, :narrative, :event_kind, :end_reason)
                """
            ),
            {
                "id": str(uuid.uuid4()),
                "run_id": run_id,
                "request_id": request_id,
                "turn_no": int(turn["turn_no"]),
                "start_age": int(turn["start_age"]),
                "elapsed_years": int(turn["elapsed_years"]),
                "end_age": int(turn["end_age"]),
                "lifespan": int(turn["lifespan"]),
                "remaining_lifespan": int(turn["remaining_lifespan"]),
                "choice_taken": turn.get("choice_taken"),
                "choices": choices_json,
                "state_delta": delta_json,
                "state_after": after_json,
                "calendar_summary": str(turn.get("calendar_summary") or ""),
                "narrative": str(turn.get("narrative") or ""),
                "event_kind": str(turn.get("event_kind") or "event"),
                "end_reason": turn.get("end_reason"),
            },
        )
        conn.execute(
            text(
                "UPDATE game_runs SET turn_count = :turn_count "
                "WHERE id = :run_id AND completed = FALSE"
            ),
            {"run_id": run_id, "turn_count": int(turn["turn_no"])},
        )

    def _save_slot_conn(
        self,
        conn: Connection,
        user_id: str,
        slot: dict[str, Any],
        now: float,
    ) -> dict[str, Any]:
        slot_name = safe_name(str(slot.get("name") or "slot_1"))
        row = conn.execute(
            text(
                "SELECT id, created_at FROM saves WHERE user_id = :user_id AND name = :name"
            ),
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
                    (:id, :user_id, :name, CAST(:snapshot AS JSONB),
                     CAST(:events AS JSONB), :created_at, :updated_at)
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
                "snapshot": dump_json(slot.get("snapshot") or {}),
                "events": dump_json(list(slot.get("events") or [])[-100:]),
                "created_at": created_at,
                "updated_at": now,
            },
        )
        return {"id": save_id, "user_id": user_id, "name": slot_name, "updated_at": now}

    def _finalize_terminal(
        self,
        conn: Connection,
        session_id: str,
        user_id: str,
        terminal: dict[str, Any],
        now: float,
    ) -> None:
        """Idempotent terminal writes kept inline (not delegated to RewardsRepository).

        They must commit inside the session-mutation transaction and use
        ``ON CONFLICT DO NOTHING`` so a replayed terminal request is a no-op.
        """
        self._ensure_active_run(conn, session_id, user_id, terminal, now)
        finalized = conn.execute(
            text(
                """
                UPDATE game_runs
                SET char_name = :char_name,
                    realm = :realm,
                    death_cause = :death_cause,
                    ascended = :ascended,
                    turn_count = :turn_count,
                    finished_at = :finished_at,
                    completed = TRUE
                WHERE id = :id AND completed = FALSE
                RETURNING id
                """
            ),
            {
                "id": session_id,
                "char_name": str(terminal.get("char_name") or ""),
                "realm": str(terminal.get("realm") or ""),
                "death_cause": str(terminal.get("death_cause") or ""),
                "ascended": bool(terminal.get("ascended")),
                "turn_count": int(terminal.get("turn_count") or 0),
                "finished_at": now,
            },
        ).first()
        if finalized is None:
            return

        summary_value = terminal.get("summary")
        summary: dict[str, Any] = summary_value if isinstance(summary_value, dict) else {}
        death_cause = str(summary.get("death_cause") or terminal.get("death_cause") or "")
        for achievement in summary.get("achievements", []) or []:
            if not isinstance(achievement, dict):
                continue
            conn.execute(
                text(
                    """
                    INSERT INTO run_achievements
                        (id, user_id, session_id, achievement_key, achievement_name,
                         description, death_cause, achieved_at)
                    VALUES
                        (:id, :user_id, :session_id, :achievement_key,
                         :achievement_name, :description, :death_cause, :achieved_at)
                    ON CONFLICT(user_id, session_id, achievement_key) DO NOTHING
                    """
                ),
                {
                    "id": str(uuid.uuid4()),
                    "user_id": user_id,
                    "session_id": session_id,
                    "achievement_key": str(achievement.get("key") or ""),
                    "achievement_name": str(achievement.get("name") or ""),
                    "description": str(achievement.get("description") or ""),
                    "death_cause": death_cause,
                    "achieved_at": now,
                },
            )
        for reward in summary.get("rewards", []) or []:
            if not isinstance(reward, dict):
                continue
            conn.execute(
                text(
                    """
                    INSERT INTO account_rewards
                        (id, user_id, reward_type, reward_value, label,
                         source_session_id, granted_at)
                    VALUES
                        (:id, :user_id, :reward_type, :reward_value, :label,
                         :source_session_id, :granted_at)
                    ON CONFLICT(user_id, source_session_id, reward_type, reward_value)
                    DO NOTHING
                    """
                ),
                {
                    "id": str(uuid.uuid4()),
                    "user_id": user_id,
                    "reward_type": str(reward.get("type") or ""),
                    "reward_value": str(reward.get("value") or ""),
                    "label": str(reward.get("label") or ""),
                    "source_session_id": session_id,
                    "granted_at": now,
                },
            )
        for bonus in terminal.get("legacy_bonuses", []) or []:
            conn.execute(
                text(
                    """
                    INSERT INTO legacy_bonuses
                        (id, user_id, bonus_type, bonus_value, label,
                         runs_remaining, source_session_id, granted_at)
                    VALUES
                        (:id, :user_id, :bonus_type, :bonus_value, :label,
                         :runs_remaining, :source_session_id, :granted_at)
                    ON CONFLICT(user_id, source_session_id, bonus_type, bonus_value)
                    DO NOTHING
                    """
                ),
                {
                    "id": str(uuid.uuid4()),
                    "user_id": user_id,
                    "bonus_type": str(bonus.get("bonus_type") or ""),
                    "bonus_value": str(bonus.get("bonus_value") or ""),
                    "label": str(bonus.get("label") or ""),
                    "runs_remaining": int(bonus.get("runs_remaining") or 1),
                    "source_session_id": session_id,
                    "granted_at": now,
                },
            )
        conn.execute(
            text(
                """
                INSERT INTO player_progress
                    (user_id, runs_completed, ascension_count, updated_at)
                VALUES (:user_id, 1, :ascended, :updated_at)
                ON CONFLICT(user_id) DO UPDATE SET
                    runs_completed = player_progress.runs_completed + 1,
                    ascension_count = player_progress.ascension_count + excluded.ascension_count,
                    updated_at = excluded.updated_at
                """
            ),
            {
                "user_id": user_id,
                "ascended": 1 if terminal.get("ascended") else 0,
                "updated_at": now,
            },
        )
