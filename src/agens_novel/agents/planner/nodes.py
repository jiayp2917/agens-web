"""Planner Agent node functions.

Single-node agent: load_settings → build_prompt → call_agnes_llm → save_artifact.
The Planner's only job is to convert a free-form ``user_request`` into a
structured outline that the downstream Writer Agent can use as scaffolding.
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

AGENT_NAME = "planner"


def load_settings(state: dict[str, Any]) -> dict[str, Any]:
    base_url = os.environ.get("AGNES_BASE_URL", "https://apihub.agnes-ai.com/v1")
    model = os.environ.get("AGNES_MODEL", "agnes-2.0-flash")
    api_key = os.environ.get("AGNES_API_KEY", "")
    run_id = store.new_run_id()
    log.info(
        "[planner.load_settings] run_id=%s model=%s api_key=%s",
        run_id, model, mask(api_key),
    )
    return {
        "model": model,
        "base_url": base_url,
        "api_key_set": bool(api_key),
        "run_id": run_id,
        "started_at": utcnow_iso(),
    }


def build_prompt(state: dict[str, Any]) -> dict[str, Any]:
    system_path = paths.system_prompt_path("planner")
    if not system_path.exists():
        raise FileNotFoundError(f"System prompt not found: {system_path}")
    system_message = system_path.read_text(encoding="utf-8").strip()

    user_request = state.get("user_request", "").strip()
    if not user_request:
        raise ValueError("user_request is required.")

    style_hint = state.get("style_hint", "").strip()
    user_message = user_request if not style_hint else f"{user_request}\n\n[风格提示] {style_hint}"

    log.info("[planner.build_prompt] system=%d user=%d", len(system_message), len(user_message))
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
        return {"output_text": "", "llm_error": "AGNES_API_KEY env var is not set.", "elapsed_ms": 0, "usage": {}}
    messages: list[Message] = state.get("messages") or []
    if not messages:
        return {"output_text": "", "llm_error": "messages list is empty.", "elapsed_ms": 0, "usage": {}}
    try:
        resp = await call_llm(
            messages,
            model=state.get("model"),
            base_url=state.get("base_url"),
            temperature=0.5,
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
        log.error("[planner.call_agnes_llm] failed: %s", e)
        return {"output_text": "", "llm_error": str(e), "elapsed_ms": 0, "usage": {}}


def save_artifact(state: dict[str, Any]) -> dict[str, Any]:
    """Parse the LLM output into structured outline + plan_notes, then persist."""
    run_id = state.get("run_id") or store.new_run_id()
    text = state.get("output_text", "")
    llm_error = state.get("llm_error", "")

    outline, plan_notes = _parse_plan_output(text) if not llm_error else ("", "")

    if llm_error:
        out_text = f"[error] LLM call failed: {llm_error}\n"
    else:
        out_text = text

    out_path = store.write_output(AGENT_NAME, run_id, out_text)
    store.write_input_snapshot(
        AGENT_NAME, run_id,
        {"user_request": state.get("user_request"), "style_hint": state.get("style_hint"),
         "model": state.get("model"), "thread_id": state.get("thread_id")},
    )
    audit = {
        "run_id": run_id, "agent": AGENT_NAME,
        "started_at": state.get("started_at"), "finished_at": utcnow_iso(),
        "model": state.get("model"), "usage": state.get("usage", {}),
        "elapsed_ms": state.get("elapsed_ms", 0), "llm_error": llm_error,
        "output_path": str(out_path),
        "outline_chars": len(outline),
        "plan_notes_chars": len(plan_notes),
    }
    audit_path = store.write_audit(AGENT_NAME, run_id, audit)
    store.append_global_log({"event": "planner_run_finished", "run_id": run_id, "ok": not llm_error})

    log.info(
        "[planner.save_artifact] run_id=%s outline=%d chars plan_notes=%d chars",
        run_id, len(outline), len(plan_notes),
    )
    return {
        "outline": outline,
        "plan_notes": plan_notes,
        "output_path": str(out_path),
        "audit_path": str(audit_path),
        "finished_at": audit["finished_at"],
    }


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────
def _parse_plan_output(text: str) -> tuple[str, str]:
    """Split the planner's free-form text into ``(outline, plan_notes)``.

    Heuristic: any line that starts with ``·`` (or ``-`` / ``*``) is an outline
    bullet. The first line not starting with such a marker, or any line
    containing ``plan_notes:`` is treated as plan_notes.

    The ``plan_notes:`` header line is consumed once; subsequent lines go to
    outline (if bullet) or notes (if prose) regardless of any prior state.
    """
    outline_lines: list[str] = []
    notes_lines: list[str] = []
    consumed_header = False
    for raw in text.splitlines():
        line = raw.rstrip()
        if not line:
            continue
        stripped = line.lstrip()
        if not consumed_header and stripped.lower().startswith("plan_notes:"):
            notes_lines.append(stripped.split(":", 1)[1].strip())
            consumed_header = True
            continue
        if stripped[:1] in {"·", "•", "-", "*"}:
            outline_lines.append(stripped)
        else:
            # Any other non-bullet prose becomes plan_notes context.
            notes_lines.append(stripped)
    outline = "\n".join(outline_lines).strip()
    plan_notes = " ".join(notes_lines).strip()
    # Fallback: if parsing produced nothing useful, keep the whole text as outline.
    if not outline and not plan_notes and text.strip():
        return text.strip(), ""
    return outline, plan_notes
