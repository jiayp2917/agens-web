"""Minimal async runner for linear agent node chains."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any

Node = Callable[[dict[str, Any]], Any]


class SequentialAgentGraph:
    """LangGraph-compatible subset used by the agent pipeline."""

    def __init__(self, nodes: list[Node]) -> None:
        self._nodes = nodes

    async def ainvoke(
        self,
        initial_state: dict[str, Any],
        config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        state = dict(initial_state)
        for node in self._nodes:
            update = node(state)
            if inspect.isawaitable(update):
                update = await update
            if isinstance(update, dict):
                state.update(update)
        return state
