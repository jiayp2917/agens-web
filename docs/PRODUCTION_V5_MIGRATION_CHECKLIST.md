# Production v5 Migration Checklist

## 2026-06-27 Local Main-Flow Fix Addendum

- Local-only fix landed after visible-Chrome validation found HTTP 200 with
  unchanged `turn_count` on valid choice clicks. This was a code/main-flow
  issue, not a production/server operation.
- Fixed local behavior:
  - free-text `/choice` payloads are rejected;
  - premature breakthrough choices settle as ordinary turns when realm rules
    reject breakthrough;
  - narrative/state mismatch rejection records contiguous `game_turns`;
  - accepted local-story fallback records its transition turn so registered-user
    `game_turns` remains contiguous when the narrator returns no usable choices.
- Local validation after this fix: `tests\web` -> `54 passed`, full
  `pytest -q` -> `416 passed`, frontend `npm.cmd run build` passed. This local
  green state does not prove production live-model success.
- At that time, production acceptance was unchanged by this local fix. Later
  2026-06-30 server-thread evidence accepted the production account flow, but
  production live-model success still requires start+choice non-fallback proof.
  Any fallback response still fails the live-model gate.

This checklist gates the next `agens-web` production action. It records the
2026-06-24 production v5 deployment sequence, including the build stop,
build-only retry, Alembic success, entrypoint CRLF startup failure, and the
approved entrypoint hotfix that restored service health.

Do not treat a new production batch as accepted until every required item below
has evidence. Historical sections retain earlier partial-acceptance records; the
current production P0 status is recorded in the 2026-07-02 addendum.

## 2026-07-02 Production P0 Acceptance Addendum

- Server thread `019ee2ee-823e-7441-bdaa-881782da7949` deployed `25ad3d15`
  with a tracked production package and kept Alembic at `20260622_0005`.
- Production `user_model_configs` exists; container health, public/origin
  health, catalog, and sensitive-marker log scan passed.
- One-time real-account registration, login, start, choice, save, load,
  relogin, and cross-session restore passed with sanitized reporting only.
- Production live-model acceptance passed for this batch: start and at least
  one choice were non-fallback, and choice advanced to `turn_count=1`.
- This closes the current P0 production blocker. Future production deploys,
  model-config changes, or provider changes must rerun the same non-fallback
  start+choice gate; HTTP 200 alone still does not count.

## 2026-06-27 Model Env Hotfix Addendum

- Historical 2026-06-27 root cause for that hotfix batch was the model
  env-prefix mismatch:
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
- Historical 2026-06-27 smoke before interruption, not current acceptance:
  local-origin and public-origin guest start/choice both returned
  `fallback_active=False`, `model_failures=0`, and `choices_count=4`.
- Resume-time reachability check on 2026-06-27 failed for
  `192.168.1.250:22`; the successful smoke above is last-known evidence, not a
  fresh current confirmation.
- This addendum is historical. The later 2026-06-30 production batch accepted
  account registration/login/save/load, while production live-model acceptance
  still remained blocked by a separate legacy `model_config` shadowing issue.

## Current Known State

- Public `https://game.jiayp2917.xyz/api/health` returns HTTP 200.
- Public `https://game.jiayp2917.xyz/api/catalog/talents` returns 10 rows.
- Origin `http://127.0.0.1:18000/api/health` returns HTTP 200.
- Production Alembic revision is `20260622_0005`.
- Production PostgreSQL now contains:
  - `game_runs`
  - `game_turns`
  - `user_model_configs`
  - `player_progress`
- The latest `agens-web` container is healthy after the 2026-07-02 deploy.
- The 2026-06-30 production deploy generated/installed `MODEL_CONFIG_SECRET`
  without printing it, created app/PostgreSQL backups, rebuilt only
  `agens-web`, migrated to `20260622_0005`, and passed public/origin
  health, catalog, container-health, and sensitive-marker log checks.
- One-time real-account registration, login, save, load, and cross-session
  restore passed without printing account, password, cookie, invite, database
  URL, or key values.
- The entrypoint CRLF failure has been fixed by the approved hotfix package:
  `D:\chat\outputs\packages\agens-web\agens-web-entrypoint-crlf-hotfix-20260624-185815.zip`.
- Historical production live-model failure: the 2026-06-30 account flow start
  was non-fallback, but one choice turn returned `fallback_active=true` with
  `turn_count=0`.
- Sanitized follow-up diagnosis found that the choice fallback happened before
  any provider request, timeout, or repair path: a legacy `model_config` row had
  no `api_key_encrypted` and shadowed the container environment system key, so
  narrator runtime saw `key_set=false`. Local code now falls back to the env
  system key for that legacy-row shape; the 2026-07-02 deploy revalidated
  start+choice non-fallback.
