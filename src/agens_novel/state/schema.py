"""WriterState — TypedDict state for the Writer Agent.

This is intentionally simple. As the user learns LangGraph, fields can
be added one at a time. The current shape covers the four-node flow:
  load_settings -> build_prompt -> call_agnes_llm -> save_artifact.
"""

from __future__ import annotations

from typing import TypedDict

from .reducers import Append


class WriterState(TypedDict, total=False):
    # ---- Inputs ----
    user_input: str            # The user's writing request (e.g. "写一段...")
    style_hint: str            # Optional style override
    thread_id: str             # LangGraph thread id for checkpointing

    # ---- Loaded by load_settings node ----
    model: str                 # Resolved model name
    base_url: str              # Resolved base URL
    api_key_set: bool          # Whether AGNES_API_KEY is set (never store the value!)
    run_id: str                # UUID for this run
    started_at: str            # ISO-8601 UTC

    # ---- Built by build_prompt node ----
    system_message: str        # Loaded from config/prompts/system/writer.md
    user_message: str          # Assembled user message
    messages: Append           # Final messages list (uses add reducer)

    # ---- LLM response ----
    output_text: str           # LLM-generated prose
    usage: dict                # {prompt_tokens, completion_tokens, total_tokens}
    elapsed_ms: int            # Wall-clock time for the LLM call
    llm_error: str             # Populated if the LLM call failed

    # ---- Output by save_artifact ----
    output_path: str           # Path to runtime/artifacts/writer/<run-id>/output.md
    audit_path: str            # Path to audit.json
    finished_at: str           # ISO-8601 UTC
