"""Provider wire-format selection for one canonical agent contract."""

from __future__ import annotations

import os
from enum import StrEnum
from typing import Any


class ProviderTransport(StrEnum):
    JSON_SCHEMA = "json_schema"
    JSON_OBJECT = "json_object"
    LEGACY_TAGS = "legacy_tags"


def narrator_transport(state: dict[str, Any]) -> ProviderTransport:
    """Choose the explicit Narrator transport without changing its semantics."""
    return _transport_for(state, "AGENS_DEEPSEEK_NARRATOR_TRANSPORT")


def world_opening_transport(state: dict[str, Any]) -> ProviderTransport:
    """Choose the World Builder transport for the same provider runtime."""
    return _transport_for(state, "AGENS_DEEPSEEK_WORLD_OPENING_TRANSPORT")


def judge_transport(state: dict[str, Any]) -> ProviderTransport:
    """Choose the Judge transport for the same provider runtime."""
    return _transport_for(state, "AGENS_DEEPSEEK_JUDGE_TRANSPORT")


def response_format(transport: ProviderTransport, schema: dict[str, Any]) -> dict[str, Any] | None:
    """Return the OpenAI-compatible response format for one adapter transport."""
    if transport == ProviderTransport.JSON_SCHEMA:
        return schema
    if transport == ProviderTransport.JSON_OBJECT:
        return {"type": "json_object"}
    return None


def _transport_for(state: dict[str, Any], deepseek_env: str) -> ProviderTransport:
    explicit = str(state.get("provider_transport") or "").strip().lower()
    if explicit in {item.value for item in ProviderTransport}:
        return ProviderTransport(explicit)
    provider = str(state.get("provider") or "").strip().lower()
    model = str(state.get("model") or "").strip().lower()
    if provider == "agens" or model.startswith("agnes-"):
        return ProviderTransport.JSON_SCHEMA
    if provider == "deepseek" or model.startswith("deepseek"):
        configured = os.environ.get(deepseek_env, "").strip().lower()
        if configured == ProviderTransport.JSON_OBJECT.value:
            return ProviderTransport.JSON_OBJECT
        return ProviderTransport.LEGACY_TAGS
    return ProviderTransport.LEGACY_TAGS
