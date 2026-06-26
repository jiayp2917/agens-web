# Next Governance Backlog

This file is the active backlog for continuing `agens-web` governance. It
separates local work from production work so future agents do not treat local
validation as production acceptance.

## Current Evidence

- Local code validation is green as of 2026-06-26:
  - `python -m compileall -q src tests web scripts migrations`
  - `pytest -q tests\web` with local `TEST_DATABASE_URL` -> 50 passed
  - `pytest -q tests\unit\engine\test_flow_failure_paths.py tests\unit\engine\test_game_engine_turn.py tests\unit\engine\test_game_engine_setup.py tests\unit\engine\test_game_engine_state.py` -> 56 passed
  - `pytest -q tests\unit\game\test_database_common.py tests\unit\game\test_game_turns_storage.py tests\web\test_web_api.py::test_postgres_database_url_smoke` -> 13 passed
  - `pytest -q` with local `TEST_DATABASE_URL` -> 415 passed
  - `web\frontend-react npm.cmd run build` -> passed, 1603 modules,
    24.34 kB CSS, 190.95 kB JS
- Historical 2026-06-24 baseline before Option C:
  - `pytest -q tests\web` -> 49 passed, 1 skipped
  - `pytest -q` -> 425 passed, 1 skipped
  - `pytest -q tests/unit/engine/test_game_engine_turn.py tests/unit/engine/test_game_engine_setup.py tests/unit/engine/test_game_engine_state.py tests/unit/game/test_database_common.py` -> 56 passed
  - `web\frontend-react npm.cmd run build` (1602 modules / 24.34 kB CSS / 190.37 kB JS)
- Local Chrome validation covers:
  - desktop guest create/start/one-turn flow against local PostgreSQL
  - local Chrome UI account flow against PostgreSQL: invite registration,
    logged-in home state, account new game, save to `slot_1`, and load from
    `slot_1` all passed; screenshot:
    `D:\chat\agens-web\output\agens-web-local-pg-account-ui-20260626.png`
  - 2560x1440 layout smoke with no horizontal overflow; screenshot:
    `D:\chat\agens-web\output\agens-web-local-pg-2k-20260626.png`
  - narrow-window smoke at the Chrome DevTools minimum effective width
    (~500 px) with no horizontal overflow; screenshot:
    `D:\chat\agens-web\output\agens-web-local-pg-mobile-500w-20260626.png`
  - live-model guest turn returned HTTP 200, but it took about 63 seconds and
    the narrator diagnostic reported incomplete structured narrative; treat this
    as a gameplay-flow/performance risk, not as full model-quality acceptance

## 2026-06-24 P1 local complexity governance batch

- Boundary: in-repo only. No server / SSH / Cloudflare / Caddy / Tunnel /
  DNS / firewall / production database / production account / production
  live model / Chrome / Playwright work. No Alembic upgrade, no service
  restart.
- Changes:
  - `GameEngine._run_breakthrough_narrator()` owns the
    `run_turn_sync("narrator", ...)` call and the raw exception branch in
    `attempt_breakthrough()`. The exception fallback uses
    `source="breakthrough_narrator_exception"`. The post-call
    `if result.get("llm_error")` block and the
    `source="breakthrough_narrator_error"` fallback are still inline in
    `attempt_breakthrough()` and remain a P1 candidate.
  - `WebGameService._require_non_guest_runner(action=...)` centralises the
    `is_guest_user_id → PermissionError("访客…")` guard used by `save` and
    `load`. The other call sites (`get_session`, `start_session`, `choose`,
    `act`, `end_session`, `death_summary`) keep calling
    `self._runner(session_id, user_id=user_id)` directly; the intermediate
    `_with_runner()` thin alias was removed in the same pass because it
    added no semantics. API schema, status codes, and DB behavior
    unchanged.
  - `web/backend/database_common.encode_game_turn_json()` central helper
    for the `choices` / `state_delta` / `state_after` JSON encoding used
    by both `record_game_turn` writers. SQL, schema, and applied Alembic
    revision unchanged.
  - `web/frontend-react/src/pages/CharacterCreatePage.tsx` collapses the
    three repeated `<CatalogGroup>` blocks into a `fateGroups` config
    array + `.map()`; `web/frontend-react/src/styles/character-create.css`
    merges the duplicate `.character-page` rule.
