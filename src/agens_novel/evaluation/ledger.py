"""Non-secret call accounting and hard caps for local provider evaluation."""

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
    """Raised before a paid provider request would exceed a declared cap."""


def evaluation_budget_root(artifact_root: Path) -> Path:
    """Resolve the shared external budget root without mixing it with new evidence."""
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
    if not (root / "evaluation-budget.json").is_file():
        raise EvaluationBudgetExceeded("evaluation budget root must contain an existing ledger")
    return root


def configured_evaluation_limits() -> tuple[int, int]:
    """Return declared evaluation limits without reading credentials."""
    total = _positive_int(os.environ.get("AGENS_EVALUATION_MAX_TOTAL_CALLS"), 800)
    narrator = _positive_int(os.environ.get("AGENS_EVALUATION_MAX_NARRATOR_CALLS"), 650)
    if narrator > total:
        raise EvaluationBudgetExceeded("narrator cap cannot exceed the total provider cap")
    return total, narrator


class EvaluationBudget:
    """A process-safe, external fact ledger for all calls in one evaluation root.

    A reservation is persisted before network traffic.  An interrupted process
    therefore consumes capacity conservatively rather than allowing a later
    process to reset the limits and exceed the declared evaluation budget.
    """

    _VERSION = 1

    def __init__(
        self,
        root: Path,
        *,
        max_total_calls: int,
        max_narrator_calls: int,
        hard_cost_limit: float | None = None,
    ) -> None:
        self.root = root.resolve()
        self.path = self.root / "evaluation-budget.json"
        self.lock_path = self.root / "evaluation-budget.lock"
        self.max_total_calls = max_total_calls
        self.max_narrator_calls = max_narrator_calls
        self.hard_cost_limit = hard_cost_limit
        self.root.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @classmethod
    def open_existing(cls, root: Path) -> EvaluationBudget:
        """Open an existing external ledger using its recorded immutable limits."""
        path = root.resolve() / "evaluation-budget.json"
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise EvaluationBudgetExceeded("evaluation budget state is unreadable") from exc
        if not isinstance(value, dict):
            raise EvaluationBudgetExceeded("evaluation budget state is invalid")
        cls._validate_state(value)
        return cls(
            root,
            max_total_calls=int(value["max_total_calls"]),
            max_narrator_calls=int(value["max_narrator_calls"]),
            hard_cost_limit=_optional_float(value.get("hard_cost_limit")),
        )

    def reserve(self, agent: str, *, estimated_cost: float | None = None) -> str:
        """Persist one global reservation before the provider request starts."""
        with self._locked_state() as state:
            if int(state["reserved_total"]) >= int(state["max_total_calls"]):
                raise EvaluationBudgetExceeded("provider request cap reached")
            if agent == "narrator" and int(state["reserved_narrator"]) >= int(
                state["max_narrator_calls"]
            ):
                raise EvaluationBudgetExceeded("narrator request cap reached")
            cost = _non_negative_cost(estimated_cost)
            hard_limit = state.get("hard_cost_limit")
            if hard_limit is not None and float(state["reserved_cost"]) + cost > float(hard_limit):
                raise EvaluationBudgetExceeded("provider cost cap would be exceeded")
            state["reserved_total"] = int(state["reserved_total"]) + 1
            if agent == "narrator":
                state["reserved_narrator"] = int(state["reserved_narrator"]) + 1
            state["reserved_cost"] = float(state["reserved_cost"]) + cost
            sequence = int(state["sequence"]) + 1
            state["sequence"] = sequence
            self._write_state(state)
            return f"global-{sequence:04d}"

    def summary(self) -> dict[str, int | float | None]:
        """Return aggregate capacity facts without request content."""
        with self._locked_state() as state:
            return {
                "max_total_calls": int(state["max_total_calls"]),
                "max_narrator_calls": int(state["max_narrator_calls"]),
                "hard_cost_limit": _optional_float(state.get("hard_cost_limit")),
                "reserved_total": int(state["reserved_total"]),
                "reserved_narrator": int(state["reserved_narrator"]),
                "reserved_cost": float(state["reserved_cost"]),
            }

    def upgrade_limits(
        self,
        *,
        max_total_calls: int,
        max_narrator_calls: int,
        reason: str,
    ) -> dict[str, int | float | None]:
        """Increase a persisted cap without resetting recorded provider usage.

        Evaluation limits are normally immutable. A release owner may explicitly
        authorize a larger envelope, but the old cap and reason remain in the
        external ledger so a later process cannot silently rewrite history.
        """
        safe_reason = str(reason or "").strip()
        if not safe_reason or len(safe_reason) > 160:
            raise ValueError("budget upgrade reason must be a short non-empty identifier")
        requested_total = int(max_total_calls)
        requested_narrator = int(max_narrator_calls)
        with self._locked_state() as state:
            self._validate_state(state)
            previous_total = int(state["max_total_calls"])
            previous_narrator = int(state["max_narrator_calls"])
            if requested_total < previous_total or requested_narrator < previous_narrator:
                raise EvaluationBudgetExceeded("evaluation budget limits may only increase")
            if requested_total < int(state["reserved_total"]) or requested_narrator < int(
                state["reserved_narrator"]
            ):
                raise EvaluationBudgetExceeded("evaluation budget cannot be lower than recorded usage")
            if requested_total == previous_total and requested_narrator == previous_narrator:
                return self._summary_from_state(state)
            state["max_total_calls"] = requested_total
            state["max_narrator_calls"] = requested_narrator
            history = state.setdefault("limit_history", [])
            if not isinstance(history, list):
                raise EvaluationBudgetExceeded("evaluation budget history is invalid")
            history.append(
                {
                    "previous_total_calls": previous_total,
                    "previous_narrator_calls": previous_narrator,
                    "max_total_calls": requested_total,
                    "max_narrator_calls": requested_narrator,
                    "reason": safe_reason,
                }
            )
            self._write_state(state)
            return self._summary_from_state(state)

    def _initialize(self) -> None:
        with self._locked_state() as state:
            if state:
                self._validate_limits(state)
                return
            self._write_state(
                {
                    "version": self._VERSION,
                    "max_total_calls": self.max_total_calls,
                    "max_narrator_calls": self.max_narrator_calls,
                    "hard_cost_limit": self.hard_cost_limit,
                    "reserved_total": 0,
                    "reserved_narrator": 0,
                    "reserved_cost": 0.0,
                    "sequence": 0,
                }
            )

    def _validate_limits(self, state: dict[str, Any]) -> None:
        expected = {
            "version": self._VERSION,
            "max_total_calls": self.max_total_calls,
            "max_narrator_calls": self.max_narrator_calls,
            "hard_cost_limit": self.hard_cost_limit,
        }
        actual = {key: state.get(key) for key in expected}
        if actual != expected:
            raise EvaluationBudgetExceeded("evaluation budget configuration does not match its manifest")

    @staticmethod
    def _validate_state(state: dict[str, Any]) -> None:
        required = {
            "version",
            "max_total_calls",
            "max_narrator_calls",
            "reserved_total",
            "reserved_narrator",
            "reserved_cost",
        }
        if not required.issubset(state):
            raise EvaluationBudgetExceeded("evaluation budget state is invalid")

    @staticmethod
    def _summary_from_state(state: dict[str, Any]) -> dict[str, int | float | None]:
        return {
            "max_total_calls": int(state["max_total_calls"]),
            "max_narrator_calls": int(state["max_narrator_calls"]),
            "hard_cost_limit": _optional_float(state.get("hard_cost_limit")),
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
            raise EvaluationBudgetExceeded("evaluation budget state is invalid")
        return value

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


def _optional_float(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) else None


def _non_negative_cost(value: float | None) -> float:
    if value is None:
        return 0.0
    numeric = float(value)
    if numeric < 0:
        raise ValueError("estimated cost must be non-negative")
    return numeric


def _positive_int(value: str | None, default: int) -> int:
    if value is None or not str(value).strip():
        return default
    try:
        numeric = int(str(value))
    except ValueError as exc:
        raise EvaluationBudgetExceeded("evaluation budget limit must be an integer") from exc
    if numeric < 1:
        raise EvaluationBudgetExceeded("evaluation budget limit must be positive")
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
    """Reserve provider calls before dispatch and report reproducible metrics."""

    def __init__(
        self,
        *,
        provider: str,
        model: str,
        price_card: PriceCard | None = None,
        max_total_calls: int = 800,
        max_narrator_calls: int = 650,
        cost_limit: float | None = None,
        reservation_cost: float | None = None,
        max_elapsed_seconds: float | None = None,
        shared_budget: EvaluationBudget | None = None,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        self.provider = provider
        self.model = model
        self.price_card = price_card
        self.max_total_calls = max_total_calls
        self.max_narrator_calls = max_narrator_calls
        self.cost_limit = cost_limit
        self.reservation_cost = _non_negative_cost(reservation_cost)
        self.max_elapsed_seconds = max_elapsed_seconds
        self.shared_budget = shared_budget
        self._clock = clock
        self._started_at = clock()
        self._calls: list[EvaluationCall] = []
        self._reserved_total = 0
        self._reserved_narrator = 0

    def reserve(self, agent: str) -> str:
        """Spend a request budget slot before sending traffic to a provider."""
        if self.max_elapsed_seconds is not None and self.elapsed_seconds >= self.max_elapsed_seconds:
            raise EvaluationBudgetExceeded("provider evaluation time cap reached")
        if self._reserved_total >= self.max_total_calls:
            raise EvaluationBudgetExceeded("provider request cap reached")
        if agent == "narrator" and self._reserved_narrator >= self.max_narrator_calls:
            raise EvaluationBudgetExceeded("narrator request cap reached")
        request_id = (
            self.shared_budget.reserve(agent, estimated_cost=self.reservation_cost)
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
        """Record a reserved call and fail before later requests exceed cost."""
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
        if self.cost_limit is not None and estimate is not None:
            current_cost = self.total_estimated_cost or 0.0
            if current_cost + estimate > self.cost_limit:
                raise EvaluationBudgetExceeded("provider cost cap would be exceeded")
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
