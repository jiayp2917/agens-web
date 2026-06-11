"""Orchestrator state — shared state across the multi-agent pipeline.

Fields flow through the four agent stages:
  plan    →    write    →    review    →    edit    →    publish
"""

from __future__ import annotations

from typing import TypedDict

from .reducers import Append


class OrchestratorState(TypedDict, total=False):
    # ---- Inputs ----
    user_request: str            # Top-level user request (e.g. "写一段都市修仙开头")
    style_hint: str              # Optional style override
    thread_id: str               # LangGraph thread id

    # ---- Run metadata ----
    run_id: str                  # UUID for the orchestrator run
    started_at: str              # ISO-8601 UTC
    finished_at: str
    model: str
    base_url: str
    api_key_set: bool

    # ---- Plan stage output (Planner Agent) ----
    outline: str                 # Bullet-list outline
    plan_notes: str              # Planner's reasoning / metadata

    # ---- Write stage output (Writer Agent) ----
    draft: str                   # First-pass prose

    # ---- Review stage output (Reviewer Agent) ----
    review_passed: bool          # True if reviewer approves
    review_score: int            # 0-10 quality score
    review_feedback: str         # Free-form critique
    review_iterations: int       # How many review cycles used (max 3)

    # ---- Edit stage output (Editor Agent) ----
    final_text: str              # Editor's revised prose

    # ---- Cumulative logs (append reducer) ----
    agent_log: Append            # Ordered list of {agent, action, ts, note}

    # ---- Errors / status ----
    error: str                   # Populated on any agent failure
    output_path: str
    audit_path: str
