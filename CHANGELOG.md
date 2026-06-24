# Changelog

## 2026-06-24

### Added

- Homepage QQ card now uses the user-provided `xian-game-icon-256.png` asset under `web/frontend-react/public/assets`.
- `WebRunner.record()` includes the current character age in readable events so the chronicle timeline can infer display years from gameplay state.
- Frontend contract checks for the image-based QQ icon, the fate summary-card structure, and chronicle year-prefix cleanup.
- Project-status notes in `docs/PROJECT_AUDIT.md`, `docs/UI_REFACTOR_PLAN.md`, and `docs/INDEX.md` for the current UI batch, validation results, and browser-validation boundary.
- `docs/NEXT_GOVERNANCE_BACKLOG.md` as the active backlog separating production-approved work, local complexity reduction, cleanup, and validation rules.
- Production v5 local package manifest for commit `11ae5e9699277ce08b42a9331932354895922149`, archive `D:\chat\outputs\packages\agens-web\agens-web-11ae5e9-20260624-173644.zip`, and SHA256 `526b8b6cbbc1abd60b1a03b1d73369778abf8c723d439579526532d9744017ad`.

### Changed

- Character creation fate groups use the approved plan A summary-card collapse design: selected item pill, color dot, chevron, one open group at a time, and internally scrolling option lists.
- Game chronicle rendering treats the card title year as authoritative and strips leading `玄历/玄元历...年` prefixes from narrative text.
- Narrator prompt now tells the model not to start each event body with a chronicle year prefix.
- Browser validation guidance now prefers Chrome DevTools MCP or external Chrome because the Codex in-app browser is unstable on this machine.
- FastAPI session endpoints now share one service-error wrapper for `KeyError` / `PermissionError` / `ValueError`, preserving the existing 404 / 403 / 400 response behavior while removing repeated route boilerplate.
- SQLite and PostgreSQL catalog seeding, catalog-row JSON preparation, and player-progress summaries now share helpers in `web/backend/database_common.py`, reducing duplicate data-layer logic without changing schema or API behavior.
- Game chronicle year/text shaping moved from `GamePage.tsx` into pure helpers in `web/frontend-react/src/lib/chronicle.ts`, keeping the page focused on rendering and interaction wiring.
- Chronicle year display now uses the strongest positive year candidate from event year, turn index, inferred turn, and age-year. This prevents local fallback events with unchanged character age from leaving turn 1 displayed as `玄元历 1 年`.
- Randomized character attributes now render as read-only meters instead of disabled manual sliders, so values above the manual cap remain visible and accessible without mismatched slider semantics.
- `WebGameService.choose()` and `WebGameService.act()` now share the same private turn-advance helper, keeping turn execution, settled-turn persistence, session persistence, and response shaping in one path.
- Alpha review and game-mode spec now align the production gate with Alembic head `20260622_0004` and the completed local Chrome/account/live-model validation coverage.
- `docs/INDEX.md` now routes structure cleanup and technical-debt work through the active governance backlog before deeper audit docs.
- Docker image hardening now strips CRLF from the copied `agens-web` entrypoint, and `.gitattributes` forces shell scripts and the Dockerfile to LF line endings.
- `GameEngine.attempt_breakthrough()` now delegates the breakthrough-narrator
  invocation to `_run_breakthrough_narrator()`. That helper only owns the raw
  exception branch (try/except + `_set_choices` fallback with
  `source="breakthrough_narrator_exception"`); the post-call `llm_error` branch
  with `source="breakthrough_narrator_error"` is still inlined in
  `attempt_breakthrough()`.
- `WebGameService` keeps `_require_non_guest_runner(action=...)`, which
  consolidates the `is_guest_user_id → PermissionError("访客…")` guard used by
  `save` and `load`. The intermediate `_with_runner()` alias was reverted in
  the same pass because it had no extra semantics over `_runner()`.
- `web/backend/database_common.py` adds `encode_game_turn_json()` to keep the
  `choices` / `state_delta` / `state_after` JSON encoding in lockstep between
  the SQLite and PostgreSQL `record_game_turn` writers; SQL, schema and
  column names are unchanged.
