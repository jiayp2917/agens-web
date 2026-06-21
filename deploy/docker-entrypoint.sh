#!/usr/bin/env sh
set -eu

mkdir -p /app/runtime/web

if [ "${DATABASE_BACKEND:-sqlite}" = "postgresql" ] || [ "${DATABASE_BACKEND:-sqlite}" = "postgres" ]; then
  alembic -c /app/alembic.ini upgrade head
fi

exec python -m uvicorn web.backend.app:app --host 0.0.0.0 --port "${PORT:-8000}"
