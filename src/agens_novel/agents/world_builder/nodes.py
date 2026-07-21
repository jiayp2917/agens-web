"""World Builder Agent node functions.

Generates initial character state, starting world, and new content on demand.
Output is wrapped in ``<world_data>`` tags containing structured JSON.

4-node pattern: load_settings → build_prompt → call_agnes_llm → save_artifact
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

from ... import paths
from ...artifacts import store
from ...engine.world_generator import is_complete_opening_payload
from ...llm.provider_adapter import (
    ProviderTransport,
    world_opening_transport,
)
from ...llm.provider_adapter import (
    response_format as provider_response_format,
)
from ...llm.types import Message
from ...utils.timing import utcnow_iso
from ..common import call_agnes_llm_common, load_agent_settings, normalize_choices
from ..contracts import WorldOpeningEnvelopeV1

log = logging.getLogger(__name__)

AGENT_NAME = "world_builder"
_WORLD_BUILDER_SCHEMA_ENV = "AGENS_WORLD_BUILDER_RESPONSE_SCHEMA"
_WORLD_BUILDER_RESPONSE_FORMAT: dict[str, Any] = {
    "type": "json_schema",
    "json_schema": {
        "name": "world_builder_opening",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "character": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "minLength": 1},
                        "realm": {"type": "string", "minLength": 1},
                        "realm_stage": {"type": "integer", "minimum": 1},
                        "spirit_root": {"type": "string", "minLength": 1},
                        "spirit_root_grade": {"type": "string"},
                        "age": {"type": "integer", "minimum": 1},
                        "talent": {"type": "string", "minLength": 1},
                        "family_background": {"type": "string", "minLength": 1},
                        "difficulty": {"type": "string", "minLength": 1},
                        "attributes": {
                            "type": "object",
                            "properties": {
                                "root_bone": {"type": "integer", "minimum": 0, "maximum": 10},
                                "comprehension": {"type": "integer", "minimum": 0, "maximum": 10},
                                "luck": {"type": "integer", "minimum": 0, "maximum": 10},
                                "willpower": {"type": "integer", "minimum": 0, "maximum": 10},
                                "physique": {"type": "integer", "minimum": 0, "maximum": 10},
                                "soul": {"type": "integer", "minimum": 0, "maximum": 10},
                            },
                            "required": [
                                "root_bone",
                                "comprehension",
                                "luck",
                                "willpower",
                                "physique",
                                "soul",
                            ],
                            "additionalProperties": False,
                        },
                        "breakthrough_flags": {"type": "array", "items": {"type": "string"}},
                        "techniques": {"type": "array", "items": {"type": "object"}},
                        "inventory": {"type": "array", "items": {"type": "object"}},
                        "status_effects": {"type": "array", "items": {"type": "string"}},
                        "lifespan": {"type": "integer", "minimum": 1},
                        "equipment_slots": {
                            "type": ["object", "null"],
                            "additionalProperties": True,
                        },
                    },
                    "required": [
                        "name",
                        "realm",
                        "realm_stage",
                        "spirit_root",
                        "spirit_root_grade",
                        "age",
                        "talent",
                        "family_background",
                        "difficulty",
                        "attributes",
                        "breakthrough_flags",
                        "techniques",
                        "inventory",
                        "status_effects",
                        "lifespan",
                        "equipment_slots",
                    ],
                    "additionalProperties": False,
                },
                "world_name": {"type": "string", "minLength": 1},
                "regions": {
                    "type": "array",
                    "minItems": 1,
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string", "minLength": 1},
                            "description": {"type": "string", "minLength": 1},
                        },
                        "required": ["name", "description"],
                        "additionalProperties": False,
                    },
                },
                "sects": {
                    "type": "array",
                    "minItems": 1,
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string", "minLength": 1},
                            "alignment": {"type": "string", "minLength": 1},
                            "description": {"type": "string", "minLength": 1},
                        },
                        "required": ["name", "alignment", "description"],
                        "additionalProperties": False,
                    },
                },
                "current_conflicts": {
                    "type": "array",
                    "minItems": 1,
                    "items": {"type": "string", "minLength": 1},
                },
                "fate_hooks": {
                    "type": "array",
                    "minItems": 1,
                    "items": {"type": "string", "minLength": 1},
                },
                "chronicle_0_16": {
                    "type": "array",
                    "minItems": 3,
                    "maxItems": 5,
                    "items": {"type": "string", "minLength": 1},
                },
                "initial_situation": {"type": "string", "minLength": 1},
                "initial_situation_16": {"type": "string", "minLength": 1},
                "opening_narrative": {"type": "string", "minLength": 1},
                "choices": {
                    "type": "array",
                    "minItems": 4,
                    "maxItems": 4,
                    "items": {"type": "string", "minLength": 4},
                },
                "world": {
                    "type": "object",
                    "properties": {
                        "current_scene": {"type": "string", "minLength": 1},
                        "location": {"type": "string", "minLength": 1},
                        "region": {"type": "string", "minLength": 1},
                        "npcs_present": {"type": "array", "items": {"type": "object"}},
                        "active_quests": {"type": "array", "items": {"type": "object"}},
                        "discovered_locations": {
                            "type": "array",
                            "minItems": 1,
                            "items": {"type": "string", "minLength": 1},
                        },
                        "lore_facts": {
                            "type": "array",
                            "minItems": 1,
                            "items": {"type": "string", "minLength": 1},
                        },
                        "day_count": {"type": "integer", "minimum": 1},
                    },
                    "required": [
                        "current_scene",
                        "location",
                        "region",
                        "npcs_present",
                        "active_quests",
                        "discovered_locations",
                        "lore_facts",
                        "day_count",
                    ],
                    "additionalProperties": False,
                },
            },
            "required": [
                "character",
                "world_name",
                "regions",
                "sects",
                "current_conflicts",
                "fate_hooks",
                "chronicle_0_16",
                "initial_situation",
                "initial_situation_16",
                "opening_narrative",
                "choices",
                "world",
            ],
            "additionalProperties": False,
        },
    },
}


def load_settings(state: dict[str, Any]) -> dict[str, Any]:
    return load_agent_settings(AGENT_NAME, state)


def build_prompt(state: dict[str, Any]) -> dict[str, Any]:
    transport = world_opening_transport(state)
    provider_structured = transport in {
        ProviderTransport.JSON_SCHEMA,
        ProviderTransport.JSON_OBJECT,
    }
    prompt_name = "world_builder_schema" if provider_structured else "world_builder"
    system_path = paths.system_prompt_path(prompt_name)
    if not system_path.exists():
        raise FileNotFoundError(f"System prompt not found: {system_path}")
    system_message = system_path.read_text(encoding="utf-8").strip()

    user_input = state.get("user_input", "").strip()
    if not user_input:
        raise ValueError("user_input is required.")

    generation_type = state.get("generation_type", "new_game")
    game_state_json = state.get("game_state_json", "")

    parts = [f"<生成类型>{generation_type}</生成类型>"]
    if game_state_json:
        parts.append(f"<当前状态>\n{game_state_json}\n</当前状态>")
    parts.append(f"<玩家输入>\n{user_input}\n</玩家输入>")

    user_content = "\n\n".join(parts)

    messages: list[Message] = [
        Message(role="system", content=system_message),
        Message(role="user", content=user_content),
    ]

    log.info("[world_builder.build_prompt] type=%s user=%d", generation_type, len(user_input))
    return {
        "system_message": system_message,
        "user_message": user_content,
        "messages": messages,
        "provider_transport": transport.value,
        "provider_json_schema": transport == ProviderTransport.JSON_SCHEMA,
        "provider_json_object": transport == ProviderTransport.JSON_OBJECT,
    }


async def call_agnes_llm(state: dict[str, Any]) -> dict[str, Any]:
    transport = _world_transport(state)
    result = await call_agnes_llm_common(
        state,
        agent_name=AGENT_NAME,
        temperature=0.6,
        max_tokens=4096,
        response_format=provider_response_format(transport, _WORLD_BUILDER_RESPONSE_FORMAT),
    )
    result["provider_transport"] = transport.value
    result["provider_json_schema"] = transport == ProviderTransport.JSON_SCHEMA
    return result


def save_artifact(state: dict[str, Any]) -> dict[str, Any]:
    """Parse <world_data> JSON from the LLM output and persist."""
    run_id = state.get("run_id") or store.new_run_id()
    text = state.get("output_text", "")
    llm_error = state.get("llm_error", "")

    if llm_error:
        generated_data: dict[str, Any] = {}
        world_description = ""
        opening_narrative = ""
    else:
        transport = str(state.get("provider_transport") or "")
        provider_structured = transport in {"json_schema", "json_object"} or bool(
            state.get("provider_json_schema")
        )
        if provider_structured:
            generated_data, world_description, opening_narrative = _parse_schema_world_output(text)
        else:
            generated_data, world_description, opening_narrative = _parse_world_output(text)

    out_path = store.write_output(AGENT_NAME, run_id, text)
    store.write_input_snapshot(
        AGENT_NAME,
        run_id,
        {
            "user_input": state.get("user_input"),
            "generation_type": state.get("generation_type"),
            "model": state.get("model"),
        },
    )
    audit = {
        "run_id": run_id,
        "agent": AGENT_NAME,
        "started_at": state.get("started_at"),
        "finished_at": utcnow_iso(),
        "model": state.get("model"),
        "usage": state.get("usage", {}),
        "elapsed_ms": state.get("elapsed_ms", 0),
        "llm_error": llm_error,
        "output_path": str(out_path),
        "generation_type": state.get("generation_type", "new_game"),
    }
    audit_path = store.write_audit(AGENT_NAME, run_id, audit)
    store.append_global_log(
        {
            "event": "world_builder_run_finished",
            "run_id": run_id,
            "ok": not llm_error,
            "type": state.get("generation_type", "new_game"),
        }
    )

    provider_structured = str(state.get("provider_transport") or "") in {
        "json_schema",
        "json_object",
    } or bool(state.get("provider_json_schema"))
    envelope = WorldOpeningEnvelopeV1.from_payload(generated_data)
    return {
        "generated_data": generated_data,
        "world_description": world_description,
        "opening_narrative": opening_narrative,
        "output_path": str(out_path),
        "audit_path": str(audit_path),
        "finished_at": audit["finished_at"],
        "provider_transport": str(state.get("provider_transport") or "legacy_tags"),
        "provider_json_schema": bool(state.get("provider_json_schema")),
        "provider_json_envelope_ok": bool(envelope) if provider_structured else False,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

_TAG_RE = re.compile(r"<world_data>(.*?)</world_data>", re.DOTALL)
_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


def _should_use_world_builder_schema(state: dict[str, Any]) -> bool:
    configured = os.environ.get(_WORLD_BUILDER_SCHEMA_ENV, "auto").strip().lower()
    if configured in {"1", "true", "yes", "on"}:
        return True
    if configured in {"0", "false", "no", "off"}:
        return False
    model = str(state.get("model") or os.environ.get("AGNES_MODEL") or "").strip().lower()
    return model.startswith("agnes-")


def _world_transport(state: dict[str, Any]) -> ProviderTransport:
    configured = str(state.get("provider_transport") or "").strip()
    if configured:
        return ProviderTransport(configured)
    if state.get("provider_json_schema"):
        return ProviderTransport.JSON_SCHEMA
    return ProviderTransport.LEGACY_TAGS


def _parse_schema_world_output(text: str) -> tuple[dict, str, str]:
    try:
        data = json.loads(str(text or ""))
    except (json.JSONDecodeError, TypeError, ValueError):
        return {}, "", ""
    if not isinstance(data, dict):
        return {}, "", ""
    generated_data = _sanitize_world_data(data)
    generated_data["choices"] = normalize_choices(generated_data.get("choices"))
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
