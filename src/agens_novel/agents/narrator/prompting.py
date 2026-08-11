"""Narrator prompt construction and bounded history rendering."""

from __future__ import annotations

import json
import logging
from typing import Any

from ... import paths
from ...engine.history import render_history_entry
from ...llm.provider_adapter import ProviderTransport, narrator_transport
from ...llm.types import Message
from ..common import prompt_metrics as _prompt_metrics
from .parsing import _schema_safe_history

log = logging.getLogger(__name__)

_RECENT_HISTORY_MESSAGES = 6
# Prompt soft cap stays below the storage cap so the narrator prompt remains bounded.
_HISTORY_PROMPT_SOFT_CAP = _RECENT_HISTORY_MESSAGES + 1
_PROMPT_ROOT_FIELDS = ("turn_count", "realm_turn_count", "game_over", "finale")
_PROMPT_CHARACTER_FIELDS = (
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
    "titles",
    "relationships",
    "status_effects",
    "lifespan",
    "remaining_lifespan",
)
_PROMPT_WORLD_FIELDS = ("current_scene", "location", "region", "story_key", "story_version")
_PROMPT_WORLD_RECENT_FIELDS = ("active_quests", "discovered_locations", "lore_facts")
_PROMPT_PROFILE_FIELDS = ("world_key", "world_name", "fate_hooks")

def build_prompt(state: dict[str, Any]) -> dict[str, Any]:
    transport = narrator_transport(state)
    provider_json_schema = transport == ProviderTransport.JSON_SCHEMA
    provider_json_object = transport == ProviderTransport.JSON_OBJECT
    provider_structured = provider_json_schema or provider_json_object
    prompt_name = "narrator_schema" if provider_structured else "narrator"
    system_path = paths.system_prompt_path(prompt_name)
    if not system_path.exists():
        raise FileNotFoundError(f"System prompt not found: {system_path}")
    system_message = system_path.read_text(encoding="utf-8").strip()

    user_input = state.get("user_input", "").strip()
    if not user_input:
        raise ValueError("user_input is required.")

    game_state_json = _narrator_state_for_prompt(state.get("game_state_json", "{}"))

    # Build messages: system + compact chat history + current turn.
    history: list[dict] = list(state.get("chat_history") or [])
    prompt_history = _compact_history_for_prompt(history)
    if provider_structured:
        prompt_history = _schema_safe_history(prompt_history)

    if provider_json_schema or provider_json_object:
        output_contract = (
            "必须返回 narrative 和 choices 两个字段；"
            "narrative 必须是 80-140 个中文字符的第三人称编年史，"
            "choices 必须恰好四项、非空且互不重复，并依次对应稳妥、机遇、风险、气运。"
            "narrative 和 choices 只能使用中文，不得含任何英文字母、英文缩写或拉丁字母。"
            "发现英文时必须在输出前改写为中文或省略该句。"
            "任何字段都不得包含标签、Markdown 或额外包装。"
        )
    else:
        output_contract = (
            "响应必须以 80-140 个中文字符的第三人称编年史正文开头，第一个字符不得是 <、{、[；随后输出恰好四项的 "
            "<choices>[\"...\", \"...\", \"...\", \"...\"]</choices>；"
            "choices 标签不得省略。叙事正文和四个选项只能使用中文，"
            "不得含任何英文字母、英文缩写或拉丁字母；发现英文时必须改写为中文或省略。"
        )
    user_content = (
        f"<当前状态>\n{game_state_json}\n</当前状态>\n\n"
        f"<玩家行动>\n{user_input}\n</玩家行动>\n\n"
        f"<本回合输出契约>\n{output_contract}\n</本回合输出契约>"
    )

    messages: list[Message] = [Message(role="system", content=system_message)]
    for entry in prompt_history:
        messages.append(Message(
            role=entry.get("role", "user"),
            content=render_history_entry(entry),
        ))
    messages.append(Message(role="user", content=user_content))

    prompt_metrics = _prompt_metrics(
        messages,
        game_state_json=game_state_json,
        history_count=len(history),
        user_input=user_input,
    )

    log.info(
        "[narrator.build_prompt] history=%d user=%d prompt_chars=%d",
        len(history),
        len(user_input),
        prompt_metrics["prompt_chars"],
    )
    return {
        "system_message": system_message,
        "user_message": user_content,
        "messages": messages,
        "prompt_metrics": prompt_metrics,
        "provider_json_schema": provider_json_schema,
        "provider_json_object": provider_json_object,
        "provider_transport": transport.value,
    }

def _compact_history_for_prompt(history: list[dict]) -> list[dict]:
    """Bound the narrator prompt: opening + summary stub + recent turns.

    Storage (``record_turn``) keeps up to 20 entries; the prompt compresses once
    ``chat_history`` exceeds the soft cap so narrator output quality does not
    degrade as the conversation grows. The opening entry (world setup from
    ``record_opening_context``) is preserved, the recent window is kept verbatim
    for continuity, and the collapsed middle is signalled by a stub.
    """
    if len(history) <= _HISTORY_PROMPT_SOFT_CAP:
        return history

    first = history[0]
    recent = history[-_RECENT_HISTORY_MESSAGES:]
    omitted = max(0, len(history) - len(recent) - 1)
    compacted = [
        {
            "role": "assistant",
            "content": (
                "前情摘要：本局开场和角色设定仍以当前状态 JSON 为准；"
                f"中间已有 {omitted} 条历史对话省略。"
            ),
        }
    ]
    if isinstance(first, dict) and first.get("content"):
        compacted.insert(0, {
            "role": first.get("role", "assistant"),
            "content": str(first.get("content", ""))[:1200],
        })
    compacted.extend(recent)
    return compacted


def _narrator_state_for_prompt(value: Any) -> str:
    """Keep rule context while excluding verbose display-only opening data."""
    raw = value if isinstance(value, str) else "{}"
    state = _json_object(raw)
    if state is None:
        return raw

    projected = _project_fields(state, _PROMPT_ROOT_FIELDS)
    if isinstance(state.get("rule_state"), dict):
        projected["rule_state"] = state["rule_state"]

    character = _mapping_or_empty(state.get("character"))
    character_fields = _project_fields(character, _PROMPT_CHARACTER_FIELDS)
    _add_section(projected, "character", character_fields)

    world_fields = _project_world(_mapping_or_empty(state.get("world")))
    if world_fields:
        projected["world"] = world_fields
    if isinstance(state.get("local_story"), dict):
        projected["local_story"] = state["local_story"]
    return json.dumps(projected, ensure_ascii=False, separators=(",", ":"))


def _json_object(raw: str) -> dict[str, Any] | None:
    try:
        value = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _mapping_or_empty(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _project_fields(value: dict[str, Any], fields: tuple[str, ...]) -> dict[str, Any]:
    return {key: value[key] for key in fields if key in value}


def _add_section(target: dict[str, Any], name: str, value: dict[str, Any]) -> None:
    if value:
        target[name] = value


def _project_world(world: dict[str, Any]) -> dict[str, Any]:
    projected = _project_fields(world, _PROMPT_WORLD_FIELDS)
    for key in _PROMPT_WORLD_RECENT_FIELDS:
        if key in world:
            projected[key] = _recent_items(world[key])
    if isinstance(world.get("story_state"), dict):
        projected["story_state"] = world["story_state"]
    profile = _project_fields(_mapping_or_empty(world.get("world_profile")), _PROMPT_PROFILE_FIELDS)
    _add_section(projected, "world_profile", profile)
    return projected


def _recent_items(value: Any) -> list[Any]:
    return list(value[-6:]) if isinstance(value, list) else []
