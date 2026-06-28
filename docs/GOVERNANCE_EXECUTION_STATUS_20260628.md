# 2026-06-28 Governance Execution Status

This document records what the governance thread can and cannot execute for the
current `agens-web` cleanup batch. It is a handoff and gate document only; it
does not claim that the user-scoped model-settings implementation has landed.

## Current Responsibility Split

- Code thread `019ee0bd-4f73-7553-a8ac-9ab1d8bc7dad` owns local code changes:
  user-scoped model settings, encrypted PostgreSQL storage, model-call
  isolation, frontend settings UI, character-creation double-circle cleanup,
  tests, implementation docs, and the implementation commit.
- Server thread `019ee2ee-823e-7441-bdaa-881782da7949` owns production/server
  checks and deployment gates. It must stay read-only unless the user explicitly
  approves a concrete production mutation batch.
- This governance thread owns dispatch, blocker tracking, local PostgreSQL
  checks, post-implementation review, local validation, visible-Chrome player
  acceptance, and final quality review.

## Cannot Execute Yet

| Item | Why it cannot be executed now | How to handle |
| --- | --- | --- |
| User-scoped model settings acceptance | The implementation is delegated to the code thread and was not yet reported as completed in this governance thread. Current known old risks are admin-only `/api/settings/model`, process-global model key injection, and singleton `model_config`. | Wait for the code thread's final report and commit. Then review diff, migration, tests, and docs before any local/production acceptance claim. |
| Production migration for `user_model_configs` | The migration and code are not yet landed locally, and production database mutation needs separate approval. | After code lands and is reviewed, ask for an explicit server-thread deployment/migration batch. Require app backup, PostgreSQL backup/restore point, `MODEL_CONFIG_SECRET` presence check without printing it, and Alembic validation. |
| Production account registration/login/save/load | This creates or uses production account state and needs a safe non-secret account/invite path or explicit one-time test-account approval. | Provide a temporary non-secret test path, or approve creation and cleanup of a one-time production test account/invite in the server thread. |
| Production user model-settings validation | It depends on the new code, `MODEL_CONFIG_SECRET`, migration, and safe production account path. | Run only after deployment approval and after the server thread verifies the runtime secret exists without printing it. |
| Visible Chrome 20-turn live-model acceptance | It must be run after the model-settings fix so the test covers the real product rule: system default, user key, clear-to-default, save/load, and non-fallback turn flow. | After implementation commit, start local backend/frontend with local PostgreSQL and run a visible Chrome player flow. Fallback is failure for live-model acceptance even when HTTP returns 200. |
| Full production live-model acceptance after model-settings deployment | Current read-only/public health checks are not enough, and HTTP 200 is not enough. | Require non-fallback evidence for start and follow-up choice/turn. Do not print response text, cookies, tokens, or keys. |
| Committing implementation changes from this governance thread | The code thread is the primary writer for this batch. Committing implementation from here would risk mixing responsibility and racing the active implementation thread. | This thread may commit governance/status documentation only. Code changes must be committed by the code thread after its validation gates pass. |

## Local PostgreSQL Status And Handling

- Current local test database endpoint: `127.0.0.1:55432`.
- Check first:

```powershell
F:\pg\bin\pg_isready.exe -h 127.0.0.1 -p 55432
```

- If it returns `accepting connections`, do not run `pg_ctl start` again.
- Only start the existing local test cluster when `pg_isready` does not accept
  connections:

```powershell
F:\pg\bin\pg_ctl.exe start -D D:\chat\agens-web\.tmp\pg-test-20260626-55432 -l D:\chat\agens-web\.tmp\pg-test-20260626-55432.log -o "-p 55432 -h 127.0.0.1"
```

- If `postmaster.pid` appears stale, first confirm no PostgreSQL process is
  using that data directory before deleting the stale pid file.
- Test URL:

```powershell
$env:TEST_DATABASE_URL = "postgresql+psycopg://agens_test@127.0.0.1:55432/agens_web_test"
```

## Post-Implementation Governance Review

After the code thread reports completion, this governance thread should verify:

1. `/api/settings/model` is a logged-in user endpoint, not admin-only.
2. Admin system-default model settings use a separate admin-only endpoint.
3. `user_model_configs` exists with unique `user_id` isolation.
4. PostgreSQL stores encrypted key material and masked state, not raw keys.
5. Missing `MODEL_CONFIG_SECRET` fails closed when encrypted PG keys are needed.
6. Runtime model calls do not mutate `os.environ["AGNES_API_KEY"]`.
7. User A cannot read or overwrite User B model config.
8. Guest model settings access is rejected.
9. Character creation no longer renders a second rarity dot next to the selected
   radio indicator.
10. Docs no longer describe ordinary model settings as admin-only current
    behavior.

## Evidence Files

`D:\chat\agens-web\output\playwright\*.json/png` are local validation evidence
files. They remain untracked by default and should not be committed unless the
user explicitly promotes them to project evidence.
