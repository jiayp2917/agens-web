"""Pure argument helpers shared by local evaluation entry points."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .ledger import PriceCard


def load_price_card(path: Path | None) -> PriceCard | None:
    if path is None:
        return None
    value: Any = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("price card must be a JSON object")
    return PriceCard(
        effective_date=str(value.get("effective_date") or ""),
        currency=str(value.get("currency") or ""),
        input_per_million=number_or_none(value.get("input_per_million")),
        output_per_million=number_or_none(value.get("output_per_million")),
        cached_input_per_million=number_or_none(value.get("cached_input_per_million")),
    )


def number_or_none(value: Any) -> float | None:
    if value is None:
        return None
    number = float(value)
    if number < 0:
        raise ValueError("price card rates must be non-negative")
    return number


def environment_limit(name: str, default: int) -> int:
    value = os.environ.get(name, "").strip()
    return int(value) if value else default
