"""ChatState -- TypedDict for the Chat Agent (conversational mode)."""

from __future__ import annotations

from typing import TypedDict

from .reducers import Append


class ChatState(TypedDict, total=False):
    # ---- Inputs ----
    user_input: str              # The user's free-form text
    thread_id: str
    chat_history: Append         # Multi-turn history: list of {role, content}

    # ---- Run metadata ----
    run_id: str
    started_at: str
    model: str
    base_url: str
    api_key_set: bool

    # ---- Built by build_prompt ----
    system_message: str
    user_message: str
    messages: Append             # Full messages list for the LLM call

    # ---- LLM response ----
    output_text: str
    usage: dict
    elapsed_ms: int
    llm_error: str

    # ---- Output ----
    output_path: str
    audit_path: str
    finished_at: str