- Cleanup within the same pass:
  - Removed unused `GAME_TURN_JSON_FIELDS` constant from
    `web/backend/database_common.py` (no callers in the repo).
- Explicit non-acceptance: this batch is **not** a production account or
  live-model acceptance. P0 production work still requires the Codex /
  server thread batch described in `docs/PRODUCTION_V5_MIGRATION_CHECKLIST.md`.
- Local production package evidence exists:
  - package `D:\chat\outputs\packages\agens-web\agens-web-11ae5e9-20260624-173644.zip`
  - manifest `D:\chat\outputs\packages\agens-web\agens-web-11ae5e9-20260624-173644.manifest.md`
  - approved deployment prompt `D:\chat\outputs\packages\agens-web\agens-web-11ae5e9-20260624-173644.server-deploy-prompt.md`
  - entrypoint CRLF hotfix prompt `D:\chat\outputs\packages\agens-web\agens-web-11ae5e9-20260624-173644.entrypoint-crlf-hotfix-prompt.md`
  - entrypoint CRLF hotfix package `D:\chat\outputs\packages\agens-web\agens-web-entrypoint-crlf-hotfix-20260624-185815.zip`
  - entrypoint CRLF hotfix package SHA256 `261ecef7fbeac0928b076802e4cd458607c651ae15153f9ea700a01afd8ce1f4`
  - commit `11ae5e9699277ce08b42a9331932354895922149`
  - SHA256 `526b8b6cbbc1abd60b1a03b1d73369778abf8c723d439579526532d9744017ad`
- Production is partially accepted:
  - production Alembic is now `20260622_0004`
  - production contains `game_runs`, `game_turns`, and `player_progress`
  - server read-only preflight on 2026-06-24 confirmed package hash, public
    health/catalog, container health, and backup/staging path candidates, but
    did not execute backup, deployment, migration, restart, or smoke acceptance
  - the approved 2026-06-24 deployment attempt created PostgreSQL and app
    backups and replaced `/srv/jiayp/apps/agens-web`, but stopped before
    Alembic/restart because Docker build could not resolve
    `langchain-core>=0.3.0`
  - the running old container was still healthy after the failed build; disk
    source and running image are now intentionally recorded as out of sync until
    a retry or separately approved recovery closes it
  - read-only follow-up diagnosis showed `python:3.12-slim` can currently see
    `langchain-core` versions including `0.3.0`; the failure is most likely
    transient or build-context-specific pip index/network behavior, not an
    invalid dependency constraint
  - the approved build-only retry succeeded through host-network fallback and
    produced image `sha256:f2d2b86e3de0c9aff5131ed238c84eb435cb0d31983e5e4629b8b75add4d6c15`
  - the approved migration/restart batch upgraded Alembic to `20260622_0004`
    and confirmed all three v5 tables, then stopped after the new container
    failed with `env: 'sh\r': No such file or directory`
  - public health was HTTP 502 at that stop point until the later entrypoint
    CRLF hotfix restored service
  - local source has been hardened with `.gitattributes` LF rules and Dockerfile
    CRLF stripping for the entrypoint
  - local hotfix package contains only `.gitattributes`, `Dockerfile`, and
    `deploy/docker-entrypoint.sh`; package entrypoint was verified as LF-only
  - server read-only hotfix preflight confirmed the deployed entrypoint has
    `crlf_count=10`, deployed Dockerfile hardening is missing, backups still
    exist, hotfix package is visible to the server thread, and public health is
    still HTTP 502
  - the approved entrypoint CRLF hotfix succeeded, changed only
    `.gitattributes`, `Dockerfile`, and `deploy/docker-entrypoint.sh` on the
    server, and backed those files up at
    `/srv/jiayp/backups/agens-web/entrypoint-crlf-hotfix-20260624-185815/`
  - the restored production image is
    `sha256:445367f496bf3b1acb8b091442f775b9c74240251cc19efdfab2d45562dbc791`
  - current service evidence after hotfix: container healthy, origin health
    HTTP 200, public health HTTP 200, public catalog talents returns 10 rows,
    Alembic remains `20260622_0004`, v5 tables exist, log sensitive-marker scan
    count is 0, guest start and one guest turn returned HTTP 200
  - server-thread P0 recheck after the server recovered confirmed homepage
    root/www HTTP 200, game health HTTP 200, catalog 10 rows, container healthy,
    origin health HTTP 200, Alembic `20260622_0004`, v5 tables present, and log
    sensitive-marker scan count 0
  - production guest live smoke is still not accepted: start returned HTTP 200
    with `fallback_prompt.active=false`, but the one-turn request returned HTTP
    200 with `fallback_prompt.active=true`
  - remaining acceptance gaps: production account flow was not tested because no
    safe non-secret test account path was available; production live-model
    success was not accepted because the guest smoke returned
    `fallback_prompt_active=true`

