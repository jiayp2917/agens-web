"""Shared helpers for the 4-node agent pipeline.

Every agent (narrator / world_builder / judge) follows the same
``load_settings → build_prompt → call_agnes_llm → save_artifact`` shape.
``load_agent_settings`` deduplicates the identical ``load_settings`` body (which
only differs by the agent name in its log line) and ``normalize_choices``
deduplicates the identical A/B/C/D choices shaping used by narrator + world_builder.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from ..artifacts import store
from ..engine.choices import clean_choice_text
from ..utils.timing import utcnow_iso

log = logging.getLogger(__name__)


def load_agent_settings(agent_name: str, state: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build the per-turn LLM settings dict shared by every agent node.

    Web requests may inject a user-scoped model config through ``state``. The
    environment remains a development fallback, but explicit state wins so one
    user's key cannot leak into another request through process globals.
    """
    state = state or {}
    base_url = str(state.get("base_url") or os.environ.get("AGNES_BASE_URL") or "https://apihub.agnes-ai.com/v1")
    model = str(state.get("model") or os.environ.get("AGNES_MODEL") or "agnes-2.0-flash")
    if "api_key" in state:
        api_key = str(state.get("api_key") or "")
    else:
        api_key = os.environ.get("AGNES_API_KEY", "")
    if "api_key_set" in state:
        api_key_set = bool(state.get("api_key_set")) and bool(api_key)
    else:
        api_key_set = bool(api_key)
    run_id = store.new_run_id()
    log.info("[%s.load_settings] run_id=%s model=%s key_set=%s", agent_name, run_id, model, api_key_set)
    return {
        "model": model,
        "base_url": base_url,
        "api_key": api_key,
        "api_key_set": api_key_set,
        "run_id": run_id,
        "started_at": utcnow_iso(),
    }


def normalize_choices(value: Any) -> list[str]:
    """Coerce a raw model choices payload into up to 4 non-empty strings."""
    choices: list[str] = []
    if not isinstance(value, list):
        return choices
    for item in value:
        if isinstance(item, str):
            text = item
        elif isinstance(item, dict):
            raw = item.get("action") or item.get("text") or item.get("label")
            text = str(raw) if raw is not None else ""
        else:
            text = ""
        text = clean_choice_text(text)
        if text:
            choices.append(text)
        if len(choices) == 4:
            break
    return choices
