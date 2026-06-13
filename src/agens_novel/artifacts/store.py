"""Artifact storage: write per-run output files + audit JSON."""

from __future__ import annotations

import json
import logging
import os
import uuid
from pathlib import Path
from typing import Any

from .. import paths
from ..utils.timing import utcnow_compact, utcnow_iso

log = logging.getLogger(__name__)

# Sentinel path returned when writes fail (e.g. read-only Android bundle).
_DEV_NULL = Path(os.devnull)


def new_run_id() -> str:
    """Generate a short run id (timestamp + uuid prefix)."""
    return f"{utcnow_compact()}_{uuid.uuid4().hex[:8]}"


def run_dir(agent_name: str, run_id: str) -> Path:
    """Create and return the per-run directory."""
    try:
        p = paths.agent_artifact_dir(agent_name) / run_id
        p.mkdir(parents=True, exist_ok=True)
        return p
    except OSError as exc:
        log.warning("Could not create artifact dir: %s", exc)
        return _DEV_NULL / agent_name / run_id


def write_input_snapshot(agent_name: str, run_id: str, payload: dict[str, Any]) -> Path:
    """Write the initial input.json for a run."""
    try:
        p = run_dir(agent_name, run_id) / "input.json"
        # Strip any fields we know are sensitive before persisting.
        safe = {k: v for k, v in payload.items() if k not in {"api_key", "AGNES_API_KEY"}}
        p.write_text(json.dumps(safe, ensure_ascii=False, indent=2), encoding="utf-8")
        return p
    except OSError as exc:
        log.warning("Could not write input snapshot: %s", exc)
        return _DEV_NULL


def write_output(agent_name: str, run_id: str, text: str) -> Path:
    """Write the final output.md for a run."""
    try:
        p = run_dir(agent_name, run_id) / "output.md"
        p.write_text(text, encoding="utf-8")
        log.info("[save_artifact] wrote %s (%d chars)", p, len(text))
        return p
    except OSError as exc:
        log.warning("Could not write artifact output: %s", exc)
        return _DEV_NULL


def write_audit(agent_name: str, run_id: str, audit: dict[str, Any]) -> Path:
    """Write a per-run audit.json with all node transitions and final state."""
    try:
        p = run_dir(agent_name, run_id) / "audit.json"
        p.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
        return p
    except OSError as exc:
        log.warning("Could not write audit: %s", exc)
        return _DEV_NULL


def append_global_log(entry: dict[str, Any]) -> Path:
    """Append a single JSON line to runtime/logs/run_<ts>.jsonl."""
    try:
        ts = utcnow_compact()
        p = paths.log_path(ts)
        entry = {**entry, "logged_at": utcnow_iso()}
        with p.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return p
    except OSError as exc:
        log.warning("Could not append global log: %s", exc)
        return _DEV_NULL
