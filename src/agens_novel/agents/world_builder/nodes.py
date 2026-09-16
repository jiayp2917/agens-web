"""World Builder Agent node functions.

Generates initial character state, starting world, and new content on demand.
Output is wrapped in ``<world_data>`` tags containing structured JSON.

4-node pattern: load_settings → build_prompt → call_agnes_llm → save_artifact
"""

from __future__ import annotations

from typing import Any

from ...llm.provider_adapter import ProviderTransport, world_opening_transport
from ...llm.provider_adapter import (
    response_format as provider_response_format,
)
from ...utils.timing import utcnow_iso
from ..common import call_agnes_llm_common, load_agent_settings
from ..contracts import WorldOpeningEnvelopeV1
from .parsing import _parse_schema_world_output, _parse_world_output
from .prompting import build_prompt as build_prompt

AGENT_NAME = "world_builder"
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

_PROFILE_OPENING_RESPONSE_FORMAT: dict[str, Any] = {
    "type": "json_schema",
    "json_schema": {
        "name": "profile_opening",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "chronicle_0_16": {
                    "type": "array",
                    "minItems": 3,
                    "maxItems": 5,
                    "items": {"type": "string", "minLength": 1},
                },
                "initial_situation_16": {"type": "string", "minLength": 1},
                "opening_narrative": {"type": "string", "minLength": 1},
                "choices": {
                    "type": "array",
                    "minItems": 4,
                    "maxItems": 4,
                    "items": {"type": "string", "minLength": 4},
                },
            },
            "required": [
                "chronicle_0_16",
                "initial_situation_16",
                "opening_narrative",
                "choices",
            ],
            "additionalProperties": False,
        },
    },
}


def load_settings(state: dict[str, Any]) -> dict[str, Any]:
    return load_agent_settings(AGENT_NAME, state)


async def call_agnes_llm(state: dict[str, Any]) -> dict[str, Any]:
    transport = _world_transport(state)
    response_schema = (
        _PROFILE_OPENING_RESPONSE_FORMAT
        if state.get("generation_type") == "profile_opening"
        else _WORLD_BUILDER_RESPONSE_FORMAT
    )
    result = await call_agnes_llm_common(
        state,
        agent_name=AGENT_NAME,
        temperature=0.6,
        max_tokens=4096,
        response_format=provider_response_format(transport, response_schema),
    )
    result["provider_transport"] = transport.value
    result["provider_json_schema"] = transport == ProviderTransport.JSON_SCHEMA
    return result


def save_artifact(state: dict[str, Any]) -> dict[str, Any]:
    """Parse the World Opening envelope without persisting provider output."""
    text = state.get("output_text", "")
    llm_error = state.get("llm_error", "")
    generation_type = str(state.get("generation_type") or "new_game")
    provider_transport = str(state.get("provider_transport") or "json_object")
    provider_structured = provider_transport in {"json_schema", "json_object"} or bool(
        state.get("provider_json_schema")
    )

    if llm_error:
        generated_data: dict[str, Any] = {}
        world_description = ""
        opening_narrative = ""
    else:
        if provider_structured:
            generated_data, world_description, opening_narrative = _parse_schema_world_output(
                text,
                profile_opening=generation_type == "profile_opening",
            )
        else:
            generated_data, world_description, opening_narrative = _parse_world_output(text)

    envelope = WorldOpeningEnvelopeV1.from_payload(generated_data)
    return {
        "generated_data": generated_data,
        "world_description": world_description,
        "opening_narrative": opening_narrative,
        "output_path": "",
        "audit_path": "",
        "finished_at": utcnow_iso(),
        "provider_transport": provider_transport,
        "provider_json_schema": bool(state.get("provider_json_schema")),
        "provider_json_object": bool(state.get("provider_json_object")),
        "provider_json_envelope_ok": bool(envelope) if provider_structured else False,
        "llm_error_code": str(state.get("llm_error_code") or ""),
        "response_diagnostics": dict(state.get("response_diagnostics") or {}),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _world_transport(state: dict[str, Any]) -> ProviderTransport:
    return world_opening_transport(state)
