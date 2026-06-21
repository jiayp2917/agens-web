# Changelog

## 2026-06-21

### Added

- PostgreSQL Alembic schema coverage for catalog tables and death reward tables.
- Production safety gates for allowed origins, OpenAPI hiding, and trusted host checks.
- React turn-action busy guards for A/B/C choices, fallback actions, and D input.
- PostgreSQL smoke path that runs only when `TEST_DATABASE_URL` is configured.
- Archived the game-mode planning draft under `docs/archive/`.

### Changed

- `docs/INDEX.md` now separates current Alpha runtime docs from future game-mode v5 specs.
- `docs/PROJECT_AUDIT.md` records the React-first entrypoint, legacy frontend fallback policy, and PG/Alembic authority.
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
