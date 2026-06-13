"""Turn runner -- executes a single agent invocation synchronously.

Replaces the old ``stage_runner.py`` with a simpler interface for the game loop.
Supports stream_callback parameter for real-time narrative streaming.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any, Callable

from .game_session import GameSession

log = logging.getLogger(__name__)

# Agent module registry.
_MODULES = {
    "narrator": "agens_novel.agents.narrator",
    "world_builder": "agens_novel.agents.world_builder",
    "judge": "agens_novel.agents.judge",
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
        agent_name: Which agent to invoke ("narrator", "judge", "world_builder").
        user_input: The player's action text.
        session: Current GameSession.
        **kwargs: Extra state fields.  Supports:
            stream_callback: Callable[[str], None] — per-chunk callback for
                             streaming narrative (narrator only).
            narrative: str — for judge agent.
            state_delta: dict — for judge agent.
            generation_type: str — for world_builder agent.
    """
    import os

    # Extract stream_callback before building state (not serializable for LangGraph).
    stream_callback: Callable[[str], None] | None = kwargs.pop("stream_callback", None)

    state: dict[str, Any] = {
        "user_input": user_input,
        "game_state_json": json.dumps(session.as_game_state(), ensure_ascii=False),
        "thread_id": kwargs.pop("thread_id", None) or f"turn-{uuid.uuid4().hex[:8]}",
        "model": os.environ.get("AGNES_MODEL", "agnes-2.0-flash"),
        "base_url": os.environ.get("AGNES_BASE_URL", "https://apihub.agnes-ai.com/v1"),
        "api_key_set": bool(os.environ.get("AGNES_API_KEY", "")),
    }

    # Pass chat history for narrator.
    if agent_name == "narrator" and session.chat_history:
        state["chat_history"] = list(session.chat_history)

    # Judge needs additional context.
    if agent_name == "judge":
        state["narrative"] = kwargs.get("narrative", "")
        state["state_delta"] = kwargs.get("state_delta", {})

    # World builder needs generation type.
    if agent_name == "world_builder":
        state["generation_type"] = kwargs.get("generation_type", "new_game")

    # Stream callback for narrator — passed via closure, NOT in state dict.
    # Putting it in state causes msgpack serialization failure at checkpoint.
    state.update(kwargs)
    return _run_agent_graph(agent_name, state, stream_callback=stream_callback)
