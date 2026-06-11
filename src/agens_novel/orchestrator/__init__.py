"""Orchestrator — multi-agent novel production pipeline.

Public entry point: ``build_orchestrator_graph()`` returns a compiled
``StateGraph`` that runs Planner → Writer → Reviewer → Editor with a
conditional feedback loop (Writer <-> Reviewer) capped at 3 iterations.
"""

from .graph import build_orchestrator_graph

__all__ = ["build_orchestrator_graph"]
