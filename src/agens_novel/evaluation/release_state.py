"""External recovery state for a resumable local evaluation and release run."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .. import paths
from ..artifacts.sink import ArtifactPolicyError, create_evaluation_run_root, redact_value

_VERSION = "ReleaseRunStateV1"
_FORBIDDEN_DETAIL_MARKERS = ("key", "secret", "token", "cookie", "authorization", "prompt", "url")


@dataclass(frozen=True)
class ReleaseRunStateV1:
    """One external, redacted checkpoint file for an authorized release run."""

    root: Path
    run_id: str

    @classmethod
    def create(cls, parent: Path, *, label: str, commit: str, budget_root: Path) -> ReleaseRunStateV1:
        run_id, root = create_evaluation_run_root(parent, label=label)
        state = cls(root=root, run_id=run_id)
        state._write(
            {
                "version": _VERSION,
                "run_id": run_id,
                "commit": _short_value(commit, "commit"),
                "budget_root": str(budget_root.resolve()),
                "checkpoints": [],
            }
        )
        return state

    @classmethod
    def open(cls, path: Path) -> ReleaseRunStateV1:
        """Open one existing external state file without creating a new run root."""
        candidate = path.expanduser().resolve()
        state_path = candidate / "release-run-state.json" if candidate.is_dir() else candidate
        if state_path.name != "release-run-state.json":
            raise ArtifactPolicyError("release recovery state has an invalid name")
        try:
            state_path.parent.relative_to(paths.PROJECT_ROOT.resolve())
        except ValueError:
            pass
        else:
            raise ArtifactPolicyError("release recovery state must be outside the repository")
        provisional = cls(root=state_path.parent, run_id="unopened")
        payload = provisional.read()
        run_id = _short_value(str(payload.get("run_id") or ""), "run id")
        return cls(root=state_path.parent, run_id=run_id)

    @property
    def path(self) -> Path:
        return self.root / "release-run-state.json"

    def checkpoint(self, phase: str, *, status: str, details: dict[str, Any] | None = None) -> None:
        safe_phase = _short_value(phase, "phase")
        safe_status = _short_value(status, "status")
        payload = self.read()
        checkpoints = payload.get("checkpoints")
        if not isinstance(checkpoints, list):
            raise ArtifactPolicyError("release recovery checkpoints are invalid")
        checkpoints.append(
            {
                "phase": safe_phase,
                "status": safe_status,
                "details": _safe_details(details or {}),
            }
        )
        self._write(payload)

    def latest_checkpoint(self, phase: str) -> dict[str, Any] | None:
        """Return the latest safe checkpoint for one phase, if any."""
        safe_phase = _short_value(phase, "phase")
        checkpoints = self.read().get("checkpoints")
        if not isinstance(checkpoints, list):
            raise ArtifactPolicyError("release recovery checkpoints are invalid")
        for checkpoint in reversed(checkpoints):
            if isinstance(checkpoint, dict) and checkpoint.get("phase") == safe_phase:
                return dict(checkpoint)
        return None

    def is_passed(self, phase: str) -> bool:
        """Return whether the latest checkpoint for a phase is an accepted pass."""
        checkpoint = self.latest_checkpoint(phase)
        return bool(checkpoint and checkpoint.get("status") == "passed")

    def read(self) -> dict[str, Any]:
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ArtifactPolicyError("release recovery state is unreadable") from exc
        if not isinstance(value, dict) or value.get("version") != _VERSION:
            raise ArtifactPolicyError("release recovery state is invalid")
        return value

    def _write(self, value: dict[str, Any]) -> None:
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(redact_value(value), ensure_ascii=False, sort_keys=True, indent=2),
            encoding="utf-8",
        )
        os.replace(temporary, self.path)


def _safe_details(value: dict[str, Any]) -> dict[str, Any]:
    for key in value:
        normalized = str(key).lower().replace("-", "_")
        if any(marker in normalized for marker in _FORBIDDEN_DETAIL_MARKERS):
            raise ValueError("release recovery details contain a forbidden key")
    return redact_value(value)


def _short_value(value: str, field: str) -> str:
    normalized = str(value or "").strip()
    if not normalized or len(normalized) > 160:
        raise ValueError(f"release recovery {field} must be a short non-empty value")
    return normalized
