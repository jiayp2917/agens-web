"""Safe artifact persistence for local model evaluation.

Product runs do not persist raw model traffic. Evaluation runs opt in through
``AGENS_EVALUATION_MODE=1`` and must write only to an external, access-restricted
directory. The sink redacts every persisted value again at the final boundary.
"""

from __future__ import annotations

import getpass
import hashlib
import json
import os
import re
import subprocess
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .. import paths

_EVALUATION_MODE_ENV = "AGENS_EVALUATION_MODE"
_ARTIFACT_ROOT_ENV = "AGENS_ARTIFACT_ROOT"
_SECRET_KEY_RE = re.compile(
    r"(?i)(?:[a-z][a-z0-9_-]*?(?:key|secret|token|cookie|authorization|password))\s*[:=]\s*[^\s,;]+"
)
_BEARER_RE = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{8,}")
_PREFIXED_TOKEN_RE = re.compile(r"\b(?:sk|ag|ds|rk)-[A-Za-z0-9_-]{8,}", re.IGNORECASE)
_URL_RE = re.compile(r"https?://[^\s\]\[\"'<>{}]+", re.IGNORECASE)
_SENSITIVE_KEYS = {
    "api_key",
    "apikey",
    "authorization",
    "cookie",
    "password",
    "secret",
    "token",
    "base_url",
    "prompt",
    "messages",
    "user_input",
    "game_state_json",
}
_DEV_NULL = Path(os.devnull)


class ArtifactPolicyError(RuntimeError):
    """Raised when an evaluation run cannot prove safe artifact storage."""


def evaluation_mode_enabled() -> bool:
    return os.environ.get(_EVALUATION_MODE_ENV, "").strip().lower() in {"1", "true", "yes", "on"}


def ensure_evaluation_sink_ready() -> Path | None:
    """Validate the external root before any evaluation provider request."""
    if not evaluation_mode_enabled():
        return None
    if os.environ.get("AGENS_ENV", "").strip().lower() in {"prod", "production"}:
        raise ArtifactPolicyError("evaluation mode is disabled in production")
    raw_root = os.environ.get(_ARTIFACT_ROOT_ENV, "").strip()
    if not raw_root:
        raise ArtifactPolicyError("AGENS_ARTIFACT_ROOT is required in evaluation mode")
    root = Path(raw_root).expanduser().resolve()
    project_root = paths.PROJECT_ROOT.resolve()
    try:
        root.relative_to(project_root)
    except ValueError:
        pass
    else:
        raise ArtifactPolicyError("AGENS_ARTIFACT_ROOT must be outside the repository")
    root.mkdir(parents=True, exist_ok=True)
    _restrict_windows_acl(root)
    if any(root.rglob("input.json")):
        raise ArtifactPolicyError("AGENS_ARTIFACT_ROOT contains forbidden input snapshots")
    return root


def create_evaluation_run_root(parent: Path, *, label: str) -> tuple[str, Path]:
    """Atomically reserve a new external evidence root for one evaluation run."""
    resolved_parent = parent.expanduser().resolve()
    project_root = paths.PROJECT_ROOT.resolve()
    try:
        resolved_parent.relative_to(project_root)
    except ValueError:
        pass
    else:
        raise ArtifactPolicyError("evaluation artifact parent must be outside the repository")
    resolved_parent.mkdir(parents=True, exist_ok=True)
    _restrict_windows_acl(resolved_parent)
    safe_label = _safe_name(label)
    for _ in range(10):
        run_id = f"{datetime.now(UTC):%Y%m%dT%H%M%S%fZ}-{safe_label}-{uuid.uuid4().hex[:8]}"
        root = resolved_parent / run_id
        try:
            root.mkdir()
        except FileExistsError:
            continue
        _restrict_windows_acl(root)
        return run_id, root
    raise ArtifactPolicyError("could not reserve a unique evaluation artifact root")


def run_dir(agent_name: str, run_id: str) -> Path:
    """Return an external run directory, or the null device outside evaluation."""
    root = ensure_evaluation_sink_ready()
    if root is None:
        return _DEV_NULL
    target = root / "agents" / _safe_name(agent_name) / _safe_name(run_id)
    target.mkdir(parents=True, exist_ok=True)
    return target