- The same local follow-up originally failed the 20-turn live browser gate at
  visible turn 7, then an early 2026-07-01 rerun failed at turn 4 fallback.
  Local code now has targeted recovery for that class: narrator parsing accepts
  fenced/bare JSON and Chinese A/B/C/D option lines, live narrative with
  malformed choices no longer immediately enters local story, chronicle display
  strips common Markdown/JSON fence markers, and the narrator prompt explicitly
  rejects JSON-only output.
- Latest local visible Chrome rerun `local-visible-20turn-20260701-final2`
  passed 20/20 non-fallback turns plus save/load, but it does not prove
  production live-model success. The run still shows P1 latency/repair risk
  with about 48.2s average choice latency and about 153.2s maximum latency.
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
- Historical local validation for the 2026-06-24 package was green:
  - `.\.venv\Scripts\python.exe -m compileall -q src tests web scripts migrations`
  - `.\.venv\Scripts\python.exe -m pytest -q tests\web` with local
    `TEST_DATABASE_URL`: `54 passed`
  - `.\.venv\Scripts\python.exe -m pytest -q` with local
    `TEST_DATABASE_URL`: `416 passed`
  - `cd web\frontend-react; npm.cmd run build`: passed, 1603 modules,
    23.69 kB CSS, 189.87 kB JS
- Chrome smoke evidence exists for:
  - historical 2026-06-24 desktop guest start, 375px mobile guest start,
    fallback continuation, and latest chronicle card at `玄元历 2 年` after turn
    1
  - historical 2026-06-24 local live-model turn with temporary SQLite: choice
    returned HTTP 200, `fallback_prompt.active=false`, and the UI refreshed
    narrative plus A/B/C/D choices. This predates Option C and is historical
    evidence only.
- Historical 2026-06-26 PostgreSQL local test evidence:
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
- Latest local validation is tracked in `README.md`, `docs/INDEX.md`, and
  `docs/NEXT_GOVERNANCE_BACKLOG.md`; do not use this historical count as the
  current quality gate.

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

Historical 2026-06-24 hotfix closeout residual gaps, later superseded by the
2026-06-30 account-flow batch and the 2026-07-02 production P0 acceptance:

- Production account flow was not accepted in this historical hotfix closeout
  because no safe non-secret test account path was available. The later
  2026-06-30 production batch accepted account registration/login/save/load and
  cross-session restore.
- Production live-model success was not accepted in that historical hotfix
  closeout because the guest smoke returned `fallback_prompt_active=true`. The
  smoke proved the fallback gameplay path was restored, not that the production
  live model was healthy.
- Rollback is not currently needed for service recovery. Any rollback drill
  remains a separate approved production action.

## Future Production Verification

After each production deployment, model-config change, or provider change, keep
the restored service evidence current and rerun these smoke gates.

1. Confirm production revision remains `20260622_0005` or a later intended
   head, and v5/user-model tables
   still exist.
2. Confirm `agens-web` container remains healthy and public health/catalog still
   return expected results.
3. Re-run production account registration/login/save/load as a regression smoke
   only; the 2026-07-02 account flow already passed.
4. Verify production live-model start and at least one choice without printing
   secrets; do not count
   fallback as live-model success.
5. Continue log redaction and rate-limit observation while the public Alpha is
   exposed.

## Read-Only Post-Deploy Verification

- `alembic_version` equals the intended head, currently `20260622_0005`.
- `information_schema.tables` confirms:
  - `game_runs`
  - `game_turns`
  - `user_model_configs`
  - `player_progress`
- `agens-web` container is healthy.
- Origin health returns HTTP 200.
- Public health returns HTTP 200.
- Public catalog talents returns 10 rows.
- Redaction/log scan does not expose secrets.
- Guest or account start and one turn return HTTP 200.
- Registered account flow is verified with sanitized evidence only; do not
  print account, password, cookie, invite, database URL, or key values.
- Production live-model flow returns non-fallback for start and choice. Fallback
  must be recorded as restored gameplay only, not model success.

## Rollback Gate

Rollback is a separate production change. Before any rollback:

- Identify the app backup path.
- Identify the database backup/restore point.
- State expected user-visible impact.
- Get explicit approval for the rollback action.

## Handoff Note

If a future production acceptance is deferred, record the blocker as:

> Production v5 is partially accepted for the new batch: the service is healthy,
> production Alembic is at the intended revision, and health/catalog/account
> flow passed, but production live-model success is not accepted yet. Record
> the latest fallback flag, turn_count, and sanitized error class; HTTP 200 is
> not enough.
