"""Reviewer Agent node functions.

Scores the Writer's draft 0-10 and either approves (passes to Editor) or
rejects (sent back to Writer for another pass). The numeric score and
feedback live in the orchestrator state.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

from ...artifacts import store
from ...llm.client import LLMError, call_llm
from ...llm.types import Message
from ... import paths
from ...utils.secrets import mask
from ...utils.timing import utcnow_iso

log = logging.getLogger(__name__)

AGENT_NAME = "reviewer"


def load_settings(state: dict[str, Any]) -> dict[str, Any]:
    base_url = os.environ.get("AGNES_BASE_URL", "https://apihub.agnes-ai.com/v1")
    model = os.environ.get("AGNES_MODEL", "agnes-2.0-flash")
    api_key = os.environ.get("AGNES_API_KEY", "")
    run_id = store.new_run_id()
    log.info("[reviewer.load_settings] run_id=%s model=%s api_key=%s", run_id, model, mask(api_key))
    return {
        "model": model, "base_url": base_url, "api_key_set": bool(api_key),
        "run_id": run_id, "started_at": utcnow_iso(),
    }


def build_prompt(state: dict[str, Any]) -> dict[str, Any]:
    system_path = paths.system_prompt_path("reviewer")
    if not system_path.exists():
        raise FileNotFoundError(f"System prompt not found: {system_path}")
    system_message = system_path.read_text(encoding="utf-8").strip()

    draft = state.get("draft", "").strip()
    if not draft:
        raise ValueError("draft is required for review.")

    user_message = (
        f"[用户原始请求]\n{state.get('user_request', '')}\n\n"
        f"[大纲]\n{state.get('outline', '')}\n\n"
        f"[初稿]\n{draft}"
    )
    log.info("[reviewer.build_prompt] draft=%d chars", len(draft))
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
            temperature=0.2,
            max_tokens=512,
            stream=False,
        )
        return {
            "output_text": resp.get("text", ""),
            "usage": dict(resp.get("usage") or {}),
            "elapsed_ms": int(resp.get("elapsed_ms", 0)),
            "llm_error": "",
        }
    except LLMError as e:
        log.error("[reviewer.call_agnes_llm] failed: %s", e)
        return {"output_text": "", "llm_error": str(e), "elapsed_ms": 0, "usage": {}}


def save_artifact(state: dict[str, Any]) -> dict[str, Any]:
    """Parse JSON verdict from the LLM and persist the review."""
    run_id = state.get("run_id") or store.new_run_id()
    text = state.get("output_text", "")
    llm_error = state.get("llm_error", "")

    score, passed, feedback = _parse_review_output(text) if not llm_error else (0, False, "")

    if llm_error:
        out_text = f"[error] LLM call failed: {llm_error}\n"
    else:
        out_text = text

    out_path = store.write_output(AGENT_NAME, run_id, out_text)
    store.write_input_snapshot(
        AGENT_NAME, run_id,
        {"draft_chars": len(state.get("draft", "")), "thread_id": state.get("thread_id")},
    )
    iterations = int(state.get("review_iterations", 0)) + 1
    audit = {
        "run_id": run_id, "agent": AGENT_NAME,
        "started_at": state.get("started_at"), "finished_at": utcnow_iso(),
        "model": state.get("model"), "usage": state.get("usage", {}),
        "elapsed_ms": state.get("elapsed_ms", 0), "llm_error": llm_error,
        "output_path": str(out_path),
        "score": score, "passed": passed, "feedback": feedback,
        "review_iterations": iterations,
    }
    audit_path = store.write_audit(AGENT_NAME, run_id, audit)
    store.append_global_log({
        "event": "reviewer_run_finished", "run_id": run_id,
        "score": score, "passed": passed, "iterations": iterations,
    })

    log.info("[reviewer.save_artifact] score=%d passed=%s iter=%d", score, passed, iterations)
    return {
        "review_score": score,
        "review_passed": passed,
        "review_feedback": feedback,
        "review_iterations": iterations,
        "output_path": str(out_path),
        "audit_path": str(audit_path),
        "finished_at": audit["finished_at"],
    }


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────
_JSON_RE = re.compile(r"\{[^{}]*\"score\"[^{}]*\"passed\"[^{}]*\"feedback\"[^{}]*\}", re.DOTALL)


def _parse_review_output(text: str) -> tuple[int, bool, str]:
    """Extract a (score, passed, feedback) tuple from the LLM output.

    Accepts:
    - clean JSON: ``{"score": 8, "passed": true, "feedback": "..."}``
    - JSON wrapped in ```json fences```
    - JSON embedded in surrounding prose
    """
    candidates: list[str] = []
    # 1. Fenced block
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        candidates.append(fence.group(1))
    # 2. Regex match for the full triple
    for m in _JSON_RE.finditer(text):
        candidates.append(m.group(0))
    # 3. Whole-string JSON
    stripped = text.strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        candidates.append(stripped)

    last_err: Exception | None = None
    for c in candidates:
        try:
            data = json.loads(c)
            score = int(data.get("score", 0))
            passed = bool(data.get("passed", score >= 7))
            feedback = str(data.get("feedback", "")).strip() or "ok"
            return max(0, min(score, 10)), passed, feedback
        except (json.JSONDecodeError, ValueError, TypeError) as e:
            last_err = e
            continue

    log.warning("[reviewer] could not parse JSON verdict: %s err=%s", text[:200], last_err)
    # Safe default: treat unparseable output as a low score so the orchestrator
    # falls back to the Editor (which still produces a result).
    return 0, False, "review output was not valid JSON; forcing edit pass."
