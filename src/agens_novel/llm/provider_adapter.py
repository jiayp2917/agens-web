"""Transport adapter for one canonical model response contract."""

from __future__ import annotations

from enum import StrEnum
from typing import Any


class ProviderTransport(StrEnum):
    JSON_SCHEMA = "json_schema"
    JSON_OBJECT = "json_object"


def narrator_transport(state: dict[str, Any]) -> ProviderTransport:
    """Return the configured Narrator response mode."""
    return _transport_for(state)


def world_opening_transport(state: dict[str, Any]) -> ProviderTransport:
    """Return the configured World Opening response mode."""
    return _transport_for(state)


def response_format(transport: ProviderTransport, schema: dict[str, Any]) -> dict[str, Any] | None:
    """Return the OpenAI-compatible response format for one adapter transport."""
    if transport == ProviderTransport.JSON_SCHEMA:
        return schema
    if transport == ProviderTransport.JSON_OBJECT:
        return {"type": "json_object"}
    return None


def _transport_for(state: dict[str, Any]) -> ProviderTransport:
    """Resolve an explicit response mode without inspecting provider identity.

    ``provider_transport`` is retained only to read older stored configuration.
    New requests default to OpenAI-compatible JSON object transport; legacy tags
    are never selected as a new request or runtime fallback.
    """
    configured = str(
        state.get("response_mode") or state.get("provider_transport") or ""
    ).strip().lower()
    if configured in {ProviderTransport.JSON_SCHEMA.value, ProviderTransport.JSON_OBJECT.value}:
        return ProviderTransport(configured)
    if state.get("provider_json_schema"):
        return ProviderTransport.JSON_SCHEMA
    return ProviderTransport.JSON_OBJECT
