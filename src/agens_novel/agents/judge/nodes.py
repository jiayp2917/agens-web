"""Judge Agent node functions.

Reviews the Narrator's output for consistency and balance.  Returns a JSON
verdict: approved (bool), corrected_delta (dict), judgment_note (str).

Key change: _parse_judge_output defaults to approved=False on parse failure,
preventing invalid state updates from being applied.

4-node pattern: load_settings → build_prompt → call_agnes_llm → save_artifact
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from ... import paths
from ...artifacts import store
from ...llm.types import Message
from ...utils.timing import utcnow_iso
from ..common import call_agnes_llm_common, load_agent_settings
from ..common import prompt_metrics as _prompt_metrics

log = logging.getLogger(__name__)

AGENT_NAME = "judge"
_MAX_CANDIDATE_LEN = 65536


def load_settings(state: dict[str, Any]) -> dict[str, Any]:
    return load_agent_settings(AGENT_NAME, state)


def build_prompt(state: dict[str, Any]) -> dict[str, Any]:
    system_path = paths.system_prompt_path("judge")
    if not system_path.exists():
        raise FileNotFoundError(f"System prompt not found: {system_path}")
    system_message = system_path.read_text(encoding="utf-8").strip()

    narrative = state.get("narrative", "")
    state_delta = state.get("state_delta", {})
    game_state_json = state.get("game_state_json", "{}")
    user_input = state.get("user_input", "")

    user_content = (
        f"<当前游戏状态>\n{game_state_json}\n</当前游戏状态>\n\n"
        f"<玩家行动>\n{user_input}\n</玩家行动>\n\n"
        f"<叙述文本>\n{narrative}\n</叙述文本>\n\n"
        f"<提议的状态更新>\n{json.dumps(state_delta, ensure_ascii=False, indent=2)}\n</提议的状态更新>"
    )

    messages: list[Message] = [
        Message(role="system", content=system_message),
        Message(role="user", content=user_content),
    ]
    prompt_metrics = _prompt_metrics(
        messages,
        game_state_json=game_state_json,
        user_input=user_input,
        narrative=narrative,
    )

    log.info(
        "[judge.build_prompt] narrative=%d delta_keys=%s prompt_chars=%d",
        len(narrative),
        list(state_delta.keys()),
        prompt_metrics["prompt_chars"],
    )
    return {
        "system_message": system_message,
        "user_message": user_content,
        "messages": messages,
        "prompt_metrics": prompt_metrics,
    }


async def call_agnes_llm(state: dict[str, Any]) -> dict[str, Any]:
    return await call_agnes_llm_common(
        state,
        agent_name=AGENT_NAME,
        temperature=0.2,
        max_tokens=512,
        include_prompt_metrics=True,
    )


def save_artifact(state: dict[str, Any]) -> dict[str, Any]:
    """Parse JSON verdict from the LLM output and persist.

    On LLM error, defaults to approved=False (safe default).
    """
    run_id = state.get("run_id") or store.new_run_id()
    text = state.get("output_text", "")
    llm_error = state.get("llm_error", "")

    if llm_error:
        # LLM error: reject by default to prevent bad state updates.
        approved = False
        corrected_delta: dict[str, Any] = {}
        judgment_note = "LLM 调用失败，拒绝状态更新"
        score = 0
    else:
        approved, corrected_delta, judgment_note, score = _parse_judge_output(text)

    out_path = store.write_output(AGENT_NAME, run_id, text)
    store.write_input_snapshot(
        AGENT_NAME, run_id,
        {"model": state.get("model"), "thread_id": state.get("thread_id")},
    )
    audit = {
        "run_id": run_id, "agent": AGENT_NAME,
        "started_at": state.get("started_at"), "finished_at": utcnow_iso(),
        "model": state.get("model"), "usage": state.get("usage", {}),
        "elapsed_ms": state.get("elapsed_ms", 0), "llm_error": llm_error,
        "output_path": str(out_path),
        "approved": approved, "judgment_note": judgment_note, "score": score,
        "prompt_metrics": state.get("prompt_metrics") or {},
    }
    audit_path = store.write_audit(AGENT_NAME, run_id, audit)
    store.append_global_log({
        "event": "judge_run_finished", "run_id": run_id,
        "ok": not llm_error, "approved": approved, "score": score,
    })

    return {
        "approved": approved,
        "corrected_delta": corrected_delta,
        "judgment_note": judgment_note,
        "review_score": score,
        "prompt_metrics": state.get("prompt_metrics") or {},
        "output_path": str(out_path),
        "audit_path": str(audit_path),
        "finished_at": audit["finished_at"],
    }


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _parse_judge_output(text: str) -> tuple[bool, dict, str, int]:
    """Extract (approved, corrected_delta, judgment_note, score) from judge output.

    Accepts JSON in any of these forms:
    - clean JSON
    - ```json fenced```
    - JSON embedded in prose

    **Key change**: Default is approved=False on parse failure to prevent
    invalid/unverified state updates from being applied.
    """
    candidates: list[str] = []

    # 1. Fenced block
    fence = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if fence:
        candidates.append(fence.group(1))

    # 2. Whole-string JSON
    stripped = text.strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        candidates.append(stripped)

    # 3. First brace-to-brace substring
    first_brace = stripped.find("{")
    last_brace = stripped.rfind("}")
    if first_brace >= 0 and last_brace > first_brace:
        candidate = stripped[first_brace: last_brace + 1]
        if candidate not in candidates:
            candidates.append(candidate)

    for c in candidates:
        if len(c) > _MAX_CANDIDATE_LEN:
            continue
        try:
            data = json.loads(c)
            if not isinstance(data, dict):
                continue
            approved_value = data.get("approved")
            approved = approved_value if isinstance(approved_value, bool) else False
            corrected_delta = data.get("corrected_delta", {})
            if not isinstance(corrected_delta, dict):
                corrected_delta = {}
            judgment_note = str(data.get("judgment_note", "ok")).strip() or "ok"
            raw_score = data.get("review_score", data.get("score", 5))
            score = int(5 if raw_score is None else raw_score)
            return approved, corrected_delta, judgment_note, max(0, min(score, 10))
        except (json.JSONDecodeError, ValueError, TypeError):
            continue

    log.warning("[judge] could not parse JSON verdict: %s", text[:200])
    # Default: REJECT on parse failure — safe default prevents bad state updates.
    return False, {}, "Judge 输出无法解析，拒绝状态更新", 0
