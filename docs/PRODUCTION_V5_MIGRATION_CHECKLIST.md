# Production v5 Migration Checklist

This checklist gates the next `agens-web` production action. It records the
2026-06-24 production v5 deployment sequence, including the build stop,
build-only retry, Alembic success, entrypoint CRLF startup failure, and the
approved entrypoint hotfix that restored service health.

Do not treat v5 production behavior as fully accepted until every item below
has evidence. Current status is restored but still partially accepted.

## 2026-06-27 Model Env Hotfix Addendum

- Root cause for the live-model fallback was the model env-prefix mismatch:
  the app reads `AGNES_API_KEY`, `AGNES_BASE_URL`, `AGNES_MODEL`, and
  `AGNES_REQUEST_TIMEOUT_SECONDS`; production model values had been placed
  under `AGENS_*`.
- Production env was backed up and the correct `AGNES_*` variables were added
  without printing secret values.
- Turn and breakthrough narrator calls now pass
  `repair_incomplete_output=True`, so incomplete structured narrator output can
  be repaired instead of immediately falling back.
- Full rebuild was blocked by the host build path, so the effective production
  recovery used a hotfix image based on the existing `jiayp-agens-web:local`
  image and copied updated code/assets into it.
- Last successful production smoke before interruption: local-origin and
  public-origin guest start/choice both returned `fallback_active=False`,
  `model_failures=0`, and `choices_count=4`.
- Resume-time reachability check on 2026-06-27 failed for
  `192.168.1.250:22`; the successful smoke above is last-known evidence, not a
  fresh current confirmation.
- Production account registration/login/save/load is still not accepted.

## Current Known State

- Public `https://game.jiayp2917.xyz/api/health` returns HTTP 200.
- Public `https://game.jiayp2917.xyz/api/catalog/talents` returns 10 rows.
- Origin `http://127.0.0.1:18000/api/health` returns HTTP 200.
- Production Alembic revision is `20260622_0004`.
- Production PostgreSQL now contains:
  - `game_runs`
  - `game_turns`
  - `player_progress`
- The latest `agens-web` container is healthy and runs image
  `sha256:445367f496bf3b1acb8b091442f775b9c74240251cc19efdfab2d45562dbc791`.
- The entrypoint CRLF failure has been fixed by the approved hotfix package:
  `D:\chat\outputs\packages\agens-web\agens-web-entrypoint-crlf-hotfix-20260624-185815.zip`.
- Guest start and one guest turn returned HTTP 200 in production smoke.
- Production live-model success is not accepted: the guest turn reported
  `fallback_prompt_active=true`.
- Production account registration/login/save/load is not accepted: no safe
  non-secret production test account path was available.
- Old app source is preserved at
  `/srv/jiayp/apps/agens-web.pre-v5-20260624-180650`, with an app tar backup at
  `/srv/jiayp/backups/agens-web/agens-web-app-20260624-180650.tar.gz`.
- PostgreSQL backup from before migration is preserved at
  `/srv/jiayp/backups/postgres/postgres-20260624-180554.sql.gz`.

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
  - `.\.venv\Scripts\python.exe -m pytest -q tests\web` with local
    `TEST_DATABASE_URL`: `50 passed`
  - `.\.venv\Scripts\python.exe -m pytest -q` with local
    `TEST_DATABASE_URL`: `415 passed`
  - `cd web\frontend-react; npm.cmd run build`: passed, 1603 modules,
    24.34 kB CSS, 190.95 kB JS
- Chrome smoke evidence exists for:
  - historical 2026-06-24 desktop guest start, 375px mobile guest start,
    fallback continuation, and latest chronicle card at `玄元历 2 年` after turn
    1
  - historical 2026-06-24 local live-model turn with temporary SQLite: choice
    returned HTTP 200, `fallback_prompt.active=false`, and the UI refreshed
    narrative plus A/B/C/D choices. This predates Option C and is historical
    evidence only.
