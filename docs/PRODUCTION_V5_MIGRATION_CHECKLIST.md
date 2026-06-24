# Production v5 Migration Checklist

This checklist gates the next `agens-web` production action. It exists because
read-only server validation on 2026-06-24 confirmed that public health and the
container are healthy, but the production database is still at Alembic
`20260621_0002` and does not have `game_runs`, `game_turns`, or
`player_progress`.

Do not treat v5 production behavior as accepted until every item below has
evidence.

## Current Known State

- Public `https://game.jiayp2917.xyz/api/health` returns HTTP 200.
- Public `https://game.jiayp2917.xyz/api/catalog/talents` is readable and has
  10 visible seed rows.
- Server `agens-web` container is healthy.
- Production Alembic revision is `20260621_0002`.
- Production PostgreSQL is missing:
  - `game_runs`
  - `game_turns`
  - `player_progress`

## Hard Boundaries

- Do not read or print `.env`, tokens, production passwords, cookies, or real
  database URLs.
- Do not run `sudo`, restart services, deploy packages, delete files, or modify
  remote state without explicit confirmation.
- Do not edit applied Alembic revisions. Add follow-on migrations only if a
  deployed database needs a bridge.
- Do not use `AGENS_PG_AUTO_DDL=1` in production. Production schema belongs to
  Alembic.

## Pre-Deploy Evidence

- Local git diff reviewed and scoped to intended source, tests, docs, and
  generated frontend build output policy.
- Local validation is green:
  - `.\.venv\Scripts\python.exe -m compileall -q src tests web scripts migrations`
  - `.\.venv\Scripts\python.exe -m pytest -q tests\web`
  - `.\.venv\Scripts\python.exe -m pytest -q`
  - `cd web\frontend-react; npm.cmd run build`
- Chrome smoke evidence exists for:
  - desktop guest start
  - 375px mobile guest start
  - fallback continuation
  - latest chronicle card at `玄元历 2 年` after turn 1
  - local live-model turn with temporary SQLite: choice returns HTTP 200,
    `fallback_prompt.active=false`, and the UI refreshes narrative plus A/B/C/D
    choices
- Package manifest or archive hash is recorded before upload.
- Server-side app backup path is recorded before replacement.
- PostgreSQL backup or restore point is recorded before Alembic migration.

## Deploy And Migration Sequence

1. Upload the reviewed package to a staging path on the server.
2. Verify package hash on the server before replacing the app directory.
3. Create or confirm an app-directory backup.
4. Create or confirm a PostgreSQL backup/restore point.
5. Replace the app directory according to `D:\chat\server` deployment runbooks.
6. Run Alembic upgrade to head from the deployed package context.
7. Restart only the intended app container or service, with explicit approval.

## Read-Only Post-Deploy Verification

- `alembic_version` equals the intended head, currently `20260622_0004`.
- `information_schema.tables` confirms:
  - `game_runs`
  - `game_turns`
  - `player_progress`
- `agens-web` container is healthy.
- Origin health returns HTTP 200.
- Public health returns HTTP 200.
- Public catalog talents returns 10 rows.
- Redaction/log scan does not expose secrets.
- Guest start and one turn return HTTP 200.
- Registered account flow is verified only if a safe test account and
  non-secret credentials are explicitly provided.

## Rollback Gate

Rollback is a separate production change. Before any rollback:

- Identify the app backup path.
- Identify the database backup/restore point.
- State expected user-visible impact.
- Get explicit approval for the rollback action.

## Handoff Note

If a deployment is deferred, record the blocker as:

> Production v5 is not accepted: public health/catalog are healthy, but the
> production database remains at `20260621_0002` and lacks
> `game_runs` / `game_turns` / `player_progress`.
