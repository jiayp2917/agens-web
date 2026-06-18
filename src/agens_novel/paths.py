"""Centralised path resolution for the project.

All filesystem paths go through this module so that:
- Tests can override `PROJECT_ROOT` to a tmp dir.
- Runtime artifacts never escape the `runtime/` tree.
- Source files in `config/` and `src/` are referenced read-only and never written to.
"""

from __future__ import annotations

import os
from pathlib import Path

# Project root: the directory containing pyproject.toml.
# We resolve via this file's location (src/agens_novel/paths.py -> 3 levels up).
_THIS_FILE = Path(__file__).resolve()
PROJECT_ROOT = Path(os.environ.get("AGENS_NOVEL_ROOT", _THIS_FILE.parents[2]))

RUNTIME_DIR = PROJECT_ROOT / "runtime"
ARTIFACT_ROOT = RUNTIME_DIR / "artifacts"
CHECKPOINT_DIR = RUNTIME_DIR / "checkpoints"
LOG_DIR = RUNTIME_DIR / "logs"
CONFIG_DIR = PROJECT_ROOT / "config"
PROMPT_DIR = CONFIG_DIR / "prompts" / "system"
SAVE_DIR = RUNTIME_DIR / "saves"


def ensure_runtime_dirs() -> dict[str, Path]:
    """Create runtime/ subdirs if missing. Returns a dict of created paths."""
    paths = {
        "runtime": RUNTIME_DIR,
        "artifacts": ARTIFACT_ROOT,
        "checkpoints": CHECKPOINT_DIR,
        "logs": LOG_DIR,
        "writer_artifacts": ARTIFACT_ROOT / "writer",
    }
    for p in paths.values():
        p.mkdir(parents=True, exist_ok=True)
    return paths


def agent_artifact_dir(agent_name: str) -> Path:
    """Return the artifact dir for a specific agent. Creates it on demand."""
    p = ARTIFACT_ROOT / agent_name
    try:
        p.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass  # Callers handle read-only or unavailable runtime paths gracefully.
    return p


def system_prompt_path(name: str) -> Path:
    """Resolve a system prompt by filename (no extension)."""
    return PROMPT_DIR / f"{name}.md"


def log_path(timestamp: str) -> Path:
    """Path for a per-run audit log (jsonl)."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    return LOG_DIR / f"run_{timestamp}.jsonl"


def checkpoint_path(thread_id: str) -> Path:
    """SQLite checkpoint DB path. A single DB is fine for v1."""
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    return CHECKPOINT_DIR / f"{thread_id}.sqlite"


def save_path(name: str) -> Path:
    """Return the path for a game save file. Creates SAVE_DIR on demand."""
    SAVE_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = "".join(c for c in name if c.isalnum() or c in ("-", "_")) or "default"
    return SAVE_DIR / f"{safe_name}.json"
