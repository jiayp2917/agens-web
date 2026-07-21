"""Artifact storage: write per-run output files + audit JSON."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from ..utils.timing import utcnow_compact, utcnow_iso
from . import sink


def new_run_id() -> str:
    """Generate a short run id (timestamp + uuid prefix)."""
    return f"{utcnow_compact()}_{uuid.uuid4().hex[:8]}"


def run_dir(agent_name: str, run_id: str) -> Path:
    """Create an external evaluation directory, never a raw repo artifact."""
    return sink.run_dir(agent_name, run_id)


def write_input_snapshot(agent_name: str, run_id: str, payload: dict[str, Any]) -> Path:
    """Persist only the redacted evaluation metadata snapshot."""
    return sink.write_json(agent_name, run_id, "input.json", payload)


def write_output(agent_name: str, run_id: str, text: str) -> Path:
    """Persist a redacted response copy only in evaluation mode."""
    return sink.write_text(agent_name, run_id, "response.md", text)


def write_audit(agent_name: str, run_id: str, audit: dict[str, Any]) -> Path:
    """Persist redacted audit facts only in evaluation mode."""
    return sink.write_json(agent_name, run_id, "audit.json", audit)


def append_global_log(entry: dict[str, Any]) -> Path:
    """Append redacted evaluation facts, never runtime logs under the repo."""
    return sink.append_jsonl("agent-events.jsonl", {**entry, "logged_at": utcnow_iso()})
