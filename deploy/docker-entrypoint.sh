#!/usr/bin/env sh
set -eu

mkdir -p /app/runtime/web

exec python -m uvicorn web.backend.app:app --host 0.0.0.0 --port "${PORT:-8000}"

