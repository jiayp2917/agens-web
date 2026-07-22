# Production v5 Migration Checklist

This checklist gates future `agens-web` production actions. The 2026-07-10 local branch contains schema and runtime changes that have not been deployed or production-validated.

## Current Branch Target

- Intended Alembic target: `20260721_0009_spirit_root_metadata`.
- New runtime requirements: `MODEL_CONFIG_SECRET`, model URL allowlist policy, total model timeout, guest TTL, mutation request IDs and session versions.
- Compose uses a one-shot migration service; application replicas no longer run Alembic at startup.
- Historical production results are recorded in `CHANGELOG.md`; they do not accept this branch.

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
   - Confirm model URL allowlist, total timeout and guest TTL present/missing without printing values.
   - Confirm production Alembic current revision and intended target.
   - Run a read-only orphan check for `game_turns` that cannot link to a run/session; migration `0008` must fail closed rather than delete them.
2. Deploy or mutate only within the approved scope.
   - Rebuild/recreate only approved services.
   - Run Alembic through the approved one-shot migration service, not each app replica.
   - Run Compose with `--env-file deploy/production.env`; service `env_file` does not supply `${...}` interpolation for resource limits.
   - Stop at the first hard failure and report completed/not-completed items.
3. Read-only verification.
   - Container health.
   - Origin/public health.
   - Public catalog count.
   - Required tables and Alembic revision.
   - Sensitive-marker log scan.
4. Account-flow smoke.
   - Register/login, verify guest-session deletion, start/choice/save/load/relogin/cross-session restore with sanitized facts only.
   - Verify duplicate request IDs return the original result and stale expected versions return 409.
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
