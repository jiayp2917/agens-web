# Next Governance Backlog

This file is the active backlog for continuing `agens-web` governance. It
separates local work from production work so future agents do not treat local
validation as production acceptance.

## Current Evidence

- Local code validation is green as of 2026-06-24:
  - `python -m compileall -q src tests web scripts migrations`
  - `pytest -q tests\web` -> 49 passed, 1 skipped
  - `pytest -q` -> 425 passed, 1 skipped
  - `web\frontend-react npm.cmd run build`
- Local Chrome validation covers:
  - desktop guest flow
  - 375px mobile guest/fallback flow
  - 2560x1440 layout smoke
  - local account register/login/save/load
  - local live-model turn
- Production is not accepted:
  - public health/catalog are healthy
  - production Alembic is still known as `20260621_0002`
  - production still lacks `game_runs`, `game_turns`, and `player_progress`
  - production must move to Alembic head `20260622_0004`

## P0: Needs Explicit Approval

These tasks modify remote production state. Do not execute without explicit
approval for the concrete command batch.

1. Package current reviewed code and record archive/hash.
2. Confirm app-directory backup path.
3. Confirm PostgreSQL backup or restore point.
4. Replace the server app directory.
5. Run Alembic upgrade to head (`20260622_0004`).
6. Restart only the intended `agens-web` service/container.
7. Verify production revision, tables, health, catalog, guest turn, redaction
   scan, production account flow, and production live-model/account smoke.

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
3. SQLite/PostgreSQL dual track:
   - extract more shared row shaping or summary helpers
   - do not change table definitions or applied Alembic revisions
4. React maintenance:
   - continue splitting `CharacterCreatePage` and style files only around
     verified UI workflows
   - use Chrome smoke after visual changes

## P2: Cleanup And Documentation

1. Keep `docs/INDEX.md`, `docs/PROJECT_AUDIT.md`, and this backlog aligned
   after each governance slice.
2. Treat `output/playwright/` and other local screenshots as generated
   artifacts unless explicitly promoted to evidence.
3. Do not delete historical artifacts without inventory, backup, and
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