def write_json(agent_name: str, run_id: str, name: str, payload: dict[str, Any]) -> Path:
    target = run_dir(agent_name, run_id)
    if target == _DEV_NULL:
        return _DEV_NULL
    path = target / _safe_name(name)
    path.write_text(json.dumps(redact_value(payload), ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def write_text(agent_name: str, run_id: str, name: str, text: str) -> Path:
    target = run_dir(agent_name, run_id)
    if target == _DEV_NULL:
        return _DEV_NULL
    path = target / _safe_name(name)
    path.write_text(redact_text(text), encoding="utf-8")
    return path


def append_jsonl(name: str, payload: dict[str, Any]) -> Path:
    root = ensure_evaluation_sink_ready()
    if root is None:
        return _DEV_NULL
    logs = root / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    path = logs / _safe_name(name)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(redact_value(payload), ensure_ascii=False) + "\n")
    return path


def redact_text(value: Any) -> str:
    text = str(value or "")
    text = _SECRET_KEY_RE.sub("[redacted_secret]", text)
    text = _BEARER_RE.sub("[redacted_secret]", text)
    text = _PREFIXED_TOKEN_RE.sub("[redacted_secret]", text)
    return _URL_RE.sub("[redacted_url]", text)


def redact_value(value: Any) -> Any:
    """Recursively remove sensitive field values without echoing them."""
    if isinstance(value, dict):
        return {
            str(key): "[redacted]" if _is_sensitive_key(str(key)) else redact_value(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_value(item) for item in value]
    if isinstance(value, tuple):
        return [redact_value(item) for item in value]
    if isinstance(value, str):
        return redact_text(value)
    return value


def external_inventory(root: Path | None = None) -> dict[str, Any]:
    """Return only counts and hashes for a ready evaluation root."""
    resolved = root or ensure_evaluation_sink_ready()
    if resolved is None:
        return {"enabled": False, "file_count": 0, "files": []}
    files = [path for path in resolved.rglob("*") if path.is_file()]
    return {
        "enabled": True,
        "file_count": len(files),
        "files": [
            {
                "path": str(path.relative_to(resolved)),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
            for path in sorted(files)
        ],
    }


def cleanup_expired(
    root: Path | None = None,
    *,
    retention_days: int = 30,
    confirm: bool = False,
) -> dict[str, Any]:
    """Report, then optionally remove, expired external evaluation files."""
    if retention_days < 1:
        raise ValueError("retention_days must be at least one")
    resolved = root or ensure_evaluation_sink_ready()
    if resolved is None:
        return {"enabled": False, "candidate_count": 0, "deleted_count": 0}
    cutoff = time.time() - retention_days * 24 * 60 * 60
    candidates = [
        path
        for path in resolved.rglob("*")
        if path.is_file() and path.stat().st_mtime < cutoff
    ]
    deleted_count = 0
    if confirm:
        for path in candidates:
            path.unlink()
            deleted_count += 1
    return {
        "enabled": True,
        "candidate_count": len(candidates),
        "deleted_count": deleted_count,
        "dry_run": not confirm,
    }


def sensitive_marker_counts(root: Path | None = None) -> dict[str, int]:
    """Count secret-like markers without returning file names or matched text."""
    resolved = root or ensure_evaluation_sink_ready()
    if resolved is None:
        return {"secret_like": 0, "url_like": 0}
    counts = {"secret_like": 0, "url_like": 0}
    for path in resolved.rglob("*"):
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        counts["secret_like"] += sum(
            len(pattern.findall(text))
            for pattern in (_SECRET_KEY_RE, _BEARER_RE, _PREFIXED_TOKEN_RE)
        )
        counts["url_like"] += len(_URL_RE.findall(text))
    return counts


def _safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value or "artifact")).strip("._") or "artifact"


def _is_sensitive_key(key: str) -> bool:
    lowered = key.strip().lower().replace("-", "_")
    if lowered in _SENSITIVE_KEYS or any(marker in lowered for marker in ("secret", "password")):
        return True
    return "token" in lowered and not lowered.endswith("_tokens")


def _restrict_windows_acl(root: Path) -> None:
    """Restrict external evaluation evidence to the current account and SYSTEM."""
    if os.name != "nt":
        return
    user = getpass.getuser()
    commands = (
        ["icacls", str(root), "/inheritance:r"],
        ["icacls", str(root), "/grant:r", f"{user}:(OI)(CI)F", "SYSTEM:(OI)(CI)F"],
        ["icacls", str(root), "/remove:g", "Everyone", "Users", "Authenticated Users"],
    )
    for command in commands:
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            raise ArtifactPolicyError("could not restrict AGENS_ARTIFACT_ROOT ACL")