- `CharacterCreatePage` collapses the three repeated `<CatalogGroup>` blocks
  into a small `fateGroups` data-driven loop. `character-create.css` merges
  the duplicate `.character-page` rule.

### Verification

- `python -m compileall -q src tests web scripts migrations` clean.
- `pytest -q tests\web` -> 49 passed, 1 skipped (`TEST_DATABASE_URL` not configured).
- `pytest -q` -> 425 passed, 1 skipped.
- `pytest -q tests/unit/engine/test_game_engine_turn.py tests/unit/engine/test_game_engine_setup.py tests/unit/engine/test_game_engine_state.py tests/unit/game/test_database_common.py` -> 56 passed.
- `npm run build` passed; frontend contract test `tests\web\test_frontend_contract.py` passed 16 tests.
- `pytest -q tests\web\test_web_api.py::test_web_api_minimum_game_flow tests\web\test_web_api.py::test_session_routes_map_service_errors` -> 9 passed; the minimum flow now covers both `/choice` and `/action` turn persistence.
- Documentation consistency check: `rg` now routes production acceptance to Alembic head `20260622_0004`, while local Chrome/account/live-model coverage is separated from still-open production account/model smoke.
- Chrome desktop and 375px mobile smoke passed for guest start, fallback continuation, A/B/C/D visibility, and `玄元历 2 年 · 回合 1` after the first local fallback turn.
- Chrome 375px random-character smoke confirmed all six randomized attributes expose meters whose `aria-valuenow` matches the visible value.
- Chrome desktop local account smoke passed with a temporary SQLite database and local-only invite: register/login, account new game, save to `slot_1`, load from `slot_1`, and `/api/saves` returning the saved row all completed with HTTP 200.
- Chrome 2560x1440 emulation smoke passed for home, character creation, and initial game view. No horizontal overflow was detected; the creation panels, start button, game grid, status rail, story panel, and A/B/C/D buttons stayed within the viewport.
- Chrome local live-model smoke passed with a temporary SQLite database and non-secret environment-presence check only: guest start plus choice A returned `/api/sessions/{id}/choice` HTTP 200, `fallback_prompt.active=false`, turn count 1, refreshed narrative, and refreshed A/B/C/D choices.
- Server read-only validation confirmed public health/catalog and container health, but production Alembic is still `20260621_0002` and v5 tables `game_runs`, `game_turns`, `player_progress` are missing.
- Production package content check found no `.env`, `production.env`, `node_modules/`, `.venv/`, cache directories, or local frontend `dist` in the archive; the package was created from tracked `HEAD` files with `git archive`.
- Server deployment preflight thread `019ee2ee-823e-7441-bdaa-881782da7949` confirmed package hash visibility, public health/catalog, internal origin health, healthy `agens-web` container, and staging/backup path candidates; it did not deploy, back up, migrate, restart, or read/print secrets.
- Approved production v5 deployment attempt stopped before Alembic/restart: server package upload and SHA256 verification passed, PostgreSQL backup `/srv/jiayp/backups/postgres/postgres-20260624-180554.sql.gz` and app backup `/srv/jiayp/backups/agens-web/agens-web-app-20260624-180650.tar.gz` were created, `/srv/jiayp/apps/agens-web` was replaced, then Docker build failed resolving `langchain-core>=0.3.0`. Existing running container stayed healthy, public health/catalog stayed OK, and production Alembic remained `20260621_0002`.
- Read-only server diagnosis found `requirements.txt` still contains `langchain-core>=0.3.0`, Docker runtime is `python:3.12-slim`, and a temporary `python:3.12-slim` container can see `langchain-core` versions including `0.3.0`; the build stop is most likely a transient or build-context-specific pip index/network issue.
- Prepared the build-only retry prompt `D:\chat\outputs\packages\agens-web\agens-web-11ae5e9-20260624-173644.server-build-only-prompt.md`, scoped to image build only and explicitly excluding Alembic, restart/recreate, rollback, and public exposure changes until separate approval.
- Build-only retry passed using host-network fallback and produced image `sha256:f2d2b86e3de0c9aff5131ed238c84eb435cb0d31983e5e4629b8b75add4d6c15`; no Alembic, restart/recreate, rollback, or public exposure change was performed in that retry.
- Approved migration/restart batch upgraded production Alembic to `20260622_0004` and confirmed `game_runs`, `game_turns`, and `player_progress`, then stopped after the recreated `agens-web` container failed with exit 127 due CRLF in the image entrypoint (`env: 'sh\r': No such file or directory`). Public health was HTTP 502 at that stop point; the later approved entrypoint hotfix restored service.
- Prepared the entrypoint CRLF hotfix prompt `D:\chat\outputs\packages\agens-web\agens-web-11ae5e9-20260624-173644.entrypoint-crlf-hotfix-prompt.md`, scoped to LF normalization, build-only, only `agens-web` recreation, and post-deploy verification.
- Prepared entrypoint CRLF hotfix package `D:\chat\outputs\packages\agens-web\agens-web-entrypoint-crlf-hotfix-20260624-185815.zip` with SHA256 `261ecef7fbeac0928b076802e4cd458607c651ae15153f9ea700a01afd8ce1f4`; contents are limited to `.gitattributes`, `Dockerfile`, and `deploy/docker-entrypoint.sh`, and the packaged entrypoint is LF-only.
- Server read-only hotfix preflight confirmed production is still in the same failed state: container `Restarting (127)`, public health HTTP 502, origin connect failed, Alembic `20260622_0004`, v5 tables present, deployed entrypoint `crlf_count=10`, deployed Dockerfile hardening missing, backups present, and the prepared hotfix package visible with matching SHA256.
- Approved entrypoint CRLF hotfix passed: server changed only `.gitattributes`, `Dockerfile`, and `deploy/docker-entrypoint.sh`, backed those files up at `/srv/jiayp/backups/agens-web/entrypoint-crlf-hotfix-20260624-185815/`, built image `sha256:445367f496bf3b1acb8b091442f775b9c74240251cc19efdfab2d45562dbc791`, recreated only `agens-web`, and restored healthy origin/public health.
- Production smoke after the hotfix confirmed Alembic `20260622_0004`, `game_runs` / `game_turns` / `player_progress`, public catalog talents count 10, log sensitive-marker count 0, guest start HTTP 200, and guest one-turn HTTP 200 with four options.
- Production v5 is only partially accepted: account registration/login/save/load still needs a safe non-secret test account path, and live-model success was not accepted because the production guest smoke returned `fallback_prompt_active=true`.