- Current PostgreSQL local test evidence exists:
  - `TEST_DATABASE_URL` against a safe local PostgreSQL test database
  - `pytest -q tests\web`: `50 passed`
  - `pytest -q tests\web\test_web_api.py::test_postgres_database_url_smoke`: passed
  - Chrome against local PostgreSQL passed guest create/start/one-turn, account
    invite registration/login/session/save/load/list-saves, 2560x1440
    no-overflow smoke, and narrow-window no-overflow smoke
  - local live-model guest turn returned HTTP 200 but took about 63 seconds and
    had incomplete structured-narrative diagnostics; this is a P1
    gameplay/performance risk, not full model-quality acceptance
- Package manifest or archive hash is recorded before upload.
- Server-side app backup path is recorded before replacement.
- PostgreSQL backup or restore point is recorded before Alembic migration.

### 2026-06-24 Local Package Evidence

- Package: `D:\chat\outputs\packages\agens-web\agens-web-11ae5e9-20260624-173644.zip`
- Manifest: `D:\chat\outputs\packages\agens-web\agens-web-11ae5e9-20260624-173644.manifest.md`
- Approved deployment prompt: `D:\chat\outputs\packages\agens-web\agens-web-11ae5e9-20260624-173644.server-deploy-prompt.md`
- Commit: `11ae5e9699277ce08b42a9331932354895922149`
- SHA256: `526b8b6cbbc1abd60b1a03b1d73369778abf8c723d439579526532d9744017ad`
- Size: `45234176` bytes
- Local validation on 2026-06-24:
  - `.\.venv\Scripts\python.exe -m compileall -q src tests web scripts migrations`: passed.
  - `.\.venv\Scripts\python.exe -m pytest -q tests\web`: `49 passed, 1 skipped`.
  - `.\.venv\Scripts\python.exe -m pytest -q`: `425 passed, 1 skipped`.
  - `cd web\frontend-react; npm.cmd run build`: passed.
- Archive source: `git archive --format=zip HEAD`; local `.env`, `production.env`,
  dependency directories, runtime data, caches, and frontend `dist` were not
  packaged.

This evidence covers local package readiness only. It does not replace the
required server backup, PostgreSQL backup/restore point, server-side hash
verification, Alembic upgrade, restart, or post-deploy production smoke.
The approved deployment prompt is prepared but must not be sent to the server
thread until the user explicitly approves the production batch.

### 2026-06-24 Server Read-Only Preflight

Server thread `019ee2ee-823e-7441-bdaa-881782da7949` completed a read-only
preflight and did not deploy, restart, delete, run Alembic upgrade, use sudo, or
read/print secrets.

- Package path was visible to the server thread and SHA256 matched
  `526b8b6cbbc1abd60b1a03b1d73369778abf8c723d439579526532d9744017ad`.
- Public health returned `{"status":"ok"}`.
- Public catalog talents returned 10 rows.
- `agens-web` container is running and healthy on `127.0.0.1:18000->8000`.
- Internal origin health returned HTTP 200.
- Candidate paths exist:
  - staging/upload: `/tmp`
  - app directory: `/srv/jiayp/apps/agens-web`
  - app backups: `/srv/jiayp/backups/agens-web`
  - PostgreSQL backups: `/srv/jiayp/backups/postgres`
  - PostgreSQL backup helper: `/srv/jiayp/bin/backup-postgres.sh`
- Current production Alembic revision remains `20260621_0002`.
- `game_runs`, `game_turns`, and `player_progress` remain missing.

The preflight satisfies entry into a user-approved deployment window. It does
not approve or complete production deployment.

### 2026-06-24 Approved Deployment Attempt: Stopped At Docker Build

User approval was granted for the P0 production v5 deployment batch. Server
thread `019ee2ee-823e-7441-bdaa-881782da7949` executed the approved batch until
the first hard failure and then stopped.

Completed evidence:

- Package uploaded to `/tmp/agens-web-11ae5e9-20260624-173644.zip`.
- Server SHA256 matched
  `526b8b6cbbc1abd60b1a03b1d73369778abf8c723d439579526532d9744017ad`.
- PostgreSQL backup was generated and `gzip -t` passed:
  - `/srv/jiayp/backups/postgres/postgres-20260624-180554.sql.gz`
  - size: `15K`
- App backup was generated and gzip/tar readability checks passed:
  - `/srv/jiayp/backups/agens-web/agens-web-app-20260624-180650.tar.gz`
  - size: `30M`
- Staging unpack succeeded.
- Sensitive filename scan found no real `.env`, `production.env`, token,
  credentials, or `key.txt` file.