## P0: Needs Explicit Approval

These tasks modify remote production state. Do not execute without explicit
approval for the concrete command batch.

1. Verify production account registration/login/save/load with a safe
   non-secret test account, invite, or separately approved test-account creation
   path.
2. Verify production live-model success without printing secrets; do not count
   fallback as live-model success.
3. Continue public Alpha observation for log redaction, rate limiting, cookie
   behavior, and origin restrictions.
4. Confirm existing backup paths before any new mutation:
   - app backup:
     `/srv/jiayp/backups/agens-web/agens-web-app-20260624-180650.tar.gz`
   - old app source:
     `/srv/jiayp/apps/agens-web.pre-v5-20260624-180650`
   - PostgreSQL backup:
     `/srv/jiayp/backups/postgres/postgres-20260624-180554.sql.gz`
   - entrypoint hotfix backup:
     `/srv/jiayp/backups/agens-web/entrypoint-crlf-hotfix-20260624-185815/`
5. If future service health fails, choose a separately approved recovery path:
   app-only recovery, image rebuild, or full DB + app rollback in a maintenance
   window.

Authoritative checklist: `docs/PRODUCTION_V5_MIGRATION_CHECKLIST.md`.

## P1: Local Complexity Reduction

These are safe local governance slices when production approval is deferred.

1. `GameEngine` split planning and tests:
   - keep `GameEngine` as the public gameplay entrypoint
   - extract only one responsibility at a time
   - start with model failure/local story/breakthrough helpers if tests already
     cover the behavior
2. Web service boundary:
   - continue reducing duplication inside `WebGameService`
   - avoid changing API schema or persistence behavior
   - prefer private helpers before router/module splits
3. PostgreSQL 数据层共享 helper 收敛（Option C 已删除 SQLite 双轨，仅保留 PostgreSQL 单后端）：
   - 当前 `database_postgres.py` 的 test-only auto-DDL 已拆到 `database_postgres_schema.py`
   - 继续抽取 catalog row shaping / progress summary 等共享 helper（仅 `database_postgres.py`）
   - 不改表定义或已应用的 Alembic revision
4. React maintenance:
   - continue splitting `CharacterCreatePage` and style files only around
     verified UI workflows
   - use Chrome smoke after visual changes

## P2: Cleanup And Documentation

1. Keep `docs/INDEX.md`, `docs/PROJECT_AUDIT.md`, and this backlog aligned
   after each governance slice.
2. Treat `output/playwright/` and other local screenshots as generated
   artifacts unless explicitly promoted to evidence.
3. Keep old SQLite references clearly marked as historical evidence; current
   runtime/test facts are PostgreSQL-only.
4. Do not delete historical artifacts without inventory, backup, and
   quarantine.

## Validation Rules

- For backend/service changes:
  - targeted tests first
  - `compileall`
  - `pytest -q tests\web`
  - full `pytest -q` when touching shared gameplay/service code
- For frontend/UI changes:
  - `npm.cmd run build`
  - relevant contract tests
  - Chrome smoke for changed viewport/workflow
- For production:
  - follow `docs/PRODUCTION_V5_MIGRATION_CHECKLIST.md`
  - never read or print secrets
  - never use `AGENS_PG_AUTO_DDL=1` in production