## 2026-06-24 Local complexity governance (P1)

- This sub-section records a local-only governance pass. It does **not**
  accept any production action; production acceptance still requires the
  Codex / server thread batch described in
  `docs/PRODUCTION_V5_MIGRATION_CHECKLIST.md`.

### Added

- `GameEngine._run_breakthrough_narrator()` private helper that owns the
  breakthrough-narrator `run_turn_sync` call and its raw exception fallback
  (`source="breakthrough_narrator_exception"` + `_set_choices`). The post-call
  `llm_error` branch (`source="breakthrough_narrator_error"`) is still inlined
  inside `attempt_breakthrough()` and is the next P1 candidate.
- `WebGameService._require_non_guest_runner(action=...)` private helper that
  consolidates the `is_guest_user_id → PermissionError("访客…")` guard used
  by `save` and `load`. The original `_with_runner()` thin alias was removed
  in the same pass because it added no semantics over `_runner()`.
- `web/backend/database_common.encode_game_turn_json()` central helper used
  by both `database_sqlite.record_game_turn()` and
  `database_postgres.record_game_turn()` for the
  `choices` / `state_delta` / `state_after` JSON encoding step.

### Changed

- `GameEngine.attempt_breakthrough()` now invokes
  `_run_breakthrough_narrator()` instead of inlining the
  `run_turn_sync` + try/except branch. The `_set_choices` fallback emitted
  from that helper still uses `source="breakthrough_narrator_exception"`.
  The follow-up `if result.get("llm_error")` check, the
  `突破叙事失败: <error>` payload and the `source="breakthrough_narrator_error"`
  fallback remain inline inside `attempt_breakthrough()`.
