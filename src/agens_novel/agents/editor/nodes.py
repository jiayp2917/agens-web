"""Editor Agent node functions.

Final stage: takes the Writer's draft and the Reviewer's feedback and produces
the polished ``final_text``. If there is no review feedback (e.g. the
orchestrator skipped review), the Editor is a no-op that just copies the
draft.
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

AGENT_NAME = "editor"


def load_settings(state: dict[str, Any]) -> dict[str, Any]:
    base_url = os.environ.get("AGNES_BASE_URL", "https://apihub.agnes-ai.com/v1")
    model = os.environ.get("AGNES_MODEL", "agnes-2.0-flash")
    api_key = os.environ.get("AGNES_API_KEY", "")
    run_id = store.new_run_id()
    log.info("[editor.load_settings] run_id=%s model=%s api_key=%s", run_id, model, mask(api_key))
    return {
        "model": model, "base_url": base_url, "api_key_set": bool(api_key),
        "run_id": run_id, "started_at": utcnow_iso(),
    }


def build_prompt(state: dict[str, Any]) -> dict[str, Any]:
    system_path = paths.system_prompt_path("editor")
    if not system_path.exists():
        raise FileNotFoundError(f"System prompt not found: {system_path}")
    system_message = system_path.read_text(encoding="utf-8").strip()

    draft = state.get("draft", "").strip()
    if not draft:
        raise ValueError("draft is required for editing.")
    feedback = state.get("review_feedback", "").strip() or "ok — no specific feedback."

    user_message = (
        f"[用户原始请求]\n{state.get('user_request', '')}\n\n"
        f"[审稿反馈]\n{feedback}\n\n"
        f"[初稿]\n{draft}"
    )
    log.info("[editor.build_prompt] draft=%d feedback=%d", len(draft), len(feedback))
    return {
        "system_message": system_message,
        "user_message": user_message,
        "messages": [
            Message(role="system", content=system_message),
            Message(role="user", content=user_message),
        ],
    }


async def call_agnes_llm(state: dict[str, Any]) -> dict[str, Any]:
    if not state.get("api_key_set"):
        return {"output_text": state.get("draft", ""), "llm_error": "", "elapsed_ms": 0, "usage": {}}
    messages: list[Message] = state.get("messages") or []
    if not messages:
        return {"output_text": state.get("draft", ""), "llm_error": "messages list is empty.", "elapsed_ms": 0, "usage": {}}
    try:
        resp = await call_llm(
            messages,
            model=state.get("model"),
            base_url=state.get("base_url"),
            temperature=0.4,
            max_tokens=2048,
            stream=False,
        )
        return {
            "output_text": resp.get("text", "") or state.get("draft", ""),
            "usage": dict(resp.get("usage") or {}),
            "elapsed_ms": int(resp.get("elapsed_ms", 0)),
            "llm_error": "",
        }
    except LLMError as e:
        log.error("[editor.call_agnes_llm] failed: %s — falling back to draft", e)
        return {"output_text": state.get("draft", ""), "llm_error": str(e), "elapsed_ms": 0, "usage": {}}


def save_artifact(state: dict[str, Any]) -> dict[str, Any]:
    run_id = state.get("run_id") or store.new_run_id()
    final_text = state.get("output_text", "") or state.get("draft", "")
    llm_error = state.get("llm_error", "")

    out_path = store.write_output(AGENT_NAME, run_id, final_text)
    store.write_input_snapshot(
        AGENT_NAME, run_id,
        {"draft_chars": len(state.get("draft", "")),
         "review_feedback": state.get("review_feedback", ""),
         "thread_id": state.get("thread_id")},
    )
    audit = {
        "run_id": run_id, "agent": AGENT_NAME,
        "started_at": state.get("started_at"), "finished_at": utcnow_iso(),
        "model": state.get("model"), "usage": state.get("usage", {}),
        "elapsed_ms": state.get("elapsed_ms", 0), "llm_error": llm_error,
        "output_path": str(out_path),
        "final_chars": len(final_text),
    }
    audit_path = store.write_audit(AGENT_NAME, run_id, audit)
    store.append_global_log({"event": "editor_run_finished", "run_id": run_id, "ok": True})

    log.info("[editor.save_artifact] run_id=%s final=%d chars", run_id, len(final_text))
    return {
        "final_text": final_text,
        "output_path": str(out_path),
        "audit_path": str(audit_path),
        "finished_at": audit["finished_at"],
    }
