"""Shared helpers for the 4-node agent pipeline.

Every agent (narrator / world_builder / judge) follows the same
``load_settings → build_prompt → call_agnes_llm → save_artifact`` shape.
``load_agent_settings`` deduplicates the identical ``load_settings`` body (which
only differs by the agent name in its log line) and ``normalize_choices``
deduplicates the identical choices shaping used by narrator + world_builder.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from ..artifacts import store
from ..utils.timing import utcnow_iso

log = logging.getLogger(__name__)


def load_agent_settings(agent_name: str) -> dict[str, Any]:
    """Build the per-turn LLM settings dict shared by every agent node.

    Base URL / model / API-key presence come from env, a fresh ``run_id`` is
    minted, and the start time is stamped. ``agent_name`` only parametrises the
    log line.
    """
    base_url = os.environ.get("AGNES_BASE_URL", "https://apihub.agnes-ai.com/v1")
    model = os.environ.get("AGNES_MODEL", "agnes-2.0-flash")
    api_key = os.environ.get("AGNES_API_KEY", "")
    run_id = store.new_run_id()
    log.info("[%s.load_settings] run_id=%s model=%s", agent_name, run_id, model)
    return {
        "model": model,
        "base_url": base_url,
        "api_key_set": bool(api_key),
        "run_id": run_id,
        "started_at": utcnow_iso(),
    }


def normalize_choices(value: Any) -> list[str]:
    """Coerce a raw model choices payload into up to 3 non-empty strings."""
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
        text = text.strip()
        if text:
            choices.append(text)
        if len(choices) == 3:
            break
    return choices
