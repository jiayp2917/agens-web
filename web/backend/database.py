"""Database factory for the web adapter."""

from __future__ import annotations

import os
from pathlib import Path

from .database_common import default_db_path
from .database_sqlite import SQLiteWebDatabase


# Backwards-compatible name for existing tests/imports. The factory below is
# the production entrypoint; direct construction remains SQLite-local.
WebDatabase = SQLiteWebDatabase


def create_database(db_path: Path | None = None):
    backend = os.environ.get("DATABASE_BACKEND", "sqlite").strip().lower()
    if backend in ("", "sqlite", "sqlite3"):
        return SQLiteWebDatabase(db_path)
    if backend in ("postgres", "postgresql", "pg"):
        from .database_postgres import PostgresWebDatabase

        return PostgresWebDatabase(os.environ.get("DATABASE_URL"))
    raise RuntimeError(f"Unsupported DATABASE_BACKEND: {backend}")
