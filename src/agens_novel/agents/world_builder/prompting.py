"""World Builder prompt construction for new games and profile openings."""

from __future__ import annotations

import logging
from typing import Any

from ... import paths
from ...llm.provider_adapter import ProviderTransport, world_opening_transport
from ...llm.types import Message

log = logging.getLogger(__name__)

def build_prompt(state: dict[str, Any]) -> dict[str, Any]:
    transport = world_opening_transport(state)
    provider_structured = transport in {
        ProviderTransport.JSON_SCHEMA,
        ProviderTransport.JSON_OBJECT,
    }
    generation_type = state.get("generation_type", "new_game")
    prompt_name = (
        "world_opening_schema"
        if provider_structured and generation_type == "profile_opening"
        else "world_builder_schema" if provider_structured else "world_builder"
    )
    system_path = paths.system_prompt_path(prompt_name)
    if not system_path.exists():
        raise FileNotFoundError(f"System prompt not found: {system_path}")
    system_message = system_path.read_text(encoding="utf-8").strip()

    user_input = state.get("user_input", "").strip()
    if not user_input:
        raise ValueError("user_input is required.")

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
