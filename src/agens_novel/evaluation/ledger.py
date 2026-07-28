"""Non-secret, record-only accounting for local provider evaluation."""

from __future__ import annotations

import json
import math
import os
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import median
from time import monotonic
from typing import Any

from .. import paths


class EvaluationBudgetExceeded(RuntimeError):
    """Raised when the external evaluation ledger cannot be safely used."""


def evaluation_budget_root(artifact_root: Path) -> Path:
    """Resolve the shared external call-record root without mixing it with evidence."""
    configured = os.environ.get("AGENS_EVALUATION_BUDGET_ROOT", "").strip()
    if not configured:
        return artifact_root.resolve()
    root = Path(configured).expanduser().resolve()
    try:
        root.relative_to(paths.PROJECT_ROOT.resolve())
    except ValueError:
        pass
    else:
        raise EvaluationBudgetExceeded("evaluation budget root must be outside the repository")
    return root


def configured_evaluation_limits() -> tuple[int, int]:
    """Return inert legacy values while callers migrate away from budget caps."""
    return (0, 0)


def evaluation_record_only() -> bool:
    """Local evaluation accounting is always record-only."""
    return True


class EvaluationBudget:
    """A process-safe external call record shared by evaluation processes.

    The historical name and constructor parameters remain temporarily for
    callers outside this change. They are ignored: this object never blocks a
    dispatch based on call counts, cost, or elapsed time.
    """

    _VERSION = 2

    def __init__(
        self,
        root: Path,
        **_legacy_options: object,
    ) -> None:
        self.root = root.resolve()
        self.path = self.root / "evaluation-budget.json"
        self.lock_path = self.root / "evaluation-budget.lock"
        self.root.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @classmethod
    def open_existing(cls, root: Path) -> EvaluationBudget:
        """Open or create the shared call record without resetting its counts."""
        return cls(root)

    def reserve(self, agent: str, *, estimated_cost: float | None = None) -> str:
        """Persist one global request record before the provider request starts."""
        with self._locked_state() as state:
            cost = _non_negative_cost(estimated_cost)
            state["reserved_total"] = int(state["reserved_total"]) + 1
            if agent == "narrator":
                state["reserved_narrator"] = int(state["reserved_narrator"]) + 1
            state["reserved_cost"] = float(state["reserved_cost"]) + cost
            sequence = int(state["sequence"]) + 1
            state["sequence"] = sequence
            self._write_state(state)
            return f"global-{sequence:04d}"

    def summary(self) -> dict[str, int | float | None]:
        """Return aggregate call facts without request content."""
        with self._locked_state() as state:
            return self._summary_from_state(state)

    def _initialize(self) -> None:
        with self._locked_state() as state:
            if state:
                normalized = self._normalize_state(state)
                if normalized != state:
                    self._write_state(normalized)
                return
            self._write_state(
                {
                    "version": self._VERSION,
                    "reserved_total": 0,
                    "reserved_narrator": 0,
                    "reserved_cost": 0.0,
                    "sequence": 0,
                }
            )

    @staticmethod
    def _normalize_state(state: dict[str, Any]) -> dict[str, Any]:
        required = {"reserved_total", "reserved_narrator", "reserved_cost"}
        if not required.issubset(state):
            raise EvaluationBudgetExceeded("evaluation call record is invalid")
        try:
            total = int(state["reserved_total"])
            narrator = int(state["reserved_narrator"])
            cost = float(state["reserved_cost"])
            sequence = int(state.get("sequence", total))
        except (TypeError, ValueError) as exc:
            raise EvaluationBudgetExceeded("evaluation call record is invalid") from exc
        if min(total, narrator, sequence) < 0 or cost < 0:
            raise EvaluationBudgetExceeded("evaluation call record is invalid")
        return {
            "version": EvaluationBudget._VERSION,
            "reserved_total": total,
            "reserved_narrator": narrator,
            "reserved_cost": cost,
            "sequence": sequence,
        }

    @staticmethod
    def _summary_from_state(state: dict[str, Any]) -> dict[str, int | float | None]:
        return {
            "reserved_total": int(state["reserved_total"]),
            "reserved_narrator": int(state["reserved_narrator"]),
            "reserved_cost": float(state["reserved_cost"]),
        }

    @contextmanager
    def _locked_state(self):
        self.lock_path.touch(exist_ok=True)
        with self.lock_path.open("a+b") as handle:
            if handle.tell() == 0:
                handle.write(b"0")
                handle.flush()
            handle.seek(0)
            _lock_file(handle)
            try:
                yield self._read_state()
            finally:
                _unlock_file(handle)

    def _read_state(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise EvaluationBudgetExceeded("evaluation budget state is unreadable") from exc
        if not isinstance(value, dict):
            raise EvaluationBudgetExceeded("evaluation call record is invalid")
        return self._normalize_state(value)

    def _write_state(self, state: dict[str, Any]) -> None:
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(state, ensure_ascii=False, sort_keys=True), encoding="utf-8"
        )
        os.replace(temporary, self.path)


