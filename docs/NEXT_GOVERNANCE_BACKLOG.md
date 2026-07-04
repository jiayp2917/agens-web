# Next Governance Backlog

This is the active backlog for `agens-web`. It separates local code work, local validation, and production/server work so local success is not mistaken for production acceptance.

## Current Evidence

- Current local code baseline includes sanitized model diagnostics and the 2026-07-04 attribute-scale cleanup.
- Validation after the latest P1 observability slice passed:
  - `python -m compileall -q src tests web scripts migrations`
  - `python -m pytest -q tests\web` -> 68 passed
  - `python -m pytest -q` with local PostgreSQL `TEST_DATABASE_URL` -> 480 passed
  - `cd web\frontend-react; npm.cmd run build` -> passed
  - `git diff --check` -> passed
- User-scoped model settings are implemented:
  - `/api/settings/model` is a logged-in user endpoint for personal config.
  - `/api/admin/settings/model` is the admin-only system-default endpoint.
  - `user_model_configs` stores one encrypted config per `user_id`; system default remains in `model_config`.
  - Runtime model calls resolve config by current session/user and do not mutate process-global `AGNES_API_KEY`.
- Local visible Chrome P0 browser acceptance passed in `local-visible-20turn-20260701-final2`: account registration/login, system-default start, character creation, 20/20 choice turns non-fallback, and save/load passed. Evidence remains generated under `output/playwright/` and is ignored by default.
- Production P0 is accepted for the latest deployed production batch: server thread deployed `25ad3d15`, kept Alembic at `20260622_0005`, verified `user_model_configs`, health/catalog/container state, sanitized log scan, real-account flow, and production start+choice non-fallback with `turn_count=1`.
- Latest local code adds sanitized `model_result` diagnostics with numeric/boolean fields only: narrator/judge elapsed time, repair elapsed time, prompt size, history count, game-state size, and provider token counters when available. This is measurement, not a latency fix.
- Current local working batch addresses four P1 complaints before the next Chrome pass: actionable secret-safe model-unavailable prompts for upstream 404/auth/timeout/key issues, Qi Refining small-stage pacing guards, stricter third-person chronicle narrator guidance, and a read-only sidebar "外界情报" projection.
- Current local working batch also closes the attribute-scale audit: runtime attributes are 0-10 with 5 as neutral, and old 0-100 values are compatibility inputs only. New realm, reward, catalog, or model-prompt logic must not use 50 as the neutral midpoint or 100 as the normal cap.
- Active phase plan remains `docs/PLAYABLE_GAMEPLAY_ROADMAP_20260629.md`: P0 current batch is closed; next work is P1 gameplay quality and model-efficiency iteration without broad architecture changes.

## Lessons To Keep

- Do not count HTTP 200 as live-model success. Acceptance requires `fallback=false` and turn progression.
- Keep local, production, and code-change validation separate. Local Chrome success does not replace production non-fallback proof.
- Keep generated Playwright evidence out of normal commits unless explicitly promoted.
- Production reports must be sanitized: booleans, counts, revisions, table names, HTTP status, and error classes only. Do not output keys, cookies, real accounts, invite codes, database URLs, raw prompts, raw responses, or secrets.
- A healthy deploy can still fail gameplay acceptance; live-model fallback remains a product/runtime failure.
- Browser evidence must be strict JSON/NDJSON/CSV so future audits can parse it.
- Chrome playtests must not run concurrently with `tests\web` against the same database because Web tests truncate the shared test DB.

## P0: Acceptance And Deployment Gates

P0 is currently closed for the latest local and production batches. Re-run only when a gate is touched.

1. Production live-model gate.
   - Re-run after every production deployment, model-config change, provider change, or migration affecting runtime model calls.
   - Required proof: production start and at least one choice are non-fallback, and choice advances `turn_count`.
   - Server thread owns this gate.
