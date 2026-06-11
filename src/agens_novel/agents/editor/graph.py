"""Editor Agent — StateGraph assembly."""

from __future__ import annotations

from typing import Any

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from ...state.orchestrator_schema import OrchestratorState
from .nodes import build_prompt, call_agnes_llm, load_settings, save_artifact


def build_editor_graph() -> Any:
    g = StateGraph(OrchestratorState)
    g.add_node("load_settings", load_settings)
    g.add_node("build_prompt", build_prompt)
    g.add_node("call_agnes_llm", call_agnes_llm)
    g.add_node("save_artifact", save_artifact)

    g.add_edge(START, "load_settings")
    g.add_edge("load_settings", "build_prompt")
    g.add_edge("build_prompt", "call_agnes_llm")
    g.add_edge("call_agnes_llm", "save_artifact")
    g.add_edge("save_artifact", END)

    return g.compile(checkpointer=MemorySaver())
