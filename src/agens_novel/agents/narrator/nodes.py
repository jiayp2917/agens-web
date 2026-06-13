"""Narrator Agent node functions.

Takes the player's action + current game state, produces narrative text +
a structured state delta wrapped in ``<state_update>`` tags.

4-node pattern: load_settings → build_prompt → call_agnes_llm → save_artifact

Stream support: when a ``stream_callback`` is present in state, the LLM call
uses streaming and each chunk is forwarded to the callback in real-time.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Callable

from ...artifacts import store
from ...llm.client import LLMError, call_llm_stream
from ...llm.types import Message
from ... import paths
from ...utils.timing import utcnow_iso

log = logging.getLogger(__name__)

AGENT_NAME = "narrator"
_MAX_HISTORY_TURNS = 20


def load_settings(state: dict[str, Any]) -> dict[str, Any]:
    base_url = os.environ.get("AGNES_BASE_URL", "https://apihub.agnes-ai.com/v1")
    model = os.environ.get("AGNES_MODEL", "agnes-2.0-flash")
    api_key = os.environ.get("AGNES_API_KEY", "")
    run_id = store.new_run_id()
    log.info("[narrator.load_settings] run_id=%s model=%s", run_id, model)
    return {
        "model": model, "base_url": base_url, "api_key_set": bool(api_key),
        "run_id": run_id, "started_at": utcnow_iso(),
    }


def build_prompt(state: dict[str, Any]) -> dict[str, Any]:
    system_path = paths.system_prompt_path("narrator")
    if not system_path.exists():
        raise FileNotFoundError(f"System prompt not found: {system_path}")
    system_message = system_path.read_text(encoding="utf-8").strip()

    # If in combat, append combat narrator instructions.
    combat = None
    char_state = state.get("game_state_json", "{}")
    try:
        parsed = json.loads(char_state) if isinstance(char_state, str) else char_state
        combat = parsed.get("character", {}).get("combat")
    except (json.JSONDecodeError, ValueError):
        pass

    if combat and combat.get("phase") not in (None, "idle", ""):
        combat_prompt_path = paths.system_prompt_path("combat_narrator")
        if combat_prompt_path.exists():
            combat_addendum = combat_prompt_path.read_text(encoding="utf-8").strip()
            system_message = system_message + "\n\n" + combat_addendum

    user_input = state.get("user_input", "").strip()
    if not user_input:
        raise ValueError("user_input is required.")

    game_state_json = state.get("game_state_json", "{}")

    # Build messages: system + chat history + current turn.
    history: list[dict] = list(state.get("chat_history") or [])
    if len(history) > _MAX_HISTORY_TURNS:
        history = history[-_MAX_HISTORY_TURNS:]

    user_content = (
        f"<当前状态>\n{game_state_json}\n</当前状态>\n\n"
        f"<玩家行动>\n{user_input}\n</玩家行动>"
    )

    messages: list[Message] = [Message(role="system", content=system_message)]
    for entry in history:
        messages.append(Message(
            role=entry.get("role", "user"),
            content=entry.get("content", ""),
        ))
    messages.append(Message(role="user", content=user_content))

    log.info("[narrator.build_prompt] history=%d user=%d", len(history), len(user_input))
    return {
        "system_message": system_message,
        "user_message": user_content,
        "messages": messages,
    }


async def call_agnes_llm(state: dict[str, Any]) -> dict[str, Any]:
    """Call the LLM with streaming support.

    If ``stream_callback`` is present in state, uses ``call_llm_stream``
    which invokes the callback for each text chunk.  Otherwise falls back
    to a normal non-streaming call.
    """
    if not state.get("api_key_set"):
        return {
            "output_text": "", "llm_error": "AGNES_API_KEY 未设置。",
            "elapsed_ms": 0, "usage": {},
        }
    messages: list[Message] = state.get("messages") or []
    if not messages:
        return {
            "output_text": "", "llm_error": "messages 为空。",
            "elapsed_ms": 0, "usage": {},
        }

    stream_callback: Callable[[str], None] | None = state.get("stream_callback")
    # Fallback: try thread-local context (avoids msgpack serialization issues).
    if stream_callback is None:
        from ...repl._stream_context import get as _get_stream_cb
        stream_callback = _get_stream_cb()

    try:
        if stream_callback is not None:
            # Streaming mode: each chunk pushed to callback.
            resp = await call_llm_stream(
                messages,
                model=state.get("model"),
                base_url=state.get("base_url"),
                temperature=0.8,
                max_tokens=1536,
                on_chunk=stream_callback,
            )
        else:
            # Non-streaming fallback.
            from ...llm.client import call_llm
            resp = await call_llm(
                messages,
                model=state.get("model"),
                base_url=state.get("base_url"),
                temperature=0.8,
                max_tokens=1536,
                stream=False,
            )
        return {
            "output_text": resp.get("text", ""),
            "usage": dict(resp.get("usage") or {}),
            "elapsed_ms": int(resp.get("elapsed_ms", 0)),
            "llm_error": "",
        }
    except LLMError as e:
        log.error("[narrator.call_agnes_llm] failed: %s", e)
        return {"output_text": "", "llm_error": str(e), "elapsed_ms": 0, "usage": {}}


def save_artifact(state: dict[str, Any]) -> dict[str, Any]:
    """Parse narrative + <state_update> from the LLM output and persist."""
    run_id = state.get("run_id") or store.new_run_id()
    text = state.get("output_text", "")
    llm_error = state.get("llm_error", "")

    if llm_error:
        narrative, state_delta, choices = "", {}, []
    else:
        narrative, state_delta, choices = _parse_narrator_output(text)

    out_path = store.write_output(AGENT_NAME, run_id, text)
    store.write_input_snapshot(
        AGENT_NAME, run_id,
        {"user_input": state.get("user_input"), "model": state.get("model")},
    )
    audit = {
        "run_id": run_id, "agent": AGENT_NAME,
        "started_at": state.get("started_at"), "finished_at": utcnow_iso(),
        "model": state.get("model"), "usage": state.get("usage", {}),
        "elapsed_ms": state.get("elapsed_ms", 0), "llm_error": llm_error,
        "output_path": str(out_path),
        "narrative_chars": len(narrative),
    }
    audit_path = store.write_audit(AGENT_NAME, run_id, audit)
    store.append_global_log({
        "event": "narrator_run_finished", "run_id": run_id,
        "ok": not llm_error, "chars": len(narrative),
    })

    return {
        "narrative": narrative,
        "state_delta": state_delta,
        "choices": choices,
        "output_path": str(out_path),
        "audit_path": str(audit_path),
        "finished_at": audit["finished_at"],
    }


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

_TAG_RE = re.compile(r"<state_update>(.*?)</state_update>", re.DOTALL)


def _parse_narrator_output(text: str) -> tuple[str, dict, list[str]]:
    """Extract (narrative, state_delta, choices) from the narrator LLM output.

    The narrative is everything before the ``<state_update>`` tag.
    The delta is parsed as JSON from within the tags.
    """
    narrative = text
    state_delta: dict = {}
    choices: list[str] = []

    m = _TAG_RE.search(text)
    if m:
        # Narrative is everything before the tag.
        narrative = text[: m.start()].strip()
        raw_json = m.group(1).strip()
        try:
            data = json.loads(raw_json)
            if isinstance(data, dict):
                state_delta = data
        except (json.JSONDecodeError, ValueError):
            log.warning("[narrator] state_update JSON parse failed: %s", raw_json[:200])

    return narrative, state_delta, choices