- `WebGameService.save()` and `WebGameService.load()` now resolve runners
  through `_require_non_guest_runner(action=...)`, which centralises the
  `is_guest_user_id → PermissionError("访客…")` raise. The other call sites
  (`get_session`, `start_session`, `choose`, `act`, `end_session`,
  `death_summary`) keep the direct `self._runner(session_id, user_id=user_id)`
  call they used before; the interim `_with_runner()` alias was removed in
  the same pass because it had no extra logic.
- `database_sqlite.record_game_turn()` and
  `database_postgres.record_game_turn()` now call
  `encode_game_turn_json()` so the JSON encoding lives in one helper.
- `web/frontend-react/src/pages/CharacterCreatePage.tsx` declares a
  `fateGroups` config array and renders the three `<CatalogGroup>` items
  via a `.map()`; the per-group `selectedName` / `onSelect` / open-state
  wiring is unchanged.
- `web/frontend-react/src/styles/character-create.css` merges the duplicate
  `.character-page` rule into a single block (no visual change).

### Verification

- `python -m compileall -q src tests web scripts migrations` clean.
- `pytest -q tests\web` -> 49 passed, 1 skipped (`TEST_DATABASE_URL` not configured).
- `pytest -q` -> 425 passed, 1 skipped.
- `pytest -q tests/unit/engine/test_game_engine_turn.py tests/unit/engine/test_game_engine_setup.py tests/unit/engine/test_game_engine_state.py tests/unit/game/test_database_common.py` -> 56 passed.
- `cd web\frontend-react; npm.cmd run build` -> 1602 modules, 24.34 kB CSS, 190.37 kB JS.
- No server, deploy, SSH, production account, production live model, or
  browser/Playwright validation was performed in this pass.

### Known deferred items (still on the backlog)

- Production account flow verification on a safe non-secret test account.
- Production live-model success verification (the production guest smoke
  still returned `fallback_prompt_active=true`).
- Further `GameEngine` decomposition beyond the breakthrough-narrator
  slice; the next candidates are the `narrator_exception` / `narrator_error`
  paths in `handle_action` and the `world_builder` paths in
  `new_game` / `_generate_profile_opening`.
- React style file split is still a P2 candidate; the current pass only
  collapsed the duplicate `.character-page` rule.

## 2026-06-23

### Added

- `rarityToColor` / `colorLabel` helpers in `web/frontend-react/src/lib/util.ts` map legacy/internal rarity or grade strings into the unified 6-color palette (白/绿/蓝/紫/橙/红).
- CSS classes `.rarity-white`, `.rarity-green`, `.rarity-blue`, `.rarity-orange` in `styles.css`, alongside the existing `.rarity-purple` and `.rarity-red`.
- Contract-test assertions in `tests/web/test_frontend_contract.py` covering the homepage eyebrow removal, the short brand label `jiayp`, the 6 palette colors, the lifespan `remaining/cap` display, and the front-end reading `character.remaining_lifespan`.
- Project docs `docs/ARCHITECTURE.md` and `docs/USER_TUTORIAL.md` registered in `docs/INDEX.md`.
- UI background generation prompts in `docs/UI_REFACTOR_PLAN.md` for the homepage and character-creation screens.
- Contract checks for the homepage `仙` QQ mark, removal of the title red dot, centered homepage buttons, collapsible catalog groups, and the age-based `凡人长寿` rule.

### Changed

- Homepage (`HomePage.tsx`) drops the eyebrow line `WEB · 文字修仙模拟器` and the four-button descriptive paragraph; the brand link in `main.tsx` shortens to `jiayp` (the underlying URL `https://www.jiayp2917.xyz/` is preserved).
- `styles.css` removes the `.brand::after` jade dot, trims `.home` / `.home-shell` / `.home-preview` / `.hero` spacing so the page fits in a 1080p viewport.
- Character-creation `<option>` labels now render as `${name} · ${rarityToColor}`; the same colored dot is drawn on the host `<label>` because native `<option>` cannot host CSS consistently across browsers.
- Game-page choices are tighter: `.choice-list button` min-height 76 → 60 px, A/B/C/D badge 32 → 28 px; mobile breakpoint 58 → 56 px.
- `GamePage` reads `character.remaining_lifespan` first (fallback `lifespan - age`, clamped by `Math.min`); the summary now shows `${remainingLifespan}/${lifespanMax} 年`, matching `StatLine`.
- Source comments and docstrings in `death_rewards.py`, `game_engine.py`, `game_session.py`, and `game/__init__.py` no longer reference the removed combat / persistence modules.
- Homepage title stays on one line, the title red dot is removed, entry text is centered independently of the left icon, and the QQ badge now displays `仙`.
- Character-creation catalog groups are collapsible with internal scrolling; selected markers moved to the start of each row and the high-contrast rarity hint pills were replaced with plain helper text.
- `凡人长寿` now requires actual character age `>= 80` instead of using the lifespan cap; `/api/sessions/{id}/death_summary` prefers a live session recomputation before falling back to persisted rows.
- `README.md` now links to `docs/UI_REFACTOR_PLAN.md` instead of the removed `docs/WEB_ITERATION_PLAN.md`.

