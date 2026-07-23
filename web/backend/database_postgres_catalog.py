"""Catalog table read/write repository extracted from PostgresWebDatabase.

Keeps the catalog SQL and row shaping in one place. ``PostgresWebDatabase``
delegates ``list_catalog``/``insert_catalog`` here, so its public API
(``WebDatabaseProtocol``) and on-disk schema are unchanged.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

from .catalog_structure import CATALOG_TABLES
from .database_common import (
    decode_json_fields,
    encode_json_fields,
    now_ts,
    prepare_catalog_row,
)

_SUPPLEMENTABLE_CATALOG_FIELDS = {
    "catalog_spirit_roots": (
        "rarity",
        "description",
        "element",
        "grade",
        "cultivation_bonus",
        "breakthrough_bonus",
        "cultivation_tendency",
        "event_tags",
    ),
}


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

    def supplement_catalog_metadata(
        self,
        table: str,
        name: str,
        metadata: dict[str, Any],
    ) -> bool:
        """Fill only empty catalog metadata without replacing existing values."""
        allowed = _SUPPLEMENTABLE_CATALOG_FIELDS.get(table, ())
        requested = {field: metadata[field] for field in allowed if field in metadata}
        if not requested:
            return False
        with self.engine.begin() as conn:
            existing = conn.execute(
                text(f"SELECT * FROM {table} WHERE name = :name"),
                {"name": name},
            ).mappings().first()
            if existing is None:
                return False
            updates = {
                field: value
                for field, value in requested.items()
                if _catalog_metadata_is_missing(existing.get(field))
            }
            if not updates:
                return False
            updates = encode_json_fields(updates)
            assignments = ", ".join(f"{field} = :{field}" for field in updates)
            conn.execute(
                text(f"UPDATE {table} SET {assignments} WHERE name = :name"),
                {**updates, "name": name},
            )
        return True


def _catalog_metadata_is_missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (dict, list, tuple, set)):
        return not value
    return False
