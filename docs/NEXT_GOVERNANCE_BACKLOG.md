# Next Governance Backlog

This is the active backlog for `agens-web`. It separates local code work, local validation, and production/server work so local success is not mistaken for production acceptance.

## Current Evidence

- 2026-06-30 local gameplay slice:
  - The 2026-06-29 roadmap merge is committed in `d405d926` and remains the active plan.
  - Local PostgreSQL at `127.0.0.1:55432` is accepting connections.
  - `tests/unit/engine/test_playable_gap_locks.py` has been reviewed and accepted as a strict xfail gap guard: T1-T4 are known P1 gaps, T5-T7 are passing lock tests.
  - The first P1 gameplay slice is implemented locally: character creation uses the six-attribute 30-point pool from `docs/GAME_MODE_SPEC.md` §4.1. Manual mode is 2-8 per stat / total 30; random mode is 0-10 per stat / total 30.
  - A Chrome observation where users/sessions/game_turns dropped to zero is not yet a deterministic product bug. `tests\web` truncates the shared `TEST_DATABASE_URL` database before each test, so visible Chrome must be re-run without concurrent pytest and preferably against an isolated database.
- User-scoped model settings are implemented locally in commit `44519d7`:
  - `/api/settings/model` is a logged-in user endpoint for personal config.
  - `/api/admin/settings/model` is the admin-only system default endpoint.
  - `user_model_configs` stores one encrypted config per `user_id`; system default remains in `model_config`.
  - Stored model keys use application-layer encryption with `MODEL_CONFIG_SECRET` and fail closed if decryption cannot be performed.
  - Runtime model calls resolve config by current session/user and do not mutate process-global `AGNES_API_KEY`.
- Latest local automated validation after the 30-point pool and model-settings input fix: `tests\web` 62 passed, full `pytest -q` with `TEST_DATABASE_URL` 427 passed / 4 xfailed, frontend build passed.
- Main-flow fixes already landed locally: fixed-choice `/choice`, no HTTP 200 without turn progression for ineligible breakthrough choices, contiguous `game_turns` after mismatch/fallback paths.
- Production/server acceptance is still separate. Fallback is not live-model success.
- The active phase plan is `docs/PLAYABLE_GAMEPLAY_ROADMAP_20260629.md`: close P0 validation first, then improve gameplay content without broad architecture changes.

## P0: Acceptance And Deployment Gates

These items block claiming the project is a stable playable public build.

1. Production deploy for user-scoped model settings.
   - Requires server-thread approval and execution.
   - Must include app backup, PostgreSQL backup/restore point, `MODEL_CONFIG_SECRET` presence check without printing value, Alembic upgrade to `20260622_0005`, restart, and health checks.
2. Production account flow.
   - Verify registration, login, save, load, and cross-session restore with a safe non-secret test account path.
   - Do not print passwords, cookies, invite codes, keys, or database URLs.
3. Production live model acceptance.
   - Prove start and at least one choice turn are non-fallback.
   - HTTP 200 alone is not enough.
4. Local visible Chrome 20-turn player validation.
   - Do not run concurrently with pytest against the same database; Web tests truncate the shared test DB.
   - Use local PostgreSQL, ordinary account login, model setting fallback/user/clear flow, role creation, at least 20 turns, save/load, and `game_turns` continuity checks.
   - Re-check the previously observed account session invalidation only under an isolated DB/no-pytest run before classifying it as P0 product bug.
   - Record response time, fallback state, narrative/state mismatch, repeated loops, and screenshots/log paths.

## P1: Gameplay Quality And Main-Flow Governance

1. Improve playable content before broad architecture work.
   - Done in current local slice: 30-point six-attribute creation pool.
   - Reduce repeated retreat/breakthrough loops.
   - Add clearer stage goals, meaningful rewards, and visible consequences.
   - Ensure model narrative claims are backed by structured state changes or rejected cleanly.
   - Treat the first playable slice and full-run pacing as gameplay acceptance targets per `docs/GAME_MODE_SPEC.md` §3.5.
   - Use an abstract xianxia trope library only. Do not copy real novel characters, sects, plot text, or proprietary settings.
2. Tighten model failure paths.
   - Cover StartFlow, TurnFlow, BreakthroughFlow fallback and `llm_error` paths.
   - API responses should distinguish provider failure, incomplete output, validation rejection, and local fallback.
   - Keep `tests/unit/engine/test_playable_gap_locks.py` as the guard for known P1 gaps; convert xfail entries to passing tests only when the corresponding gameplay fix lands.
3. Continue small complexity slices only when they support main-flow stability.
   - `GameEngine`: split model failure, local story, breakthrough helpers one responsibility at a time.
   - `WebGameService`: keep reducing duplicate runner/error/persistence orchestration.
   - `database_postgres.py`: extract row shaping and helper functions without schema changes.
   - `app.py`: router split is optional and lower priority than gameplay correctness.
4. Frontend maintenance.
   - Continue splitting `CharacterCreatePage` and style files around verified workflows.
   - Use Chrome smoke after visual changes.
5. Gameplay system iteration.
   - Done: move character creation to a six-attribute point pool per `docs/GAME_MODE_SPEC.md` §4.1.
   - Add an opening chronicle before the first player choice per `docs/GAME_MODE_SPEC.md` §3.5.
   - Build event pools by steady, opportunity, risk, and luck routes.
   - Keep small-realm progress mostly implicit; reserve major-realm breakthroughs for stage events.

## P2: Documentation And Cleanup

1. Keep current docs short and authoritative.
   - `docs/INDEX.md` routes current reading.
   - `docs/PLAYABLE_GAMEPLAY_ROADMAP_20260629.md` contains the current phase plan.
   - `docs/PROJECT_AUDIT.md` contains current structure and risk only.
   - This file contains active backlog only.
   - `CHANGELOG.md` and `docs/archive/` retain history.
2. Formalize local PostgreSQL startup/recovery.
   - Check `pg_isready` before starting.
   - Do not remove `.tmp\pg-test-20260626-55432` while PG is running.
   - Document stale `postmaster.pid` recovery separately.
3. Handle generated evidence deliberately.
   - Treat `output/playwright/`, screenshots, and JSON traces as generated artifacts unless explicitly promoted.
   - Do not delete historical artifacts without inventory, backup, and quarantine.

## Validation Rules

- Backend/service changes:
  - targeted tests first
  - `python -m compileall -q src tests web scripts migrations`
  - `python -m pytest -q tests\web`
  - full `python -m pytest -q` when touching shared gameplay/service code
- Frontend/UI changes:
  - `npm.cmd run build`
  - relevant frontend contract tests
  - visible Chrome smoke for changed viewport/workflow
- Production:
  - follow `docs/PRODUCTION_V5_MIGRATION_CHECKLIST.md`
  - never read or print secrets
  - never use `AGENS_PG_AUTO_DDL=1` in production
  - never count fallback as live-model success
