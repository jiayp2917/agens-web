"""Writer Agent — StateGraph assembly.

This is the core of the learning example. Five LangGraph concepts are
exercised here:
  1. ``StateGraph``   — the graph container
  2. ``Node``         — the 4 functions in nodes.py
  3. ``State``        — the WriterState TypedDict (imported via state_schema)
  4. ``Edge``         — the 4 plain edges
  5. ``Checkpoint``   — the optional SqliteSaver

The compiled graph is the single object that the CLI invokes.
"""

from __future__ import annotations

import logging
from typing import Any

from langgraph.graph import END, START, StateGraph
from langgraph.checkpoint.memory import MemorySaver

from ...state.schema import WriterState
from .nodes import (
    AGENT_NAME,
    build_prompt,
    call_agnes_llm,
    load_settings,
    save_artifact,
)

log = logging.getLogger(__name__)


def build_writer_graph() -> Any:
    """Construct and compile the Writer Agent state graph.

    Returns a ``CompiledStateGraph`` that can be invoked with an initial state.
    """
    # 1. StateGraph: container that knows the shape of state.
    g = StateGraph(WriterState)

    # 2. Nodes: register each function under a name.
    g.add_node("load_settings", load_settings)
    g.add_node("build_prompt", build_prompt)
    g.add_node("call_agnes_llm", call_agnes_llm)
    g.add_node("save_artifact", save_artifact)

    # 3+4. Edges: wire START -> load_settings -> ... -> END.
    g.add_edge(START, "load_settings")
    g.add_edge("load_settings", "build_prompt")
    g.add_edge("build_prompt", "call_agnes_llm")
    g.add_edge("call_agnes_llm", "save_artifact")
    g.add_edge("save_artifact", END)

    # 5. Checkpoint: in-memory for v1; SqliteSaver can be swapped in tests.
    checkpointer = MemorySaver()

    return g.compile(checkpointer=checkpointer)


# LangGraph's compiled graph cannot have async node functions without an
# explicit async checkpointer config. We expose a tiny async runner for tests
# that want to exercise the LLM call directly.
async def ainvoke_writer_graph(initial: dict[str, Any], thread_id: str) -> dict[str, Any]:
    """Async invoke — used by tests that want to assert on the LLM node output."""
    graph = build_writer_graph()
    config = {"configurable": {"thread_id": thread_id}}
    result = await graph.ainvoke(initial, config=config)
    return result
