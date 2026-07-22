"""Run one safe local capability probe for the configured evaluation provider."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
from typing import Any

from agens_novel.artifacts.sink import ensure_evaluation_sink_ready
from agens_novel.evaluation.ledger import (
    EvaluationBudget,
    EvaluationLedger,
    PriceCard,
    evaluation_budget_root,
)
from agens_novel.evaluation.manifest import write_inventory_manifest, write_manifest
from agens_novel.evaluation.model_config import EvaluationModelConfig
from agens_novel.evaluation.provider_probe import probe_provider


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--price-card", type=Path)
    parser.add_argument("--max-total-calls", type=int, default=_limit("AGENS_EVALUATION_MAX_TOTAL_CALLS", 800))
    parser.add_argument("--max-narrator-calls", type=int, default=_limit("AGENS_EVALUATION_MAX_NARRATOR_CALLS", 650))
    parser.add_argument("--max-elapsed-seconds", type=float, default=1800.0)
    parser.add_argument("--hard-cost-limit", type=float)
    parser.add_argument("--reservation-cost", type=float)
    args = parser.parse_args()

    config = EvaluationModelConfig.from_environment()
    write_manifest(config, mode="provider-probe")
    price_card = _load_price_card(args.price_card)
    if args.hard_cost_limit is not None and args.reservation_cost is None:
        raise ValueError("--reservation-cost is required with --hard-cost-limit")
    root = ensure_evaluation_sink_ready()
    if root is None:
        raise RuntimeError("evaluation artifact root is unavailable")
    budget = EvaluationBudget(
        evaluation_budget_root(root),
        max_total_calls=args.max_total_calls,
        max_narrator_calls=args.max_narrator_calls,
        hard_cost_limit=args.hard_cost_limit,
    )
    ledger = EvaluationLedger(
        provider=config.provider,
        model=config.model,
        price_card=price_card,
        max_total_calls=args.max_total_calls,
        max_narrator_calls=args.max_narrator_calls,
        reservation_cost=args.reservation_cost,
        max_elapsed_seconds=args.max_elapsed_seconds,
        shared_budget=budget,
    )
    report = asyncio.run(probe_provider(config, ledger=ledger))
    write_inventory_manifest()
    probes = report["probes"]
    contract_names = {"world_opening", "narrator", "judge"}
    contracts_ok = all(
        bool(probe["strict"])
        for probe in probes
        if str(probe["name"]) in contract_names
    )
    output = {
        "provider": report["provider"],
        "model": report["model"],
        "recommended_transport": report["recommended_transport"],
        "probe_count": len(probes),
        "strict_count": sum(bool(probe["strict"]) for probe in probes),
        "contracts_ok": contracts_ok,
        "call_count": report["ledger"]["call_count"],
        "estimated_cost_known": report["ledger"]["estimated_cost"] is not None,
    }
    print(json.dumps(output, ensure_ascii=False, sort_keys=True))
    return 0 if contracts_ok else 2


def _load_price_card(path: Path | None) -> PriceCard | None:
    if path is None:
        return None
    value: Any = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("price card must be a JSON object")
    return PriceCard(
        effective_date=str(value.get("effective_date") or ""),
        currency=str(value.get("currency") or ""),
        input_per_million=_number_or_none(value.get("input_per_million")),
        output_per_million=_number_or_none(value.get("output_per_million")),
        cached_input_per_million=_number_or_none(value.get("cached_input_per_million")),
    )


def _number_or_none(value: Any) -> float | None:
    if value is None:
        return None
    number = float(value)
    if number < 0:
        raise ValueError("price card rates must be non-negative")
    return number


def _limit(name: str, default: int) -> int:
    value = os.environ.get(name, "").strip()
    return int(value) if value else default


if __name__ == "__main__":
    raise SystemExit(main())
