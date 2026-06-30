# Next Governance Backlog

This is the active backlog for `agens-web`. It separates local code work, local validation, and production/server work so local success is not mistaken for production acceptance.

## Current Evidence

- 2026-06-30 local gameplay slice:
  - The 2026-06-29 roadmap merge is committed in `d405d926` and remains the active plan.
  - Local PostgreSQL at `127.0.0.1:55432` is accepting connections.
  - `tests/unit/engine/test_playable_gap_locks.py` is now a passing gameplay guard: T1-T4 cover formerly xfailed P1 gaps, and T5-T7 lock lifespan death and attribute-pool behavior.
  - The first P1 gameplay slice is implemented locally: character creation uses the six-attribute 30-point pool from `docs/GAME_MODE_SPEC.md` §4.1. Manual mode is 2-8 per stat / total 30; random mode is 0-10 per stat / total 30.
  - Review follow-up fixed random attribute preview persistence: React now submits the shown random pool, backend validates it instead of re-rolling, and switching back to manual resets to a legal manual pool.
  - Visible Chrome 20-turn local player validation completed after the model-settings and playable-gap fixes: login, system-default model config, personal config save/clear, character creation, save/load, 20 non-fallback choice turns, and contiguous `game_turns` all passed.
  - Local Chrome evidence is generated under `output/playwright/` and remains untracked by default.
- User-scoped model settings are implemented locally in commit `44519d7`:
  - `/api/settings/model` is a logged-in user endpoint for personal config.
  - `/api/admin/settings/model` is the admin-only system default endpoint.
  - `user_model_configs` stores one encrypted config per `user_id`; system default remains in `model_config`.
  - Stored model keys use application-layer encryption with `MODEL_CONFIG_SECRET` and fail closed if decryption cannot be performed.
  - Runtime model calls resolve config by current session/user and do not mutate process-global `AGNES_API_KEY`.
  - Empty first-time stored model configs are rejected so an empty user row cannot shadow the effective system Agens default.
- Latest local automated validation after the playable-gap follow-up: `tests\web` 63 passed, full `pytest -q` with `TEST_DATABASE_URL` 432 passed, frontend build passed.
- Main-flow fixes already landed locally: fixed-choice `/choice`, no HTTP 200 without turn progression for ineligible breakthrough choices, contiguous `game_turns` after mismatch/fallback paths.
- Local Chrome 20-turn evidence still found P1 gameplay quality gaps: slow live-model turns, misleading breakthrough options after ineligible breakthrough rejection, player-visible mismatch warnings, state/chronicle age drift, untracked narrative rewards, and unstable option semantics.
- 2026-06-30 production/server batch:
  - Deployed the current package, generated/installed `MODEL_CONFIG_SECRET` without printing it, backed up app/PostgreSQL, rebuilt only `agens-web`, and migrated Alembic to `20260622_0005`.
  - Production `user_model_configs` exists; public/origin health, catalog, container health, and sensitive-marker log scan passed.
  - One-time real-account registration, login, save, load, and cross-session restore passed without printing account, cookie, invite, database URL, or key values.
  - Production live-model acceptance failed: start was non-fallback, but one choice turn returned `fallback_active=true` with `turn_count=0`. Fallback is not live-model success.
- The active phase plan is `docs/PLAYABLE_GAMEPLAY_ROADMAP_20260629.md`: close P0 validation first, then improve gameplay content without broad architecture changes.

## 2026-06-30 Lessons

Successful patterns to keep:

- Split local, production, and code-change work. Local 20-turn Chrome success did not hide the separate production live-model gate.
- Generate deployment packages from tracked files only, scan them before upload, and keep generated Playwright evidence out of commits by default.
- Treat `MODEL_CONFIG_SECRET` as a server-side runtime secret: generate or install it on the server, report only present/missing, and never paste values into chat or docs.
- Require backups before production mutation. The successful production batch created app and PostgreSQL backups before source replacement, image build, migration, and service recreate.
- Check real business semantics, not only transport success. Registration/login/save/load/cross-session restore were verified separately from health/catalog and from live-model non-fallback.
- Use explicit stop gates. The production batch stopped at live-model fallback instead of claiming success from HTTP 200.

