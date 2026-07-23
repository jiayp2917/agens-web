"""Run one local v2 smoke or v3 canonical evaluation for one provider process."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from agens_novel.artifacts import store
from agens_novel.artifacts.sink import ensure_evaluation_sink_ready
from agens_novel.evaluation.cli_utils import environment_limit, load_price_card
from agens_novel.evaluation.ledger import (
    EvaluationBudget,
    EvaluationLedger,
    evaluation_budget_root,
)
from agens_novel.evaluation.manifest import write_inventory_manifest, write_manifest
from agens_novel.evaluation.model_config import EvaluationModelConfig
from agens_novel.evaluation.playthrough import run_canonical_playthrough
from agens_novel.evaluation.scenarios import canonical_v3_scenarios


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("smoke-v2", "formal-v3"))
    parser.add_argument("--scenario", choices=("all", "high_steady", "low_risk", "middle_mixed"), default="all")
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
    scenarios = _selected_scenarios(args.scenario, smoke=args.mode == "smoke-v2")
    write_manifest(
        config,
        mode=args.mode,
        story_version=2 if args.mode == "smoke-v2" else 3,
        scenarios=tuple(scenarios),
    )
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
    results = [
        run_canonical_playthrough(
            config,
            scenario,
            story_version=2 if args.mode == "smoke-v2" else 3,
            ledger=ledger,
            max_turns=20 if args.mode == "smoke-v2" else 90,
            live_opening=args.mode == "smoke-v2",
            live_judge=args.mode == "smoke-v2",
        )
        for scenario in scenarios
    ]
    accepted = _accepted_smoke(results) if args.mode == "smoke-v2" else _accepted_v3(results)
    report = {
        "mode": args.mode,
        "provider": config.provider,
        "model": config.model,
        "accepted": accepted,
        "results": results,
        "ledger": ledger.summary(),
    }
    run_id = f"{args.mode}-{config.provider}-{config.model}"
    store.write_audit("playthrough_summary", run_id, report)
    write_inventory_manifest()
    output = {
        "mode": args.mode,
        "provider": config.provider,
        "model": config.model,
        "accepted": accepted,
        "scenario_count": len(results),
        "turn_counts": [result["turn_count"] for result in results],
        "narrator_strict": [result["narrator_final_strict"] for result in results],
        "fallback_count": sum(result["fallback_count"] for result in results),
        "call_count": report["ledger"]["call_count"],
        "estimated_cost_known": report["ledger"]["estimated_cost"] is not None,
    }
    print(json.dumps(output, ensure_ascii=False, sort_keys=True))
    return 0 if accepted else 2


def _selected_scenarios(key: str, *, smoke: bool):
    scenarios = canonical_v3_scenarios()
    if smoke:
        return [scenarios[0]]
    if key == "all":
        return list(scenarios)
    return [scenario for scenario in scenarios if scenario.key == key]


def _accepted_smoke(results: list[dict[str, Any]]) -> bool:
    if len(results) != 1:
        return False
    result = results[0]
    return bool(
        result["turn_count"] == 20
        and result["world_opening_event_count"] >= 1
        and result["world_opening_final_strict"] >= 1
        and result["narrator_event_count"] == 20
        and result["narrator_first_pass_strict"] >= 18
        and result["narrator_final_strict"] == 20
        and result["fallback_count"] == 0
        and result["repair_count"] == 0
        and result["recovery_count"] == 0
        and result["authority_mismatch_count"] == 0
        and not result["visible_english"]
        and result["judge_status"] == "ok"
        and not result["notices"]
    )


def _accepted_v3(results: list[dict[str, Any]]) -> bool:
    if len(results) != 3:
        return False
    return all(
        result["turn_count"] > 0
        and result["fallback_count"] == 0
        and result["repair_count"] == 0
        and result["recovery_count"] == 0
        and result["authority_mismatch_count"] == 0
        and result["narrator_final_strict"] == result["turn_count"]
        and len(result["accepted_turns"]) == result["turn_count"]
        and result["story_version_bound"] == 3
        and not result["visible_english"]
        and not result["notices"]
        and (result["game_over"] or result["story_resolution"] in {"resolved", "failed"})
        for result in results
    )

if __name__ == "__main__":
    raise SystemExit(main())
