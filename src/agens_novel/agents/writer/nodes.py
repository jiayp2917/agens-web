"""Writer Agent node functions.

Each function takes a ``WriterState`` and returns a dict of state updates
to merge. LangGraph merges these updates into the running state, applying
the field-level reducers defined in the TypedDict.

Node layout (4 nodes, linear):
  load_settings -> build_prompt -> call_agnes_llm -> save_artifact
"""

from __future__ import annotations

import logging
import os
import uuid
from typing import Any

from ...artifacts import store
from ...llm.client import LLMError, call_llm
from ...llm.types import Message
from ... import paths
from ...utils.secrets import mask
from ...utils.timing import utcnow_iso

log = logging.getLogger(__name__)

AGENT_NAME = "writer"


# ─────────────────────────────────────────────────────────────────────────────
# Node 1: load_settings
# Read env config, generate run_id, mark started_at.
# ─────────────────────────────────────────────────────────────────────────────
def load_settings(state: dict[str, Any]) -> dict[str, Any]:
    base_url = os.environ.get("AGNES_BASE_URL", "https://apihub.agnes-ai.com/v1")
    model = os.environ.get("AGNES_MODEL", "agnes-2.0-flash")
    api_key = os.environ.get("AGNES_API_KEY", "")
    run_id = store.new_run_id()
    log.info(
        "[load_settings] run_id=%s model=%s base_url=%s api_key=%s",
        run_id, model, base_url, mask(api_key),
    )
    return {
        "base_url": base_url,
        "model": model,
        "api_key_set": bool(api_key),
        "run_id": run_id,
        "started_at": utcnow_iso(),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Node 2: build_prompt
# Load system prompt from disk and assemble the messages list.
# ─────────────────────────────────────────────────────────────────────────────
def build_prompt(state: dict[str, Any]) -> dict[str, Any]:
    system_path = paths.system_prompt_path("writer")
    if not system_path.exists():
        raise FileNotFoundError(
            f"System prompt not found: {system_path}. "
            f"Create config/prompts/system/writer.md first."
        )
    system_message = system_path.read_text(encoding="utf-8").strip()

    user_input = state.get("user_input", "").strip()
    if not user_input:
        raise ValueError("user_input is required (pass --input '...').")

    style_hint = state.get("style_hint", "").strip()
    user_message = user_input if not style_hint else f"{user_input}\n\n[风格提示] {style_hint}"

    log.info(
        "[build_prompt] system_prompt=%d chars user_message=%d chars",
        len(system_message), len(user_message),
    )

    return {
        "system_message": system_message,
        "user_message": user_message,
        "messages": [
            Message(role="system", content=system_message),
            Message(role="user", content=user_message),
        ],
    }


# ─────────────────────────────────────────────────────────────────────────────
# Node 3: call_agnes_llm
# Make a single non-streaming call to the configured LLM endpoint.
# ─────────────────────────────────────────────────────────────────────────────
async def call_agnes_llm(state: dict[str, Any]) -> dict[str, Any]:
    if not state.get("api_key_set"):
        return {
            "output_text": "",
            "llm_error": "AGNES_API_KEY env var is not set.",
            "elapsed_ms": 0,
            "usage": {},
        }
    messages: list[Message] = state.get("messages") or []
    if not messages:
        return {"output_text": "", "llm_error": "messages list is empty.", "elapsed_ms": 0, "usage": {}}

    try:
        resp = await call_llm(
            messages,
            model=state.get("model"),
            base_url=state.get("base_url"),
            temperature=0.7,
            max_tokens=2048,
            stream=False,
        )
        log.info(
            "[call_agnes_llm] model=%s elapsed=%dms tokens=%s",
            resp.get("model"),
            resp.get("elapsed_ms"),
            resp.get("usage"),
        )
        return {
            "output_text": resp.get("text", ""),
            "usage": dict(resp.get("usage") or {}),
            "elapsed_ms": int(resp.get("elapsed_ms", 0)),
            "llm_error": "",
        }
    except LLMError as e:
        log.error("[call_agnes_llm] failed: %s", e)
        return {"output_text": "", "llm_error": str(e), "elapsed_ms": 0, "usage": {}}


# ─────────────────────────────────────────────────────────────────────────────
# Node 4: save_artifact
# Persist the generated prose to runtime/artifacts/writer/<run-id>/.
# ─────────────────────────────────────────────────────────────────────────────
def save_artifact(state: dict[str, Any]) -> dict[str, Any]:
    run_id = state.get("run_id") or store.new_run_id()
    output_text = state.get("output_text", "")
    llm_error = state.get("llm_error", "")

    if llm_error:
        # Still write an audit so failures are inspectable.
        text = f"[error] LLM call failed: {llm_error}\n"
    else:
        text = output_text

    out_path = store.write_output(AGENT_NAME, run_id, text)

    # Persist input.json (echo of inputs minus secrets).
    store.write_input_snapshot(
        AGENT_NAME,
        run_id,
        {
            "user_input": state.get("user_input"),
            "style_hint": state.get("style_hint"),
            "model": state.get("model"),
            "thread_id": state.get("thread_id"),
        },
    )

    audit = {
        "run_id": run_id,
        "agent": AGENT_NAME,
        "started_at": state.get("started_at"),
        "finished_at": utcnow_iso(),
        "model": state.get("model"),
        "usage": state.get("usage", {}),
        "elapsed_ms": state.get("elapsed_ms", 0),
        "llm_error": llm_error,
        "output_path": str(out_path),
        "system_prompt_chars": len(state.get("system_message", "")),
        "user_message_chars": len(state.get("user_message", "")),
        "output_chars": len(output_text),
    }
    audit_path = store.write_audit(AGENT_NAME, run_id, audit)
    store.append_global_log({"event": "writer_run_finished", "run_id": run_id, "ok": not llm_error})

    return {
        "output_path": str(out_path),
        "audit_path": str(audit_path),
        "finished_at": audit["finished_at"],
    }


# ─────────────────────────────────────────────────────────────────────────────
# Convenience entry point used by the CLI.
# ─────────────────────────────────────────────────────────────────────────────
def run_writer_agent(user_input: str, style_hint: str = "", thread_id: str | None = None) -> dict[str, Any]:
    """Run the Writer Agent synchronously.

    The CLI / tests want a sync call, but ``call_agnes_llm`` is async, so we
    drive the graph via ``ainvoke`` from a tiny asyncio event loop.
    """
    import asyncio

    from .graph import build_writer_graph

    graph = build_writer_graph()
    initial: dict[str, Any] = {
        "user_input": user_input,
        "style_hint": style_hint,
        "thread_id": thread_id or f"writer-{uuid.uuid4().hex[:8]}",
    }
    config = {"configurable": {"thread_id": initial["thread_id"]}}

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Already inside an event loop (e.g. inside a notebook).
            return loop.run_until_complete(_ainvoke(graph, initial, config))
    except RuntimeError:
        pass

    return asyncio.run(_ainvoke(graph, initial, config))


async def _ainvoke(graph, initial, config) -> dict[str, Any]:
    return await graph.ainvoke(initial, config=config)