### Removed

- `src/agens_novel/game/combat.py` remnants in git history plus the dead `config/prompts/system/combat_narrator.md`.
- Empty `src/agens_novel/persistence/` shell and its leftover `__pycache__/`.
- `docs/WEB_ITERATION_PLAN.md` (superseded by `RUNTIME_FLOW.md` and `PROJECT_AUDIT.md`).
- Android APK skill `.agents/skills/build-apk/` (out of scope for the Web-only project).
- One-off Playwright smoke scripts under `web/frontend-react/.tmp/`.
- Redundant `.venv311/` Python 3.14 virtual environment alongside the active `.venv/`.
- Orphaned `__pycache__/*.pyc` files whose `.py` source had already been removed.
- Local `runtime/uvicorn-local.{err,out}.log` files.

### Verification

- `python -m compileall -q src tests web` clean.
- `pytest -q` → 466 passed, 1 skipped (no regressions).
- `npm run build` → 1590 modules, 15.18 kB CSS, 179.71 kB JS.

## 2026-06-22

### Added

- Alembic `20260622_0003` for game-mode v5 `game_runs`, `game_turns`, and `player_progress`.
- React public assets under `web/frontend-react/public/assets`, including BGM.
- Web service writes settled turns and terminal run progress for rarity unlocks.

### Changed

- React is the only product frontend entrypoint; old `web/frontend` fallback was removed.
- Docs now describe the current runtime as game-mode v5 Alpha with A/B/C/D fixed semantics.
- Frontend contract tests now target the React entrypoint and public assets.

## 2026-06-21

### Added

- PostgreSQL Alembic schema coverage for catalog tables and death reward tables.
- Production safety gates for allowed origins, OpenAPI hiding, and trusted host checks.
- React turn-action busy guards for A/B/C choices, fallback actions, and D input.
- PostgreSQL smoke path that runs only when `TEST_DATABASE_URL` is configured.
- Archived the game-mode planning draft under `docs/archive/`.
- Alpha review evidence and lessons in `docs/ALPHA_REVIEW_AND_LESSONS.md`.

### Changed

- `docs/INDEX.md` now separates current Alpha runtime docs from future game-mode v5 specs.
- `docs/PROJECT_AUDIT.md` records the React-first entrypoint, legacy frontend retirement, and PG/Alembic authority.
- `docs/ALPHA_REVIEW_AND_LESSONS.md` now records current conclusion, verification evidence, success lessons, failure lessons, residual risks, and follow-up execution rules.
- `/api/invites` now uses a typed request schema instead of ad hoc dict parsing.

## 2026-06-18

### Added

- FastAPI Web backend under `web/backend`.
- Static browser UI under `web/frontend`.
- SQLite users, sessions, saves, chat history snapshots, and masked model settings.
- Web API tests and frontend contract tests under `tests/web`.
- Web-only documentation entry points in `README.md`, `AGENTS.md`, `CLAUDE.md`, and `docs/`.

### Changed

- `master` is now the Web-only mainline.
- Root `main.py` and `Makefile` run the FastAPI app.
- Validation is now core engine tests, Web API tests, and browser UI checks.
- Model configuration is read or updated through the backend and returned only as masked state.

### Removed

- Mobile product source tree and packaging configuration.
- Mobile UI contract tests and mobile startup tests.
- Device-validation and packaging documentation from the Web project.
- Standalone BGM adapter layer that only served the old product path.