def _lock_file(handle: Any) -> None:
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        return
    import fcntl

    fcntl_module: Any = fcntl
    fcntl_module.flock(handle.fileno(), fcntl_module.LOCK_EX)


def _unlock_file(handle: Any) -> None:
    if os.name == "nt":
        import msvcrt

        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        return
    import fcntl

    fcntl_module: Any = fcntl
    fcntl_module.flock(handle.fileno(), fcntl_module.LOCK_UN)


def _non_negative_cost(value: float | None) -> float:
    if value is None:
        return 0.0
    numeric = float(value)
    if numeric < 0:
        raise ValueError("estimated cost must be non-negative")
    return numeric


@dataclass(frozen=True)
class PriceCard:
    """Dated per-million-token pricing; unknown rates remain unknown."""

    effective_date: str
    currency: str
    input_per_million: float | None = None
    output_per_million: float | None = None
    cached_input_per_million: float | None = None

    def estimate(self, usage: dict[str, int]) -> float | None:
        if self.input_per_million is None or self.output_per_million is None:
            return None
        input_tokens = max(0, int(usage.get("prompt_tokens") or 0))
        output_tokens = max(0, int(usage.get("completion_tokens") or 0))
        return (
            input_tokens * self.input_per_million + output_tokens * self.output_per_million
        ) / 1_000_000


@dataclass(frozen=True)
class EvaluationCall:
    """One request record safe to persist in an evaluation artifact."""

    request_id: str
    agent: str
    provider: str
    model: str
    transport: str
    elapsed_ms: int
    ttft_ms: int | None
    usage: dict[str, int]
    retry: int
    strict: bool
    fallback: bool
    success: bool
    estimated_cost: float | None
    error_code: str
    response_diagnostics: dict[str, object]