- App source directory was replaced:
  - current source path: `/srv/jiayp/apps/agens-web`
  - old source preserved at `/srv/jiayp/apps/agens-web.pre-v5-20260624-180650`

Stop point:

- `docker compose ... build agens-web` failed during `pip install -r
  requirements.txt`.
- Error summary: no matching distribution was found for
  `langchain-core>=0.3.0` from the server's current build dependency source.

Not executed:

- Alembic upgrade was not run.
- `agens-web` container was not restarted or recreated.
- No rollback was run.
- Production account flow and production live-model smoke were not run.

Post-failure read-only status:

- Existing running container remained healthy on `127.0.0.1:18000->8000`.
- Public `https://game.jiayp2917.xyz/api/health` still returned
  `{"status":"ok"}`.
- Public catalog talents still returned 10 rows.
- Production Alembic revision remained `20260621_0002`.
- `game_runs`, `game_turns`, and `player_progress` remain unaccepted in
  production because migration did not run.

Residual risk:

- Disk source at `/srv/jiayp/apps/agens-web` is now the new package, while the
  running container is still the old image/code. A future restart or rebuild
  can fail or activate an unverified source tree unless the dependency issue is
  fixed first or the old app directory is restored under a separately approved
  rollback/recovery action.
- Any rollback or recovery remains a separate production action and requires
  explicit approval.

### 2026-06-24 Read-Only Build Stop Diagnosis

Server thread `019ee2ee-823e-7441-bdaa-881782da7949` ran a follow-up read-only
diagnostic after the Docker build failure. It did not retry the build, install
packages, change files, restart services, run Alembic, or roll back.

Evidence:

- Existing running container was still healthy on `127.0.0.1:18000->8000`.
- Public health still returned `{"status":"ok"}`.
- Public catalog talents still returned 10 rows.
- Current source still contains `langchain-core>=0.3.0` in `requirements.txt`.
- Runtime Docker base remains `FROM python:3.12-slim AS runtime`.
- Server host Python is `Python 3.14.4`, but host `pip3` / `python3 -m pip`
  is not available, so host pip config could not be checked.
- A temporary `python:3.12-slim` container could run `pip index versions
  langchain-core` without installing packages.
- That index query could see `langchain-core`, including `0.3.0` and newer
  releases up to `1.4.8`.

Conclusion:

- `langchain-core>=0.3.0` is a valid dependency constraint.
- Python 3.12 is not the cause.
- The most likely cause is a transient or build-context-specific pip
  index/network issue during the original Docker build.

Next approved action must choose one path:

- Retry a controlled `agens-web` image build only after confirming the build
  dependency source is reachable.
- Build and transfer a local image if server-side PyPI access remains unstable.
- Prepare an offline wheelhouse if repeatability matters more than speed.
- Separately approve app-source recovery from
  `/srv/jiayp/apps/agens-web.pre-v5-20260624-180650` or the app tar backup to
  remove the disk-source/running-image mismatch without deploying v5.

Prepared build-only retry prompt:

- `D:\chat\outputs\packages\agens-web\agens-web-11ae5e9-20260624-173644.server-build-only-prompt.md`
- This prompt is not approval to execute. It only scopes a future user-approved
  batch that may build the `agens-web` image and then stop before Alembic,
  restart/recreate, rollback, or public exposure changes.

### 2026-06-24 Build-Only Retry: Passed

User approval was granted for a build-only retry. Server thread
`019ee2ee-823e-7441-bdaa-881782da7949` executed only the build scope and did
not run Alembic, restart/recreate the service, roll back, or change public
exposure.

Evidence:

- Normal compose build progressed past the original `langchain-core` stop, but
  later failed on a `files.pythonhosted.org` read timeout.
- Build-only fallback succeeded:
  - `DOCKER_BUILDKIT=0 docker build --network=host -t jiayp-agens-web:local /srv/jiayp/apps/agens-web`
- Built image:
  - tag: `jiayp-agens-web:local`
  - id: `sha256:f2d2b86e3de0c9aff5131ed238c84eb435cb0d31983e5e4629b8b75add4d6c15`
  - created: `2026-06-24T18:37:42+08:00`
- The running container still used the old image after this build-only step and
  public health/catalog still passed.
