"""Turn runner -- executes a single agent invocation synchronously.

Replaces the old ``stage_runner.py`` with a simpler interface for the game loop.
Supports stream_callback parameter for real-time narrative streaming.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections.abc import Callable
from typing import Any

from agens_novel.settings import Settings

from ..llm.runtime_context import RuntimeModelConfig, model_runtime
from ..session.game_session import GameSession

log = logging.getLogger(__name__)

# Agent module registry.
_MODULES = {
    "narrator": "agens_novel.agents.narrator",
    "world_builder": "agens_novel.agents.world_builder",
}


def _run_agent_graph(
    agent_name: str,
    initial_state: dict[str, Any],
    stream_callback: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Build and invoke an agent graph synchronously."""
    import importlib

    module = importlib.import_module(_MODULES[agent_name])
    # Convention: each agent module exports build_<agent>_graph()
    graph_fn = getattr(module, f"build_{agent_name}_graph")
    graph = graph_fn()

    thread_id = initial_state.get("thread_id") or f"{agent_name}-{uuid.uuid4().hex[:8]}"
    config = {"configurable": {"thread_id": thread_id}}

    # If a stream callback is needed, pass it via a thread-local so the
    # narrator node can access it without it being in the serialized state.
    if stream_callback is not None and agent_name == "narrator":
        from . import _stream_context
        _stream_context.set(stream_callback)
        try:
            result = asyncio.run(graph.ainvoke(initial_state, config=config))
        finally:
            _stream_context.set(None)
        return result

    return asyncio.run(graph.ainvoke(initial_state, config=config))


def run_turn_sync(
    agent_name: str,
    user_input: str,
    session: GameSession,
    **kwargs: Any,
) -> dict[str, Any]:
    """Run a single agent turn synchronously and return the full result dict.

    Args:
        agent_name: Which agent to invoke ("narrator", "world_builder").
        user_input: The player's action text.
        session: Current GameSession.
        **kwargs: Extra state fields.  Supports:
            stream_callback: Callable[[str], None] — per-chunk callback for
                             streaming narrative (narrator only).
            generation_type: str — for world_builder agent.
    """
    import os

    # Extract stream_callback before building the data-only agent state.
    stream_callback: Callable[[str], None] | None = kwargs.pop("stream_callback", None)

    model = str(kwargs.pop("model", None) or os.environ.get("AGNES_MODEL", Settings().model))
    base_url = str(
        kwargs.pop("base_url", None) or os.environ.get("AGNES_BASE_URL", Settings().base_url)
    )
    api_key = str(kwargs.pop("api_key", None) or os.environ.get("AGNES_API_KEY", ""))
    runtime = RuntimeModelConfig(
        provider=str(kwargs.pop("provider", None) or "Agens"),
        model=model,
        base_url=base_url,
        api_key=api_key,
        source=str(kwargs.pop("source", None) or "env"),
        key_error=str(kwargs.pop("key_error", None) or ""),
    )
    state: dict[str, Any] = {
        "user_input": user_input,
        "game_state_json": json.dumps(session.as_game_state(), ensure_ascii=False),
        "thread_id": kwargs.pop("thread_id", None) or f"turn-{uuid.uuid4().hex[:8]}",
        "model": runtime.model,
        "base_url": runtime.base_url,
        "provider": runtime.provider,
        "api_key_set": runtime.api_key_set,
    }

    # Pass chat history for narrator.
    if agent_name == "narrator" and session.chat_history:
        state["chat_history"] = list(session.chat_history)
    if agent_name == "narrator":
        state["repair_incomplete_output"] = bool(kwargs.pop("repair_incomplete_output", False))

    # World builder needs generation type.
    if agent_name == "world_builder":
        state["generation_type"] = kwargs.get("generation_type", "new_game")

    # Stream callback for narrator — passed via closure, NOT in state dict.
    # Putting it in state causes msgpack serialization failure at checkpoint.
    state.update(kwargs)
    with model_runtime(runtime):
        return _run_agent_graph(agent_name, state, stream_callback=stream_callback)

