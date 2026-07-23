"""Run one safe local capability probe for the configured evaluation provider."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from agens_novel.artifacts.sink import ensure_evaluation_sink_ready
from agens_novel.evaluation.cli_utils import environment_limit, load_price_card
from agens_novel.evaluation.ledger import (
    EvaluationBudget,
    EvaluationLedger,
    evaluation_budget_root,
)
from agens_novel.evaluation.manifest import write_inventory_manifest, write_manifest
from agens_novel.evaluation.model_config import EvaluationModelConfig
from agens_novel.evaluation.provider_probe import probe_provider


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--price-card", type=Path)
    parser.add_argument(
        "--max-total-calls",
        type=int,
        default=environment_limit("AGENS_EVALUATION_MAX_TOTAL_CALLS", 800),
    )
    parser.add_argument(
        "--max-narrator-calls",
        type=int,
        default=environment_limit("AGENS_EVALUATION_MAX_NARRATOR_CALLS", 650),
    )
    parser.add_argument("--max-elapsed-seconds", type=float, default=1800.0)
    parser.add_argument("--hard-cost-limit", type=float)
    parser.add_argument("--reservation-cost", type=float)
    args = parser.parse_args()

    config = EvaluationModelConfig.from_environment()
    write_manifest(config, mode="provider-probe")
    price_card = load_price_card(args.price_card)
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

if __name__ == "__main__":
    raise SystemExit(main())