2. Local visible Chrome 20-turn gate.
   - Re-run after gameplay pacing, state/chronicle consistency, option constraints, model-efficiency, or major UI-flow changes.
   - Required proof: 20/20 choices non-fallback, save/load works, `game_turns` stays continuous, and evidence is strict JSON/NDJSON/CSV.
   - Do not run concurrently with pytest against the same database.

## P1: Gameplay Quality And Model Efficiency

Next work should be data-led and gameplay-facing.

1. Run a real visible Chrome 20-turn sampling pass with the new diagnostics.
   - Capture average/max choice latency, narrator elapsed time, judge elapsed time, repair attempt count, repaired output count, prompt chars, game-state chars, history count, token usage, fallback count, and `game_turns` continuity.
   - Do not treat observability itself as performance improvement.
2. Choose the next latency fix from evidence.
   - If prompt/history grows: compress `chat_history` into summary + recent turns.
   - If repair dominates: tighten narrator output contract/parser without accepting incomplete narrative.
   - If judge dominates: narrow judge trigger conditions to authoritative/risky state changes.
   - If provider dominates: document model performance differences and rely on user-configurable providers.
3. Improve 20-turn playable content.
   - Add the 0-16 岁 opening chronicle per `docs/GAME_MODE_SPEC.md` §3.5.
   - Add 3-5 turn stage feedback.
   - Build event pools for steady, opportunity, risk, and luck routes.
   - Reduce repeated retreat/breakthrough loops.
   - Keep small-realm progress mostly implicit; reserve major breakthroughs for stage events.
   - Keep Qi Refining pacing credible: age and turn count should prevent a 20-turn slice from lingering in early small layers.
   - Keep the sidebar "外界情报" read-only and fed by existing world summaries; do not turn it into a new resource system until the gameplay design explicitly calls for one.
4. Tighten authoritative state accounting.
   - Key items, techniques, attribute growth, titles, relationships, injuries, lifespan, realm changes, and karma must be structured state or rewritten/suppressed.
   - Ordinary chronicle rumors, intentions, or non-authoritative color text do not automatically become inventory.
   - Model text can polish narrative and choices, but cannot decide authoritative numbers.

## P1: Complexity Governance

Only do complexity work that supports the main flow.

- `tests/web/test_web_api.py`: split by account/model settings/session/save-load/turn persistence when touched.
- `web/backend/service.py`: extract session progression, model config resolution, persistence, and error mapping helpers without changing API behavior.
- `web/backend/database_postgres.py`: extract row shaping and repeated SQL helpers without schema changes.
- `src/agens_novel/engine/game_engine.py`: make small slices around fallback, breakthrough, local story, and model failure.
- Avoid broad router rewrites or architecture restructuring unless a blocking bug proves it necessary.

## P2: Documentation And Cleanup

- Keep `docs/INDEX.md`, `docs/PLAYABLE_GAMEPLAY_ROADMAP_20260629.md`, `docs/GAME_MODE_SPEC.md`, `docs/RUNTIME_FLOW.md`, and this file aligned.
- Historical planning drafts and UI prototypes have been removed from `docs/archive/`; current state belongs in current docs, and history belongs in `CHANGELOG.md` or concise lessons sections.
- Keep `scripts/start_local_pg.ps1` as the PG startup/recovery helper. Do not delete `.tmp\pg-test-20260626-55432` while PG is running.
- `output/playwright/` remains ignored generated evidence. Do not stage it in ordinary code/docs commits.

## Validation Rules

- Backend/service changes:
  - targeted tests first
  - `python -m compileall -q src tests web scripts migrations`
  - `python -m pytest -q tests\web`
  - full `python -m pytest -q` when touching shared gameplay/service code
- Frontend/UI changes:
  - `npm.cmd run build`
  - visible Chrome smoke for changed viewport/workflow
- Production:
  - follow `docs/PRODUCTION_V5_MIGRATION_CHECKLIST.md`
  - never read or print secrets
  - never use `AGENS_PG_AUTO_DDL=1` in production
  - never count fallback as live-model success
