"""Serializable state for a model failure awaiting an explicit player decision."""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from typing import Any

_STAGES = {"opening", "turn", "breakthrough"}
_STATUSES = {"pending", "retrying", "resolved"}


@dataclass(frozen=True)
class PendingModelFailureV1:
    """One frozen request that may be retried, locally expressed, or ended."""

    failure_id: str
    stage: str
    request_no: int
    slot: str
    action: str
    frozen_result: dict[str, Any]
    outcome_hash: str
    rule_rng_counter: int
    base_version: int
    status: str = "pending"
    error_code: str = "llm_error"

    @classmethod
    def create(
        cls,
        *,
        stage: str,
        action: str,
        slot: str,
        frozen_result: dict[str, Any],
        rule_rng_counter: int,
        error_code: str,
    ) -> PendingModelFailureV1:
        if stage not in _STAGES:
            raise ValueError("pending model failure stage is invalid")
        payload = _json_object(frozen_result)
        return cls(
            failure_id=str(uuid.uuid4()),
            stage=stage,
            request_no=1,
            slot=slot if slot in {"A", "B", "C", "D", "breakthrough", "opening"} else "",
            action=str(action or "")[:512],
            frozen_result=payload,
            outcome_hash=_outcome_hash(payload),
            rule_rng_counter=max(0, int(rule_rng_counter or 0)),
            base_version=0,
            error_code=_error_code(error_code),
        )

    @classmethod
    def from_payload(cls, value: Any) -> PendingModelFailureV1 | None:
        if not isinstance(value, dict):
            return None
        stage = str(value.get("stage") or "")
        status = str(value.get("status") or "pending")
        frozen_result = _json_object(value.get("frozen_result"))
        if stage not in _STAGES or status not in _STATUSES or not frozen_result:
            return None
        outcome_hash = str(value.get("outcome_hash") or "")
        if outcome_hash != _outcome_hash(frozen_result):
            return None
        failure_id = str(value.get("failure_id") or "")
        if not failure_id or len(failure_id) > 64:
            return None
        return cls(
            failure_id=failure_id,
            stage=stage,
            request_no=max(1, int(value.get("request_no") or 1)),
            slot=str(value.get("slot") or ""),
            action=str(value.get("action") or "")[:512],
            frozen_result=frozen_result,
            outcome_hash=outcome_hash,
            rule_rng_counter=max(0, int(value.get("rule_rng_counter") or 0)),
            base_version=max(0, int(value.get("base_version") or 0)),
            status=status,
            error_code=_error_code(value.get("error_code")),
        )

    def with_status(self, status: str, *, request_no: int | None = None) -> PendingModelFailureV1:
        if status not in _STATUSES:
            raise ValueError("pending model failure status is invalid")
        value = self.to_dict()
        value.pop("version", None)
        value["status"] = status
        value["request_no"] = max(1, int(request_no or self.request_no))
        return PendingModelFailureV1(**value)

    def with_base_version(self, base_version: int) -> PendingModelFailureV1:
        value = self.to_dict()
        value.pop("version", None)
        value["base_version"] = max(0, int(base_version))
        return PendingModelFailureV1(**value)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": "PendingModelFailureV1",
            "failure_id": self.failure_id,
            "stage": self.stage,
            "request_no": self.request_no,
            "slot": self.slot,
            "action": self.action,
            "frozen_result": self.frozen_result,
            "outcome_hash": self.outcome_hash,
            "rule_rng_counter": self.rule_rng_counter,
            "base_version": self.base_version,
            "status": self.status,
            "error_code": self.error_code,
        }

    def public_summary(self) -> dict[str, Any]:
        return {
            "failure_id": self.failure_id,
            "stage": self.stage,
            "request_no": self.request_no,
            "slot": self.slot,
            "status": self.status,
            "error_code": self.error_code,
        }


def _json_object(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    try:
        normalized = json.loads(json.dumps(value, ensure_ascii=False, sort_keys=True))
    except (TypeError, ValueError):
        return {}
    return normalized if isinstance(normalized, dict) else {}


def _outcome_hash(value: dict[str, Any]) -> str:
    canonical = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _error_code(value: Any) -> str:
    code = str(value or "llm_error")
    return code if code.replace("_", "").isalnum() and len(code) <= 64 else "llm_error"