Failure lessons and follow-up rules:

- A deployment can be healthy while gameplay acceptance still fails. `fallback_active=true` with `turn_count=0` is a product/runtime failure even when health checks pass.
- Test scripts must be simple and audited. The initial production invite creation probe failed because `docker exec` missed stdin wiring; script errors must not be mistaken for product failures.
- Evidence artifacts must be machine-readable. The local 20-turn browser JSON had escaping/encoding damage, so future evidence writers must output strict JSON or a separate NDJSON/CSV summary.
- UI sanity checks catch issues that API checks miss. The headed browser found duplicate option prefixes such as `A：A：...`.
- Do not let internal arbitration text reach players. Mismatch diagnostics must become logs or natural in-world partial-success/failure text.
- Keep production diagnosis sanitized: collect fallback source/error class/provider status/timeout/repair-path evidence, not request payloads, model keys, cookies, account details, invite codes, or database URLs.

## P0: Acceptance And Deployment Gates

These items block claiming the project is a stable playable public build.

1. Production live model acceptance.
   - Prove start and at least one choice turn are non-fallback.
   - HTTP 200 alone is not enough.
   - Current blocker: the 2026-06-30 production choice smoke returned `fallback_active=true` with `turn_count=0`.
2. Local visible Chrome 20-turn player validation.
   - Done locally on 2026-06-30 for the current slice.
   - Re-run after fixes to option constraints, state/chronicle consistency, or major UI changes.
   - Do not run concurrently with pytest against the same database; Web tests truncate the shared test DB.

## P1: Gameplay Quality And Main-Flow Governance

1. Improve playable content before broad architecture work.
   - Done in current local slice: 30-point six-attribute creation pool.
   - Done in current local slice: silent visible rewards without narration are rejected, invalid local-story input no longer consumes a turn, local-story self-loops vary their result text, and eligible breakthroughs append a settled turn.
   - Diagnose production choice fallback with only sanitized evidence: fallback source/error class, provider status, timeout, and structured-output repair path. Do not print model keys or request payload secrets.
   - Reduce repeated retreat/breakthrough loops.
   - Remove duplicate option prefixes such as `A：A：...` from the player UI.
   - Filter or rewrite breakthrough/realm options from structured state so invalid breakthrough options are not shown after a rejection.
   - Remove player-visible internal mismatch warnings; convert them into natural in-world failure/partial-success text plus debug logs.
   - Keep state bar age, chronicle age, and `game_turns` age from one authoritative source.
   - Add clearer stage goals, meaningful rewards, and visible consequences.
   - Ensure model narrative claims are backed by structured state changes or rejected cleanly.
   - Add visible handling for injuries, key items, techniques, and attribute growth, or prevent the narrative from asserting them.
   - Improve live-model latency; the latest 20-turn local run averaged about 42.9 seconds per choice with a maximum about 106 seconds.
   - Treat the first playable slice and full-run pacing as gameplay acceptance targets per `docs/GAME_MODE_SPEC.md` §3.5.
   - Use an abstract xianxia trope library only. Do not copy real novel characters, sects, plot text, or proprietary settings.
2. Tighten model failure paths.
   - Cover StartFlow, TurnFlow, BreakthroughFlow fallback and `llm_error` paths.
   - API responses should distinguish provider failure, incomplete output, validation rejection, and local fallback.
   - Keep `tests/unit/engine/test_playable_gap_locks.py` passing as the guard for previously identified playable-gap regressions.
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
   - Initial helper is now `scripts/start_local_pg.ps1`.
   - Do not remove `.tmp\pg-test-20260626-55432` while PG is running.
   - Document stale `postmaster.pid` recovery separately.
3. Handle generated evidence deliberately.
   - Treat `output/playwright/`, screenshots, and JSON traces as generated artifacts unless explicitly promoted.
   - Do not delete historical artifacts without inventory, backup, and quarantine.
   - Fix evidence writers so browser traces are strict parseable JSON, or emit a separate NDJSON/CSV summary for automated auditing.

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
