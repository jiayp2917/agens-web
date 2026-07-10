"""normalize catalog attribute metadata to v5 scale"""

from __future__ import annotations

import json
from typing import Any

import sqlalchemy as sa
from alembic import op

revision = "20260704_0006"
down_revision = "20260622_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    talents = bind.execute(sa.text("SELECT id, attribute_mods FROM catalog_talents")).mappings()
    for row in talents:
        mods = _as_dict(row["attribute_mods"])
        normalized = {
            str(key): _normalize_modifier(value)
            for key, value in mods.items()
            if _normalize_modifier(value) != 0
        }
        bind.execute(
            sa.text("UPDATE catalog_talents SET attribute_mods = CAST(:mods AS jsonb) WHERE id = :id"),
            {"id": row["id"], "mods": json.dumps(normalized, ensure_ascii=False)},
        )

    difficulties = bind.execute(sa.text("SELECT id, luck_modifier FROM catalog_difficulties")).mappings()
    for row in difficulties:
        bind.execute(
            sa.text("UPDATE catalog_difficulties SET luck_modifier = :value WHERE id = :id"),
            {"id": row["id"], "value": _normalize_modifier(row["luck_modifier"])},
        )


def downgrade() -> None:
    # This data migration is intentionally not reversible; old 0-100-scale
    # catalog modifiers should not be restored.
    return None


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _normalize_modifier(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    try:
        number = int(value)
    except (TypeError, ValueError):
        return 0
    if -3 <= number <= 3:
        return number
    magnitude = min(3, int(abs(number) / 5 + 0.5))
    return magnitude if number > 0 else -magnitude
