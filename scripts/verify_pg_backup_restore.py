"""Exercise a PostgreSQL dump/restore against disposable local databases."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url

from agens_novel.engine.pending_model_failure import PendingModelFailureV1
from web.backend.local_postgres_safety import require_loopback_postgres_url

EXPECTED_REVISION = "20260721_0009"
EXPECTED_TABLES = 18
ROOT = Path(__file__).resolve().parents[1]


def _restore_snapshots() -> dict[str, dict[str, object]]:
    """Representative persisted saves for every supported story version."""
    pending_failure = PendingModelFailureV1.create(
        stage="turn",
        action="B",
        slot="B",
        frozen_result={"state_delta": {}, "turn_summary": "备份恢复中的冻结回合"},
        rule_rng_counter=95,
        error_code="request_failed",
    ).with_base_version(95)
    base = {
        "turn_count": 1,
        "game_started": True,
        "game_over": False,
        "character": {"name": "restore_hero", "realm": "练气", "age": 18},
    }
    return {
        "v1": {
            **base,
            "world": {"story_key": "border-vein-crisis", "story_version": 1},
        },
        "v2": {
            **base,
            "world": {
                "story_key": "border-vein-crisis",
                "story_version": 2,
                "story_state": {"phase_key": "turning"},
            },
        },
        "v3": {
            **base,
            "turn_count": 95,
            "world": {
                "story_key": "border-vein-crisis",
                "story_version": 3,
                "story_state": {
                    "phase_key": "post_arc",
                    "status": "post_arc",
                    "arc_resolution": "resolved",
                    "post_arc_turns": 5,
                },
            },
            "pending_model_failure": pending_failure.to_dict(),
        },
    }


def main() -> int:
    raw_url = os.environ.get("DATABASE_URL", "").strip()
    if not raw_url:
        raise RuntimeError("DATABASE_URL is required")
    source_url = require_loopback_postgres_url(make_url(raw_url))

    pg_dump = _pg_tool("pg_dump")
    pg_restore = _pg_tool("pg_restore")
    dump_path = Path(tempfile.gettempdir()) / "agens_web_backup_restore.dump"

    try:
        _reset_public_schema(source_url)
        os.environ["DATABASE_URL"] = source_url.render_as_string(hide_password=False)
        command.upgrade(Config(str(ROOT / "alembic.ini")), "head")
        _insert_fixture(source_url)
        _run_pg_dump(pg_dump, source_url, dump_path)
        _reset_public_schema(source_url)
        _run_pg_restore(pg_restore, source_url, dump_path)
        result = _verify_restore(source_url)
        print(json.dumps(result, ensure_ascii=True, sort_keys=True))
        return 0 if result["backup_restore_ok"] else 1
    finally:
        _reset_public_schema(source_url)
        command.upgrade(Config(str(ROOT / "alembic.ini")), "head")
        dump_path.unlink(missing_ok=True)


def _pg_tool(name: str) -> Path:
    executable = shutil.which(name)
    if executable:
        return Path(executable)
    pg_bin = os.environ.get("PG_BIN", "").strip()
    candidates = [Path(pg_bin) / f"{name}.exe"] if pg_bin else []
    candidates.append(Path("F:/pg/bin") / f"{name}.exe")
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise RuntimeError(f"{name} is required; add it to PATH or set PG_BIN")


def _reset_public_schema(database_url: URL) -> None:
    engine = create_engine(database_url)
    try:
        with engine.begin() as conn:
            conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
            conn.execute(text("CREATE SCHEMA public"))
    finally:
        engine.dispose()


def _insert_fixture(database_url: URL) -> None:
    engine = create_engine(database_url)
    snapshots = _restore_snapshots()
    v3_snapshot = json.dumps(snapshots["v3"], ensure_ascii=False)
    pending = snapshots["v3"].get("pending_model_failure")
    if not isinstance(pending, dict):
        raise RuntimeError("backup fixture is missing pending model failure")
    failure_id = str(pending.get("failure_id") or "")
    events = json.dumps(
        [
            {"type": "narrative", "text": "恢复演练"},
            {"type": "model_failure", "failure_id": failure_id},
        ],
        ensure_ascii=False,
    )
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO users "
                    "(id, username, password_hash, is_admin, created_at, updated_at) "
                    "VALUES ('restore-marker', 'restore_marker', 'hash', FALSE, 1, 1)"
                )
            )
            conn.execute(
                text(
                    """
                    INSERT INTO sessions
                        (id, user_id, title, snapshot, events, created_at, updated_at)
                    VALUES
                        ('restore-session', 'restore-marker', 'restore-run',
                         CAST(:snapshot AS JSONB), CAST(:events AS JSONB), 1, 1)
                    """
                ),
                {"snapshot": v3_snapshot, "events": events},
            )
            for version, snapshot in snapshots.items():
                conn.execute(
                    text(
                        """
                        INSERT INTO saves
                            (id, user_id, name, snapshot, events, created_at, updated_at)
                        VALUES
                            (:id, 'restore-marker', :name,
                             CAST(:snapshot AS JSONB), CAST(:events AS JSONB), 1, 1)
                        """
                    ),
                    {
                        "id": f"restore-save-{version}",
                        "name": f"slot_{version}",
                        "snapshot": json.dumps(snapshot, ensure_ascii=False),
                        "events": events,
                    },
                )
            conn.execute(
                text(
                    """
                    INSERT INTO game_runs
                        (id, user_id, session_id, char_name, realm, turn_count,
                         started_at, completed)
                    VALUES
                        ('restore-session', 'restore-marker', 'restore-session',
                         'restore_hero', '练气', 1, 1, FALSE)
                    """
                )
            )
            conn.execute(
                text(
                    """
                    INSERT INTO game_turns
                        (id, run_id, request_id, turn_no, start_age, elapsed_years,
                         end_age, lifespan, remaining_lifespan, choice_taken, choices,
                         state_delta, state_after, calendar_summary, narrative, event_kind)
                    VALUES
                        ('restore-turn', 'restore-session', 'restore-turn-request', 1,
                         16, 2, 18, 100, 82, '稳妥修行', CAST('["A","B","C","D"]' AS JSONB),
                         CAST('{}' AS JSONB), CAST(:snapshot AS JSONB),
                         '玄元历一年第1回合', '恢复演练回合', 'event')
                    """
                ),
                {"snapshot": v3_snapshot},
            )
            conn.execute(
                text(
                    """
                    INSERT INTO session_mutations
                        (session_id, request_id, operation, expected_version,
                         result_version, response, created_at)
                    VALUES
                        ('restore-session', 'restore-turn-request', 'turn', 0, 1,
                        CAST(:response AS JSONB), 1)
                    """
                ),
                {
                    "response": json.dumps(
                        {"turn_count": 95, "version": 1, "pending_model_failure": True}
                    )
                },
            )
            conn.execute(
                text(
                    """
                    INSERT INTO run_achievements
                        (id, user_id, session_id, achievement_key, achievement_name,
                         achieved_at)
                    VALUES
                        ('restore-achievement', 'restore-marker', 'restore-session',
                         'restore_key', '恢复成就', 1)
                    """
                )
            )
            conn.execute(
                text(
                    """
                    INSERT INTO account_rewards
                        (id, user_id, reward_type, reward_value, label,
                         source_session_id, granted_at)
                    VALUES
                        ('restore-reward', 'restore-marker', 'title', 'restore_title',
                         '恢复奖励', 'restore-session', 1)
                    """
                )
            )
            conn.execute(
                text(
                    """
                    INSERT INTO legacy_bonuses
                        (id, user_id, bonus_type, bonus_value, label, runs_remaining,
                         source_session_id, granted_at)
                    VALUES
                        ('restore-bonus', 'restore-marker', 'attribute', 'luck:1',
                         '恢复遗泽', 1, 'restore-session', 1)
                    """
                )
            )
            conn.execute(
                text(
                    """
                    INSERT INTO player_progress
                        (user_id, runs_completed, ascension_count, updated_at)
                    VALUES ('restore-marker', 1, 0, 1)
                    """
                )
            )
    finally:
        engine.dispose()


def _pg_connection_args(database_url: URL) -> tuple[list[str], dict[str, str]]:
    args = [
        f"--host={database_url.host or '127.0.0.1'}",
        f"--port={database_url.port or 5432}",
        f"--username={database_url.username or ''}",
        f"--dbname={database_url.database or ''}",
    ]
    env = dict(os.environ)
    password = database_url.password
    if password:
        env["PGPASSWORD"] = password
    return args, env


def _run_pg_dump(executable: Path, database_url: URL, dump_path: Path) -> None:
    connection_args, env = _pg_connection_args(database_url)
    subprocess.run(
        [str(executable), "--format=custom", f"--file={dump_path}", *connection_args],
        check=True,
        capture_output=True,
        env=env,
    )


def _run_pg_restore(executable: Path, database_url: URL, dump_path: Path) -> None:
    connection_args, env = _pg_connection_args(database_url)
    subprocess.run(
        [
            str(executable),
            "--no-owner",
            "--no-privileges",
            *connection_args,
            str(dump_path),
        ],
        check=True,
        capture_output=True,
        env=env,
    )


def _verify_restore(database_url: URL) -> dict[str, int | str | bool]:
    engine = create_engine(database_url)
    try:
        with engine.connect() as conn:
            revision = str(conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one())
            marker_count = int(
                conn.execute(
                    text("SELECT count(*) FROM users WHERE id = 'restore-marker'")
                ).scalar_one()
            )
            table_count = int(
                conn.execute(
                    text(
                        "SELECT count(*) FROM information_schema.tables "
                        "WHERE table_schema = 'public' AND table_type = 'BASE TABLE' "
                        "AND table_name <> 'alembic_version'"
                    )
                ).scalar_one()
            )
            graph = conn.execute(
                text(
                    """
                    SELECT
                        (SELECT count(*) FROM sessions WHERE id = 'restore-session') AS sessions,
                        (SELECT count(*) FROM saves WHERE user_id = 'restore-marker') AS saves,
                        (SELECT count(*) FROM game_runs WHERE id = 'restore-session') AS runs,
                        (SELECT count(*) FROM game_turns gt
                         JOIN game_runs gr ON gr.id = gt.run_id
                         WHERE gt.id = 'restore-turn' AND gr.session_id = 'restore-session') AS turns,
                        (SELECT count(*) FROM session_mutations
                         WHERE session_id = 'restore-session'
                           AND request_id = 'restore-turn-request') AS mutations,
                        (SELECT count(*) FROM run_achievements
                         WHERE id = 'restore-achievement') AS achievements,
                        (SELECT count(*) FROM account_rewards
                         WHERE id = 'restore-reward') AS rewards,
                        (SELECT count(*) FROM legacy_bonuses
                         WHERE id = 'restore-bonus') AS bonuses,
                        (SELECT count(*) FROM player_progress
                         WHERE user_id = 'restore-marker' AND runs_completed = 1) AS progress,
                        (SELECT count(*) FROM game_turns gt
                         LEFT JOIN game_runs gr ON gr.id = gt.run_id
                         WHERE gr.id IS NULL) AS orphan_turns,
                        (SELECT count(*) FROM saves
                         WHERE snapshot #>> '{world,story_version}' IN ('1', '2', '3')) AS save_versions,
                        (SELECT count(*) FROM saves
                         WHERE name = 'slot_v3'
                           AND snapshot #>> '{world,story_state,status}' = 'post_arc'
                           AND snapshot ? 'pending_model_failure') AS post_arc_pending
                    """
                )
            ).mappings().one()
    finally:
        engine.dispose()
    return {
        "backup_restore_ok": (
            revision == EXPECTED_REVISION
            and table_count == EXPECTED_TABLES
            and marker_count == 1
            and all(int(graph[key]) == 1 for key in (
                "sessions", "runs", "turns", "mutations",
                "achievements", "rewards", "bonuses", "progress",
            ))
            and int(graph["saves"]) == 3
            and int(graph["save_versions"]) == 3
            and int(graph["post_arc_pending"]) == 1
            and int(graph["orphan_turns"]) == 0
        ),
        "restored_revision": revision,
        "restored_tables": table_count,
        "restored_marker_count": marker_count,
        "restored_business_graph_ok": all(int(graph[key]) == 1 for key in (
            "sessions", "runs", "turns", "mutations",
            "achievements", "rewards", "bonuses", "progress",
        )) and int(graph["saves"]) == 3,
        "restored_save_versions": int(graph["save_versions"]),
        "restored_post_arc_pending": int(graph["post_arc_pending"]),
        "restored_orphan_turns": int(graph["orphan_turns"]),
    }


if __name__ == "__main__":
    raise SystemExit(main())