- Production Alembic remained `20260621_0002` after this build-only step.

### 2026-06-24 Migration And Restart Attempt: Stopped At Entrypoint CRLF

User approval was then granted for Alembic upgrade, restarting/recreating only
`agens-web`, and production verification. Server thread
`019ee2ee-823e-7441-bdaa-881782da7949` stopped at the first hard failure.

Completed evidence:

- Backup paths were rechecked.
- New image id was rechecked:
  - `sha256:f2d2b86e3de0c9aff5131ed238c84eb435cb0d31983e5e4629b8b75add4d6c15`
- Alembic upgrade succeeded:
  - `20260621_0002 -> 20260622_0003`
  - `20260622_0003 -> 20260622_0004`
- Production revision is now `20260622_0004`.
- Required v5 tables exist:
  - `game_runs`
  - `game_turns`
  - `player_progress`
- Only the `agens-web` container was recreated.

Stop point:

- New container used the target image but entered restart loop:
  - status: `Restarting (127)` / unhealthy
- Error summary:
  - `env: 'sh\r': No such file or directory`
  - `env: use -[v]S to pass options in shebang lines`
- Root cause: `deploy/docker-entrypoint.sh` was CRLF inside the image, so the
  shebang resolved to `sh\r`.
- Public health after the failed restart returned HTTP 502.

Not executed after the stop point:

- Origin health verification.
- Public catalog verification.
- Guest start and one-turn smoke.
- Production account flow.
- Production live-model smoke.
- Rollback.

Local source hardening after this failure:

- `.gitattributes` now forces shell scripts and `Dockerfile` to LF.
- `Dockerfile` strips CRLF from `/usr/local/bin/agens-web-entrypoint.sh` after
  copying it into the runtime image.

Prepared hotfix prompt:

- `D:\chat\outputs\packages\agens-web\agens-web-11ae5e9-20260624-173644.entrypoint-crlf-hotfix-prompt.md`
- This prompt is not approval to execute. It scopes a future user-approved
  batch that only normalizes the entrypoint, rebuilds, recreates `agens-web`,
  and verifies production.

Local hotfix package evidence:

- Package: `D:\chat\outputs\packages\agens-web\agens-web-entrypoint-crlf-hotfix-20260624-185815.zip`
- SHA256: `261ecef7fbeac0928b076802e4cd458607c651ae15153f9ea700a01afd8ce1f4`
- Contents:
  - `.gitattributes`
  - `Dockerfile`
  - `deploy/docker-entrypoint.sh`
- Package entrypoint line endings verified as LF-only (`crlf=0`).
- Local validation after preparing the package:
  - `.\.venv\Scripts\python.exe -m compileall -q src tests web scripts migrations`: passed.
  - `.\.venv\Scripts\python.exe -m pytest -q`: `425 passed, 1 skipped`.
  - `cd web\frontend-react; npm.cmd run build`: passed.
  - `D:\chat\ai-governance\agents\output-index.yaml` parsed as YAML.
  - `git diff --check`: passed.

### 2026-06-24 Hotfix Read-Only Preflight

Server thread `019ee2ee-823e-7441-bdaa-881782da7949` completed a strict
read-only preflight before the entrypoint CRLF hotfix. It did not upload,
modify, build, restart/recreate, roll back, run Alembic, change public
configuration, or read/print secrets.

Evidence:

- `agens-web` container remains `Restarting (127)` / unhealthy.
- Running image id remains
  `sha256:f2d2b86e3de0c9aff5131ed238c84eb435cb0d31983e5e4629b8b75add4d6c15`.
- Public health remains HTTP 502.
- Origin health `http://127.0.0.1:18000/api/health` cannot connect.
- Alembic revision remains `20260622_0004`.
- Required v5 tables still exist:
  - `game_runs`
  - `game_turns`
  - `player_progress`
- Backup evidence still exists:
  - `/srv/jiayp/apps/agens-web.pre-v5-20260624-180650`
  - `/srv/jiayp/backups/agens-web/agens-web-app-20260624-180650.tar.gz` (`30M`)
  - `/srv/jiayp/backups/postgres/postgres-20260624-180554.sql.gz` (`15K`)
