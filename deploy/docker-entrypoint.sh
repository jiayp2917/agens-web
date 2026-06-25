#!/usr/bin/env sh
set -eu

mkdir -p /app/runtime/web

# PostgreSQL is the only backend (Option C consolidation); always apply migrations.
alembic -c /app/alembic.ini upgrade head

exec python -m uvicorn web.backend.app:app --host 0.0.0.0 --port "${PORT:-8000}"
