"""Catalog table read/write repository extracted from PostgresWebDatabase.

Keeps the catalog SQL and row shaping in one place. ``PostgresWebDatabase``
delegates ``list_catalog``/``insert_catalog`` here, so its public API
(``WebDatabaseProtocol``) and on-disk schema are unchanged.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

from .database_common import (
    CATALOG_TABLES,
    decode_json_fields,
    now_ts,
    prepare_catalog_row,
)


class CatalogRepository:
    """Read/write the versioned catalog tables (talents, backgrounds, ...)."""

    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def list_catalog(self, table: str) -> list[dict[str, Any]]:
        if table not in CATALOG_TABLES:
            raise ValueError(f"Unknown catalog table: {table}")
        with self.engine.begin() as conn:
            rows = conn.execute(
                text(f"SELECT * FROM {table} ORDER BY created_at")
            ).mappings().all()
        return [decode_json_fields(row) for row in rows]

    def insert_catalog(self, table: str, row: dict[str, Any]) -> dict[str, Any]:
        if table not in CATALOG_TABLES:
            raise ValueError(f"Unknown catalog table: {table}")
        data = prepare_catalog_row(row, created_at=now_ts())
        cols = ", ".join(data.keys())
        placeholders = ", ".join(f":{k}" for k in data.keys())
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    f"INSERT INTO {table} ({cols}) VALUES ({placeholders}) ON CONFLICT DO NOTHING"
                ),
                data,
            )
        return dict(row)
