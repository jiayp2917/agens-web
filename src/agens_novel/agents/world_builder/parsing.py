"""World Builder output parsing and recursive safety filtering."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from ...engine.world_generator import is_complete_opening_payload
from ..common import normalize_choices
from ..contracts import WorldOpeningEnvelopeV1

log = logging.getLogger(__name__)

_TAG_RE = re.compile(r"<world_data>(.*?)</world_data>", re.DOTALL)
_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


def _parse_schema_world_output(
    text: str,
    *,
    profile_opening: bool = False,
) -> tuple[dict, str, str]:
    try:
        data = json.loads(str(text or ""))
    except (json.JSONDecodeError, TypeError, ValueError):
        return {}, "", ""
    if not isinstance(data, dict):
        return {}, "", ""
    generated_data = _sanitize_world_data(data)
    generated_data["choices"] = normalize_choices(generated_data.get("choices"))
    envelope = WorldOpeningEnvelopeV1.from_payload(generated_data)
    if profile_opening:
        if envelope is None or not 3 <= len(envelope.chronicle_0_16) <= 5:
            return {}, "", ""
        opening_data = {
            "opening_narrative": envelope.opening_narrative,
            "chronicle_0_16": list(envelope.chronicle_0_16),
            "initial_situation_16": envelope.initial_situation_16,
            "choices": list(envelope.choices),
        }
        return opening_data, "", envelope.opening_narrative
    if not is_complete_opening_payload(generated_data):
        return {}, "", ""
    return generated_data, "", str(generated_data.get("opening_narrative") or "")


def _parse_world_output(text: str) -> tuple[dict, str, str]:
    """Extract (generated_data, world_description, opening_narrative) from output."""
    generated_data: dict = {}
    world_description = text
    opening_narrative = ""

    raw_json = ""
    m = _TAG_RE.search(text)
    if m:
        world_description = text[: m.start()].strip()
        raw_json = m.group(1).strip()
    else:
        fence = _JSON_FENCE_RE.search(text)
        if fence:
            world_description = text[: fence.start()].strip()
            raw_json = fence.group(1).strip()
        elif text.strip().startswith("{") and text.strip().endswith("}"):
            world_description = ""
            raw_json = text.strip()

    if raw_json:
        try:
            data = json.loads(_strip_json_fence(raw_json))
            if isinstance(data, dict):
                generated_data = _sanitize_world_data(data)
                opening_narrative = str(data.get("opening_narrative") or "")
                generated_data["choices"] = normalize_choices(generated_data.get("choices"))
        except (json.JSONDecodeError, ValueError):
            log.warning("[world_builder] world_data JSON parse failed: %s", raw_json[:200])

    return generated_data, world_description, opening_narrative


def _strip_json_fence(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned.strip()


def _sanitize_world_data(data: dict[str, Any]) -> dict[str, Any]:
    blocked = {
        "llm_error",
        "_error",
        "error",
        "traceback",
        "raw_prompt",
        "state_delta",
        "api_key",
        "authorization",
    }
    sanitized: dict[str, Any] = {}
    for key, value in data.items():
        if str(key).lower() in blocked:
            continue
        if isinstance(value, dict):
            sanitized[key] = _sanitize_world_data(value)
        elif isinstance(value, list):
            sanitized[key] = [
                _sanitize_world_data(item) if isinstance(item, dict) else item for item in value
            ]
        else:
            sanitized[key] = value
    return sanitized
