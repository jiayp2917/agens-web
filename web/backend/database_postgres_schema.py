"""PostgreSQL schema used by the test-only auto-DDL path."""

from importlib import import_module

POSTGRES_SCHEMA_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        username TEXT NOT NULL UNIQUE,
        password_hash TEXT,
        is_admin BOOLEAN NOT NULL DEFAULT FALSE,
        created_at DOUBLE PRECISION NOT NULL,
        updated_at DOUBLE PRECISION NOT NULL
    )
    """,
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
    """,
    """
    CREATE TABLE IF NOT EXISTS sessions (
        id TEXT PRIMARY KEY,
        user_id TEXT REFERENCES users(id),
        guest_token_hash TEXT,
        expires_at DOUBLE PRECISION,
        version INTEGER NOT NULL DEFAULT 0,
        title TEXT NOT NULL,
        snapshot JSONB NOT NULL,
        events JSONB NOT NULL,
        created_at DOUBLE PRECISION NOT NULL,
        updated_at DOUBLE PRECISION NOT NULL,
        CHECK ((user_id IS NOT NULL) <> (guest_token_hash IS NOT NULL))
    )
    """,
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
    """,
    """
    CREATE TABLE IF NOT EXISTS model_config (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        provider TEXT NOT NULL,
        base_url TEXT NOT NULL,
        model TEXT NOT NULL,
        api_key_masked TEXT NOT NULL,
        api_key_set BOOLEAN NOT NULL,
        api_key_encrypted TEXT NOT NULL DEFAULT '',
        updated_at DOUBLE PRECISION NOT NULL
    )
    """,
    """
    ALTER TABLE model_config
    ADD COLUMN IF NOT EXISTS api_key_encrypted TEXT NOT NULL DEFAULT ''
    """,
    """
    CREATE TABLE IF NOT EXISTS user_model_configs (
        user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
        provider TEXT NOT NULL,
        base_url TEXT NOT NULL,
        model TEXT NOT NULL,
        api_key_masked TEXT NOT NULL,
        api_key_set BOOLEAN NOT NULL,
        api_key_encrypted TEXT NOT NULL DEFAULT '',
        updated_at DOUBLE PRECISION NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS catalog_talents (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL UNIQUE,
        rarity TEXT NOT NULL DEFAULT '普通',
        description TEXT NOT NULL DEFAULT '',
        attribute_mods JSONB NOT NULL DEFAULT '{}',
        tags JSONB NOT NULL DEFAULT '[]',
        created_at DOUBLE PRECISION NOT NULL DEFAULT EXTRACT(EPOCH FROM now())
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS catalog_family_backgrounds (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL UNIQUE,
        rarity TEXT NOT NULL DEFAULT '普通',
        description TEXT NOT NULL DEFAULT '',
        initial_resources JSONB NOT NULL DEFAULT '{}',
        initial_risks JSONB NOT NULL DEFAULT '[]',
        story_tags JSONB NOT NULL DEFAULT '[]',
        created_at DOUBLE PRECISION NOT NULL DEFAULT EXTRACT(EPOCH FROM now())
    )
    """,
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
        created_at DOUBLE PRECISION NOT NULL DEFAULT EXTRACT(EPOCH FROM now())
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS catalog_difficulties (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL UNIQUE,
        risk_multiplier DOUBLE PRECISION NOT NULL DEFAULT 1.0,
        reward_multiplier DOUBLE PRECISION NOT NULL DEFAULT 1.0,
        lifespan_modifier DOUBLE PRECISION NOT NULL DEFAULT 1.0,
        luck_modifier DOUBLE PRECISION NOT NULL DEFAULT 0,
        description TEXT NOT NULL DEFAULT '',
        created_at DOUBLE PRECISION NOT NULL DEFAULT EXTRACT(EPOCH FROM now())
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS catalog_story_seeds (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        category TEXT NOT NULL DEFAULT '',
        description TEXT NOT NULL DEFAULT '',
        tags JSONB NOT NULL DEFAULT '[]',
        created_at DOUBLE PRECISION NOT NULL DEFAULT EXTRACT(EPOCH FROM now())
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS run_achievements (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL REFERENCES users(id),
        session_id TEXT NOT NULL,
        achievement_key TEXT NOT NULL,
        achievement_name TEXT NOT NULL,
        description TEXT NOT NULL DEFAULT '',
        death_cause TEXT NOT NULL DEFAULT '',
        achieved_at DOUBLE PRECISION NOT NULL,
        UNIQUE(user_id, session_id, achievement_key)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS account_rewards (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL REFERENCES users(id),
        reward_type TEXT NOT NULL,
        reward_value TEXT NOT NULL,
        label TEXT NOT NULL DEFAULT '',
        source_session_id TEXT NOT NULL DEFAULT '',
        granted_at DOUBLE PRECISION NOT NULL,
        UNIQUE(user_id, source_session_id, reward_type, reward_value)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS legacy_bonuses (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL REFERENCES users(id),
        bonus_type TEXT NOT NULL,
        bonus_value TEXT NOT NULL,
        label TEXT NOT NULL DEFAULT '',
        runs_remaining INTEGER NOT NULL DEFAULT 1,
        source_session_id TEXT NOT NULL DEFAULT '',
        granted_at DOUBLE PRECISION NOT NULL,
        UNIQUE(user_id, source_session_id, bonus_type, bonus_value)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS game_runs (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL REFERENCES users(id),
        session_id TEXT NOT NULL DEFAULT '',
        char_name TEXT NOT NULL DEFAULT '',
        realm TEXT NOT NULL DEFAULT '',
        death_cause TEXT NOT NULL DEFAULT '',
        ascended BOOLEAN NOT NULL DEFAULT FALSE,
        turn_count INTEGER NOT NULL DEFAULT 0,
        started_at DOUBLE PRECISION,
        finished_at DOUBLE PRECISION,
        completed BOOLEAN NOT NULL DEFAULT FALSE
    )
    """,
    """
    CREATE UNIQUE INDEX IF NOT EXISTS uq_game_runs_session
    ON game_runs(session_id) WHERE session_id <> ''
    """,
    """
    CREATE TABLE IF NOT EXISTS game_turns (
        id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL,
        request_id TEXT,
        turn_no INTEGER NOT NULL,
        start_age INTEGER NOT NULL,
        elapsed_years INTEGER NOT NULL,
        end_age INTEGER NOT NULL,
        lifespan INTEGER NOT NULL,
        remaining_lifespan INTEGER NOT NULL,
        choice_taken TEXT,
        choices JSONB NOT NULL,
        state_delta JSONB NOT NULL,
        state_after JSONB NOT NULL,
        calendar_summary TEXT NOT NULL,
        narrative TEXT NOT NULL,
        event_kind TEXT NOT NULL,
        end_reason TEXT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        UNIQUE(run_id, turn_no),
        UNIQUE(run_id, request_id),
        FOREIGN KEY(run_id) REFERENCES game_runs(id) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS session_mutations (
        session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
        request_id TEXT NOT NULL,
        operation TEXT NOT NULL,
        expected_version INTEGER NOT NULL,
        result_version INTEGER NOT NULL,
        response JSONB NOT NULL,
        created_at DOUBLE PRECISION NOT NULL,
        PRIMARY KEY(session_id, request_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS player_progress (
        user_id TEXT PRIMARY KEY REFERENCES users(id),
        runs_completed INTEGER NOT NULL DEFAULT 0,
        ascension_count INTEGER NOT NULL DEFAULT 0,
        updated_at DOUBLE PRECISION NOT NULL
    )
    """,
)

def schema_comment_statements() -> tuple[str, ...]:
    return import_module(
        "migrations.versions.20260705_0007_schema_comments"
    ).comment_sql_statements()
