"""External, network-free recovery state for local governance runs."""

from __future__ import annotations

import getpass
import json
import os
import re
import subprocess
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .. import paths

_VERSION = "GovernanceRunStateV1"
_STATE_FILE = "governance-run-state.json"
_SAFE_LABEL = re.compile(r"^[A-Za-z0-9_.:-]{1,160}$")
_FORBIDDEN_KEY_MARKERS = (
    "api_key",
    "apikey",
    "secret",
    "password",
    "cookie",
    "authorization",
    "prompt",
    "base_url",
    "endpoint",
)
_URL_RE = re.compile(r"(?i)\bhttps?://\S+")
_SECRET_VALUE_RE = re.compile(
    r"(?i)(?:\bbearer\s+\S+|\b(?:sk|ag|ds|rk)-[A-Za-z0-9_-]{8,}|"
    r"(?:api[_ -]?key|secret|cookie|authorization|prompt)\s*[:=])"
)


class GovernanceStateError(RuntimeError):
    """Raised when recovery state cannot stay outside the repository safely."""


@dataclass(frozen=True)
class GovernanceRunStateV1:
    """One append-only, redacted checkpoint stream for a local governance run."""

    root: Path
    run_id: str

    @classmethod
    def create(
        cls,
        parent: Path,
        *,
        commit: str,
        database_label: str,
        model_label: str,
        scenario_label: str,
        evidence_root: Path,
        phase: str = "created",
        checkpoint: str = "created",
        recovery_point: str | None = None,
        test_summary: dict[str, Any] | None = None,
    ) -> GovernanceRunStateV1:
        """Atomically reserve a unique external root and write its first checkpoint."""
        resolved_parent = _external_path(parent, "governance state parent")
        resolved_evidence_root = _external_path(evidence_root, "evidence root")
        resolved_parent.mkdir(parents=True, exist_ok=True)

        for _ in range(10):
            run_id = _new_run_id()
            root = resolved_parent / run_id
            try:
                root.mkdir()
            except FileExistsError:
                continue
            try:
                _restrict_windows_acl(root)
                state = cls(root=root, run_id=run_id)
                payload = state._initial_payload(
                    commit=commit,
                    database_label=database_label,
                    model_label=model_label,
                    scenario_label=scenario_label,
                    evidence_root=resolved_evidence_root,
                )
                state._append_checkpoint(
                    payload,
                    phase=phase,
                    checkpoint=checkpoint,
                    recovery_point=recovery_point,
                    test_summary=test_summary,
                )
                state._write(payload)
                return state
            except Exception:
                # The root is intentionally retained for forensic inspection.
                raise
        raise GovernanceStateError("could not reserve a unique governance state directory")

    @classmethod
    def open(cls, path: Path) -> GovernanceRunStateV1:
        """Open an existing external recovery record without creating anything."""
        candidate = path.expanduser().resolve()
        state_path = candidate / _STATE_FILE if candidate.is_dir() else candidate
        if state_path.name != _STATE_FILE:
            raise GovernanceStateError("governance recovery state has an invalid name")
        root = _external_path(state_path.parent, "governance state root")
        provisional = cls(root=root, run_id="unopened")
        payload = provisional.read()
        run_id = _safe_label(payload.get("run_id"), "run id")
        return cls(root=root, run_id=run_id)

    @property
    def path(self) -> Path:
        return self.root / _STATE_FILE

    def checkpoint(
        self,
        phase: str,
        checkpoint: str,
        *,
        recovery_point: str | None = None,
        test_summary: dict[str, Any] | None = None,
    ) -> None:
        """Persist one safe checkpoint so an interrupted local run can resume."""
        payload = self.read()
        self._append_checkpoint(
            payload,
            phase=phase,
            checkpoint=checkpoint,
            recovery_point=recovery_point,
            test_summary=test_summary,
        )
        self._write(payload)

    def latest_checkpoint(self) -> dict[str, Any]:
        """Return a copy of the current checkpoint summary."""
        payload = self.read()
        return dict(payload["current"])

    def read(self) -> dict[str, Any]:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise GovernanceStateError("governance recovery state is unreadable") from exc
        _validate_payload(payload)
        return payload

    def _initial_payload(
        self,
        *,
        commit: str,
        database_label: str,
        model_label: str,
        scenario_label: str,
        evidence_root: Path,
    ) -> dict[str, Any]:
        return {
            "version": _VERSION,
            "run_id": self.run_id,
            "commit": _safe_label(commit, "commit"),
            "database_label": _safe_label(database_label, "database label"),
            "model_label": _safe_label(model_label, "model label"),
            "scenario_label": _safe_label(scenario_label, "scenario label"),
            "evidence_root": str(evidence_root),
            "current": {},
            "checkpoints": [],
        }

    def _append_checkpoint(
        self,
        payload: dict[str, Any],
        *,
        phase: str,
        checkpoint: str,
        recovery_point: str | None,
        test_summary: dict[str, Any] | None,
    ) -> None:
        entry = {
            "phase": _safe_label(phase, "phase"),
            "checkpoint": _safe_label(checkpoint, "checkpoint"),
            "recovery_point": None
            if recovery_point is None
            else _safe_label(recovery_point, "recovery point"),
            "test_summary": _safe_summary(test_summary or {}),
        }
        checkpoints = payload.get("checkpoints")
        if not isinstance(checkpoints, list):
            raise GovernanceStateError("governance recovery checkpoints are invalid")
        checkpoints.append(entry)
        payload["current"] = entry

    def _write(self, payload: dict[str, Any]) -> None:
        _validate_payload(payload)
        temporary = self.root / f".{_STATE_FILE}.{uuid.uuid4().hex}.tmp"
        try:
            with temporary.open("x", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=True, sort_keys=True, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        finally:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass


def _new_run_id() -> str:
    return f"governance-{datetime.now(UTC):%Y%m%dT%H%M%S%fZ}-{uuid.uuid4().hex[:8]}"


def _external_path(value: Path, field: str) -> Path:
    candidate = Path(value).expanduser().resolve()
    try:
        candidate.relative_to(paths.PROJECT_ROOT.resolve())
    except ValueError:
        return candidate
    raise GovernanceStateError(f"{field} must be outside the repository")


def _safe_label(value: object, field: str) -> str:
    normalized = str(value or "").strip()
    if not _SAFE_LABEL.fullmatch(normalized):
        raise ValueError(f"governance {field} must be a short safe label")
    _reject_sensitive_content(normalized)
    return normalized


def _safe_summary(value: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("governance test summary must be an object")
    return _safe_value(value)


def _safe_value(value: Any) -> Any:
    if isinstance(value, dict):
        safe: dict[str, Any] = {}
        for key, item in value.items():
            normalized_key = str(key).strip().lower().replace("-", "_")
            if any(marker in normalized_key for marker in _FORBIDDEN_KEY_MARKERS):
                raise ValueError("governance state contains a forbidden field")
            if normalized_key.endswith("_token") or normalized_key in {"token", "access_token"}:
                raise ValueError("governance state contains a forbidden field")
            safe[str(key)] = _safe_value(item)
        return safe
    if isinstance(value, list):
        return [_safe_value(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        if isinstance(value, str):
            _reject_sensitive_content(value)
        return value
    raise ValueError("governance test summary contains an unsupported value")


def _reject_sensitive_content(value: str) -> None:
    if _URL_RE.search(value) or _SECRET_VALUE_RE.search(value):
        raise ValueError("governance state contains sensitive content")


def _restrict_windows_acl(root: Path) -> None:
    """Allow only the local account and SYSTEM to read the run directory."""
    if os.name != "nt":
        return
    user = getpass.getuser().strip()
    if not user:
        raise GovernanceStateError("current Windows user is unavailable for governance state")
    commands = (
        ["icacls", str(root), "/inheritance:r"],
        ["icacls", str(root), "/grant:r", f"{user}:(OI)(CI)F", "SYSTEM:(OI)(CI)F"],
        ["icacls", str(root), "/remove:g", "Everyone", "Users", "Authenticated Users"],
    )
    for command in commands:
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            raise GovernanceStateError("could not restrict governance state ACL")


def _validate_payload(payload: object) -> None:
    if not isinstance(payload, dict) or payload.get("version") != _VERSION:
        raise GovernanceStateError("governance recovery state is invalid")
    required = (
        "run_id",
        "commit",
        "database_label",
        "model_label",
        "scenario_label",
        "evidence_root",
        "current",
        "checkpoints",
    )
    if any(key not in payload for key in required):
        raise GovernanceStateError("governance recovery state is invalid")
    _safe_label(payload["run_id"], "run id")
    for key in ("commit", "database_label", "model_label", "scenario_label"):
        _safe_label(payload[key], key)
    _external_path(Path(str(payload["evidence_root"])), "evidence root")
    if not isinstance(payload["current"], dict) or not isinstance(payload["checkpoints"], list):
        raise GovernanceStateError("governance recovery state is invalid")
    for entry in payload["checkpoints"]:
        if not isinstance(entry, dict):
            raise GovernanceStateError("governance recovery state is invalid")
        _safe_label(entry.get("phase"), "phase")
        _safe_label(entry.get("checkpoint"), "checkpoint")
        recovery_point = entry.get("recovery_point")
        if recovery_point is not None:
            _safe_label(recovery_point, "recovery point")
        summary = entry.get("test_summary")
        if not isinstance(summary, dict):
            raise GovernanceStateError("governance recovery state is invalid")
        _safe_summary(summary)
