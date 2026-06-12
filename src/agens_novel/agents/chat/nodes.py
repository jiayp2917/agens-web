"""Chat Agent node functions.

A lightweight conversational agent that responds to free-form user input.
Supports multi-turn context via ``chat_history``.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from ...artifacts import store
from ...llm.client import LLMError, call_llm
from ...llm.types import Message
from ... import paths
from ...utils.secrets import mask
from ...utils.timing import utcnow_iso

log = logging.getLogger(__name__)

AGENT_NAME = "chat"
_MAX_HISTORY_TURNS = 20  # cap at 10 user + 10 assistant messages


def load_settings(state: dict[str, Any]) -> dict[str, Any]:
    base_url = os.environ.get("AGNES_BASE_URL", "https://apihub.agnes-ai.com/v1")
    model = os.environ.get("AGNES_MODEL", "agnes-2.0-flash")
    api_key = os.environ.get("AGNES_API_KEY", "")
    run_id = store.new_run_id()
    log.info("[chat.load_settings] run_id=%s model=%s", run_id, model)
    return {
        "model": model, "base_url": base_url, "api_key_set": bool(api_key),
        "run_id": run_id, "started_at": utcnow_iso(),
    }


def build_prompt(state: dict[str, Any]) -> dict[str, Any]:
    system_path = paths.system_prompt_path("chat")
    if not system_path.exists():
        raise FileNotFoundError(f"System prompt not found: {system_path}")
    system_message = system_path.read_text(encoding="utf-8").strip()

    user_input = state.get("user_input", "").strip()
    if not user_input:
        raise ValueError("user_input is required.")

    # Build messages list: system + chat history + current user message.
    history: list[dict] = list(state.get("chat_history") or [])
    # Cap history to prevent context overflow.
    if len(history) > _MAX_HISTORY_TURNS:
        history = history[-_MAX_HISTORY_TURNS:]

    messages: list[Message] = [Message(role="system", content=system_message)]
    for entry in history:
        messages.append(Message(role=entry.get("role", "user"), content=entry.get("content", "")))
    messages.append(Message(role="user", content=user_input))

    log.info("[chat.build_prompt] history=%d user=%d", len(history), len(user_input))
    return {
        "system_message": system_message,
        "user_message": user_input,
        "messages": messages,
    }


async def call_agnes_llm(state: dict[str, Any]) -> dict[str, Any]:
    if not state.get("api_key_set"):
        return {"output_text": "", "llm_error": "AGNES_API_KEY env var is not set.", "elapsed_ms": 0, "usage": {}}
    messages: list[Message] = state.get("messages") or []
    if not messages:
        return {"output_text": "", "llm_error": "messages list is empty.", "elapsed_ms": 0, "usage": {}}
    try:
        resp = await call_llm(
            messages,
            model=state.get("model"),
            base_url=state.get("base_url"),
            temperature=0.7,
            max_tokens=1024,
            stream=False,
        )
        return {
            "output_text": resp.get("text", ""),
            "usage": dict(resp.get("usage") or {}),
            "elapsed_ms": int(resp.get("elapsed_ms", 0)),
            "llm_error": "",
        }
    except LLMError as e:
        log.error("[chat.call_agnes_llm] failed: %s", e)
        return {"output_text": "", "llm_error": str(e), "elapsed_ms": 0, "usage": {}}


def save_artifact(state: dict[str, Any]) -> dict[str, Any]:
    run_id = state.get("run_id") or store.new_run_id()
    text = state.get("output_text", "")
    llm_error = state.get("llm_error", "")

    if llm_error:
        out_text = f"[error] LLM call failed: {llm_error}\n"
    else:
        out_text = text

    out_path = store.write_output(AGENT_NAME, run_id, out_text)
    store.write_input_snapshot(
        AGENT_NAME, run_id,
        {"user_input": state.get("user_input"), "model": state.get("model"),
         "thread_id": state.get("thread_id")},
    )
    audit = {
        "run_id": run_id, "agent": AGENT_NAME,
        "started_at": state.get("started_at"), "finished_at": utcnow_iso(),
        "model": state.get("model"), "usage": state.get("usage", {}),
        "elapsed_ms": state.get("elapsed_ms", 0), "llm_error": llm_error,
        "output_path": str(out_path),
        "history_turns": len(state.get("chat_history") or []),
        "output_chars": len(text),
    }
    audit_path = store.write_audit(AGENT_NAME, run_id, audit)
    store.append_global_log({"event": "chat_run_finished", "run_id": run_id, "ok": not llm_error})

    return {
        "output_path": str(out_path),
        "audit_path": str(audit_path),
        "finished_at": audit["finished_at"],
    }


def run_chat_agent(user_input: str, chat_history: list[dict] | None = None) -> dict[str, Any]:
    """Sync entry point for the Chat Agent."""
    import asyncio
    from .graph import build_chat_graph
    import uuid

    graph = build_chat_graph()
    initial: dict[str, Any] = {
        "user_input": user_input,
        "chat_history": list(chat_history or []),
        "thread_id": f"chat-{uuid.uuid4().hex[:8]}",
    }
    config = {"configurable": {"thread_id": initial["thread_id"]}}
    return asyncio.run(graph.ainvoke(initial, config=config))