- Server entrypoint line-ending check:
  - `lf_count=10`
  - `crlf_count=10`
  - `has_crlf=True`
- Server Dockerfile hardening check:
  - `dockerfile_crlf_hardening=miss`
- Prepared hotfix package is visible to the server thread and SHA256 matched:
  - `D:\chat\outputs\packages\agens-web\agens-web-entrypoint-crlf-hotfix-20260624-185815.zip`
  - `261ecef7fbeac0928b076802e4cd458607c651ae15153f9ea700a01afd8ce1f4`

Conclusion:

- Hotfix diagnosis is confirmed. The next production action still requires
  explicit approval and should apply only the prepared entrypoint CRLF hotfix,
  then build-only, recreate only `agens-web`, and run production verification.

### 2026-06-24 Entrypoint CRLF Hotfix: Passed

User approval was granted for the narrow entrypoint CRLF hotfix. Server thread
`019ee2ee-823e-7441-bdaa-881782da7949` completed the approved batch and did not
change Cloudflare, Tunnel, Caddy, DNS, firewall, database revision, unrelated
services, or secrets.

Changed files on the server:

- `/srv/jiayp/apps/agens-web/.gitattributes`
- `/srv/jiayp/apps/agens-web/Dockerfile`
- `/srv/jiayp/apps/agens-web/deploy/docker-entrypoint.sh`

Backup:

- `/srv/jiayp/backups/agens-web/entrypoint-crlf-hotfix-20260624-185815/`

Completed evidence:

- Hotfix package SHA256 matched
  `261ecef7fbeac0928b076802e4cd458607c651ae15153f9ea700a01afd8ce1f4`.
- Package contents were limited to `.gitattributes`, `Dockerfile`, and
  `deploy/docker-entrypoint.sh`.
- Server entrypoint was confirmed LF-only after the hotfix (`crlf_count=0`).
- Server Dockerfile hardening was confirmed.
- `agens-web` image build passed through the known host-network fallback.
- New image id:
  `sha256:445367f496bf3b1acb8b091442f775b9c74240251cc19efdfab2d45562dbc791`.
- Only `agens-web` was recreated.
- Running container is healthy and uses image
  `sha256:445367f496bf3b1acb8b091442f775b9c74240251cc19efdfab2d45562dbc791`.
- Origin health returned HTTP 200.
- Public health returned HTTP 200.
- Public catalog talents returned 10 rows.
- Production Alembic remained `20260622_0004`.
- `game_runs`, `game_turns`, and `player_progress` still exist.
- Log sensitive-marker scan returned 0.
- Guest start returned HTTP 200.
- One guest turn returned HTTP 200 and still returned four options.

Residual acceptance gaps:

- Production account flow is not accepted because no safe non-secret test
  account path was available. It needs a user-provided test account, invite, or
  separately approved test-account creation path.
- Production live-model success is not accepted because the guest smoke returned
  `fallback_prompt_active=true`. The smoke proves the fallback gameplay path is
  restored, not that the production live model is healthy.
- Rollback is not currently needed for service recovery. Any rollback drill
  remains a separate approved production action.

## Future Production Verification

Before full production acceptance, keep the restored service evidence current
and close the remaining smoke gaps.

1. Confirm production revision remains `20260622_0004` and v5 tables still
   exist.
2. Confirm `agens-web` container remains healthy and public health/catalog still
   return expected results.
3. Verify production account registration/login/save/load only with a safe
   non-secret test account or a separately approved test-account creation path.
4. Verify production live-model behavior without printing secrets; do not count
   fallback as live-model success.
5. Continue log redaction and rate-limit observation while the public Alpha is
   exposed.

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
- Production live-model flow returns a non-fallback result. Fallback must be
  recorded as restored gameplay only, not model success.

## Rollback Gate

Rollback is a separate production change. Before any rollback:

- Identify the app backup path.
- Identify the database backup/restore point.
- State expected user-visible impact.
- Get explicit approval for the rollback action.

## Handoff Note

If full acceptance is deferred, record the blocker as:

> Production v5 is partially accepted: the service is healthy, production
> Alembic is `20260622_0004`, the v5 tables exist, health/catalog and guest
> fallback gameplay pass, but production account flow and live-model success are
> not accepted yet. The last guest smoke returned `fallback_prompt_active=true`.
