"""Non-secret call accounting and hard caps for local provider evaluation."""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import asdict, dataclass
from statistics import median
from time import monotonic
from typing import Any


class EvaluationBudgetExceeded(RuntimeError):
    """Raised before a paid provider request would exceed a declared cap."""


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
        max_elapsed_seconds: float | None = None,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        self.provider = provider
        self.model = model
        self.price_card = price_card
        self.max_total_calls = max_total_calls
        self.max_narrator_calls = max_narrator_calls
        self.cost_limit = cost_limit
        self.max_elapsed_seconds = max_elapsed_seconds
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
        self._reserved_total += 1
        if agent == "narrator":
            self._reserved_narrator += 1
        return f"call-{self._reserved_total:04d}"

    @property
    def elapsed_seconds(self) -> float:
        """Return monotonic evaluation elapsed time without exposing request content."""
        return max(0.0, self._clock() - self._started_at)

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
    ) -> None:
        self._ledger.record(
            request_id=ticket["request_id"],
            agent=ticket["agent"],
            transport=ticket["transport"],
            elapsed_ms=elapsed_ms,
            usage=usage,
            success=success,
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
