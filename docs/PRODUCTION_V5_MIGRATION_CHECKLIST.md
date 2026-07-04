# Production v5 Migration Checklist

This checklist gates future `agens-web` production actions. The current production P0 batch is accepted, but every future production deploy, model-config change, provider change, or runtime model-call change must rerun the non-fallback gate.

## Current Production State

- Latest accepted production batch: server thread `019ee2ee-823e-7441-bdaa-881782da7949` deployed commit `25ad3d15`.
- Alembic is at `20260622_0005`.
- Required production tables exist, including `game_runs`, `game_turns`, `user_model_configs`, and `player_progress`.
- `agens-web` container was healthy in the accepted batch.
- Public/origin health, catalog, container health, and sensitive-marker log scan passed.
- One-time real-account registration, login, start, choice, save, load, relogin, and cross-session restore passed with sanitized reporting only.
- Production live-model acceptance passed for that batch: start and at least one choice were non-fallback, and choice advanced to `turn_count=1`.

## Hard Boundaries

- Do not read or print `.env`, tokens, production passwords, cookies, invite codes, real account values, raw model requests/responses, or real database URLs.
- Do not run `sudo`, restart services, deploy packages, delete files, roll back, or modify production data without explicit confirmation.
- Do not edit applied Alembic revisions. Add follow-on migrations only if a deployed database needs a bridge.
- Do not use `AGENS_PG_AUTO_DDL=1` in production. Production schema belongs to Alembic.
- HTTP 200 alone is never production live-model success. Fallback must be false and the turn must advance.

## Future Production Gate

After each production deployment, model-config change, provider change, migration affecting runtime, or model-call-path change, rerun this gate through the server thread.

1. Preflight.
   - Confirm intended revision/package/commit.
   - Confirm app and PostgreSQL backup paths or restore points before mutation.
   - Confirm `MODEL_CONFIG_SECRET` present/missing without printing the value.
   - Confirm production Alembic current revision and intended target.
2. Deploy or mutate only within the approved scope.
   - Rebuild/recreate only approved services.
   - Run Alembic only when the approved batch requires it.
   - Stop at the first hard failure and report completed/not-completed items.
3. Read-only verification.
   - Container health.
   - Origin/public health.
   - Public catalog count.
   - Required tables and Alembic revision.
   - Sensitive-marker log scan.
4. Account-flow smoke.
   - Register/login/start/choice/save/load/relogin/cross-session restore with sanitized facts only.
5. Live-model acceptance.
   - Start must be non-fallback.
   - At least one choice must be non-fallback.
   - Choice must advance `turn_count`.
   - Record fallback booleans, turn count, choices count, and sanitized error class only.

## Current Lessons

- A healthy container and account flow do not prove live-model success.
- Legacy DB rows can shadow runtime defaults; system model config must not treat missing encrypted key material as a valid stored key.
- Production evidence must be derived facts: booleans, counts, revisions, status codes, table names, image/package identifiers, and backup paths.
- Keep local Chrome evidence and production evidence separate.
- Rollback is a separate production change and requires explicit approval.

## Rollback Gate

Before any rollback:

- Identify the app backup path.
- Identify the database backup/restore point.
- State expected user-visible impact.
- Get explicit approval for the rollback action.

## Handoff Note

If a future production acceptance is deferred, record the blocker as:

> Production v5 is partially accepted for the new batch: the service is healthy, production Alembic is at the intended revision, and health/catalog/account flow passed, but production live-model success is not accepted yet. Record the latest fallback flag, turn_count, and sanitized error class; HTTP 200 is not enough.