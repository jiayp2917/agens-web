"""World Builder Agent node functions.

Generates initial character state, starting world, and new content on demand.
Output is wrapped in ``<world_data>`` tags containing structured JSON.

4-node pattern: load_settings → build_prompt → call_agnes_llm → save_artifact
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
from ...utils.timing import utcnow_iso

log = logging.getLogger(__name__)

AGENT_NAME = "world_builder"


def load_settings(state: dict[str, Any]) -> dict[str, Any]:
    base_url = os.environ.get("AGNES_BASE_URL", "https://apihub.agnes-ai.com/v1")
    model = os.environ.get("AGNES_MODEL", "agnes-2.0-flash")
    api_key = os.environ.get("AGNES_API_KEY", "")
    run_id = store.new_run_id()
    log.info("[world_builder.load_settings] run_id=%s model=%s", run_id, model)
    return {
        "model": model, "base_url": base_url, "api_key_set": bool(api_key),
        "run_id": run_id, "started_at": utcnow_iso(),
    }


def build_prompt(state: dict[str, Any]) -> dict[str, Any]:
    system_path = paths.system_prompt_path("world_builder")
    if not system_path.exists():
        raise FileNotFoundError(f"System prompt not found: {system_path}")
    system_message = system_path.read_text(encoding="utf-8").strip()

    user_input = state.get("user_input", "").strip()
    if not user_input:
        raise ValueError("user_input is required.")

    generation_type = state.get("generation_type", "new_game")
    game_state_json = state.get("game_state_json", "")

    parts = [f"<生成类型>{generation_type}</生成类型>"]
    if game_state_json:
        parts.append(f"<当前状态>\n{game_state_json}\n</当前状态>")
    parts.append(f"<玩家输入>\n{user_input}\n</玩家输入>")

    user_content = "\n\n".join(parts)

    messages: list[Message] = [
        Message(role="system", content=system_message),
        Message(role="user", content=user_content),
    ]

    log.info("[world_builder.build_prompt] type=%s user=%d", generation_type, len(user_input))
    return {
        "system_message": system_message,
        "user_message": user_content,
        "messages": messages,
    }


async def call_agnes_llm(state: dict[str, Any]) -> dict[str, Any]:
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
    try:
        resp = await call_llm(
            messages,
            model=state.get("model"),
            base_url=state.get("base_url"),
            temperature=0.6,
            max_tokens=4096,
            stream=False,
        )
        return {
            "output_text": resp.get("text", ""),
            "usage": dict(resp.get("usage") or {}),
            "elapsed_ms": int(resp.get("elapsed_ms", 0)),
            "llm_error": "",
        }
    except LLMError as e:
        log.error("[world_builder.call_agnes_llm] failed: %s", e)
        return {"output_text": "", "llm_error": str(e), "elapsed_ms": 0, "usage": {}}


def save_artifact(state: dict[str, Any]) -> dict[str, Any]:
    """Parse <world_data> JSON from the LLM output and persist."""
    run_id = state.get("run_id") or store.new_run_id()
    text = state.get("output_text", "")
    llm_error = state.get("llm_error", "")

    if llm_error:
        generated_data, world_description, opening_narrative = {}, "", ""
    else:
        generated_data, world_description, opening_narrative = _parse_world_output(text)

    out_path = store.write_output(AGENT_NAME, run_id, text)
    store.write_input_snapshot(
        AGENT_NAME, run_id,
        {"user_input": state.get("user_input"),
         "generation_type": state.get("generation_type"), "model": state.get("model")},
    )
    audit = {
        "run_id": run_id, "agent": AGENT_NAME,
        "started_at": state.get("started_at"), "finished_at": utcnow_iso(),
        "model": state.get("model"), "usage": state.get("usage", {}),
        "elapsed_ms": state.get("elapsed_ms", 0), "llm_error": llm_error,
        "output_path": str(out_path),
        "generation_type": state.get("generation_type", "new_game"),
    }
    audit_path = store.write_audit(AGENT_NAME, run_id, audit)
    store.append_global_log({
        "event": "world_builder_run_finished", "run_id": run_id,
        "ok": not llm_error, "type": state.get("generation_type", "new_game"),
    })

    return {
        "generated_data": generated_data,
        "world_description": world_description,
        "opening_narrative": opening_narrative,
        "output_path": str(out_path),
        "audit_path": str(audit_path),
        "finished_at": audit["finished_at"],
    }


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

_TAG_RE = re.compile(r"<world_data>(.*?)</world_data>", re.DOTALL)


def _parse_world_output(text: str) -> tuple[dict, str, str]:
    """Extract (generated_data, world_description, opening_narrative) from output."""
    generated_data: dict = {}
    world_description = text
    opening_narrative = ""

    m = _TAG_RE.search(text)
    if m:
        world_description = text[: m.start()].strip()
        raw_json = m.group(1).strip()
        try:
            data = json.loads(raw_json)
            if isinstance(data, dict):
                generated_data = data
                opening_narrative = data.get("opening_narrative", "")
        except (json.JSONDecodeError, ValueError):
            log.warning("[world_builder] world_data JSON parse failed: %s", raw_json[:200])

    return generated_data, world_description, opening_narrative