class EvaluationLedger:
    """Record provider calls before dispatch and report reproducible metrics."""

    def __init__(
        self,
        *,
        provider: str,
        model: str,
        price_card: PriceCard | None = None,
        shared_budget: EvaluationBudget | None = None,
        clock: Callable[[], float] = monotonic,
        **_legacy_options: object,
    ) -> None:
        self.provider = provider
        self.model = model
        self.price_card = price_card
        self.shared_budget = shared_budget
        self.record_only = True
        self._clock = clock
        self._started_at = clock()
        self._calls: list[EvaluationCall] = []
        self._reserved_total = 0
        self._reserved_narrator = 0

    def reserve(self, agent: str) -> str:
        """Record a request attempt before sending traffic to a provider."""
        request_id = (
            self.shared_budget.reserve(agent)
            if self.shared_budget is not None
            else f"call-{self._reserved_total + 1:04d}"
        )
        self._reserved_total += 1
        if agent == "narrator":
            self._reserved_narrator += 1
        return request_id

    @property
    def elapsed_seconds(self) -> float:
        """Return monotonic evaluation elapsed time without exposing request content."""
        return max(0.0, self._clock() - self._started_at)

    @property
    def call_count(self) -> int:
        """Return the local number of completed provider attempts."""
        return len(self._calls)

    def calls_since(self, index: int) -> tuple[EvaluationCall, ...]:
        """Return safe call metadata recorded after one evaluation boundary."""
        return tuple(self._calls[max(0, index) :])

    def record(
        self,
        *,
        request_id: str,
        agent: str,
        transport: str,
        elapsed_ms: int,
        usage: dict[str, int] | None = None,
        ttft_ms: int | None = None,
        retry: int = 0,
        strict: bool = False,
        fallback: bool = False,
        success: bool = True,
        error_code: str = "",
        response_diagnostics: dict[str, object] | None = None,
    ) -> EvaluationCall:
        """Record a reserved call without changing dispatch eligibility."""
        normalized_usage = _usage(usage)
        estimate = self.price_card.estimate(normalized_usage) if self.price_card else None
        call = EvaluationCall(
            request_id=request_id,
            agent=agent,
            provider=self.provider,
            model=self.model,
            transport=transport,
            elapsed_ms=max(0, int(elapsed_ms)),
            ttft_ms=max(0, int(ttft_ms)) if ttft_ms is not None else None,
            usage=normalized_usage,
            retry=max(0, int(retry)),
            strict=bool(strict),
            fallback=bool(fallback),
            success=bool(success),
            estimated_cost=estimate,
            error_code=str(error_code or ""),
            response_diagnostics=dict(response_diagnostics or {}),
        )
        self._calls.append(call)
        return call

    @property
    def total_estimated_cost(self) -> float | None:
        if self.price_card is None or any(call.estimated_cost is None for call in self._calls):
            return None
        return sum(call.estimated_cost or 0.0 for call in self._calls)

    def summary(self) -> dict[str, Any]:
        """Return aggregate reliability, latency, usage, and cost facts."""
        elapsed = [call.elapsed_ms for call in self._calls]
        ttft = [call.ttft_ms for call in self._calls if call.ttft_ms is not None]
        token_totals = {
            field: sum(call.usage[field] for call in self._calls)
            for field in ("prompt_tokens", "completion_tokens", "total_tokens")
        }
        return {
            "provider": self.provider,
            "model": self.model,
            "call_count": len(self._calls),
            "narrator_call_count": sum(call.agent == "narrator" for call in self._calls),
            "success_count": sum(call.success for call in self._calls),
            "strict_count": sum(call.strict for call in self._calls),
            "fallback_count": sum(call.fallback for call in self._calls),
            "elapsed_ms": _percentiles(elapsed),
            "ttft_ms": _percentiles(ttft) if ttft else {"p50": None, "p95": None, "max": None},
            "usage": token_totals,
            "estimated_cost": self.total_estimated_cost,
            "run_elapsed_ms": int(self.elapsed_seconds * 1000),
            "price_card": asdict(self.price_card) if self.price_card else None,
            "record_only": self.record_only,
            "shared_budget": self.shared_budget.summary() if self.shared_budget else None,
            "calls": [asdict(call) for call in self._calls],
        }


class EvaluationCallObserver:
    """Bridge private LLM request metadata to one evaluation ledger."""

    def __init__(self, ledger: EvaluationLedger) -> None:
        self._ledger = ledger

    def before_request(self, *, agent: str, transport: str, stream: bool) -> dict[str, str]:
        return {
            "request_id": self._ledger.reserve(agent),
            "agent": agent,
            "transport": transport,
            "stream": str(bool(stream)),
        }

    def after_request(
        self,
        ticket: dict[str, str],
        *,
        elapsed_ms: int,
        usage: dict[str, int],
        success: bool,
        error_code: str = "",
        response_diagnostics: dict[str, object] | None = None,
    ) -> None:
        self._ledger.record(
            request_id=ticket["request_id"],
            agent=ticket["agent"],
            transport=ticket["transport"],
            elapsed_ms=elapsed_ms,
            usage=usage,
            success=success,
            error_code=error_code,
            response_diagnostics=response_diagnostics,
        )


def _usage(value: dict[str, int] | None) -> dict[str, int]:
    data = value or {}
    return {
        field: max(0, int(data.get(field) or 0))
        for field in ("prompt_tokens", "completion_tokens", "total_tokens")
    }


def _percentiles(values: list[int]) -> dict[str, int | None]:
    if not values:
        return {"p50": None, "p95": None, "max": None}
    ordered = sorted(values)
    return {
        "p50": int(median(ordered)),
        "p95": ordered[math.ceil(0.95 * len(ordered)) - 1],
        "max": ordered[-1],
    }
