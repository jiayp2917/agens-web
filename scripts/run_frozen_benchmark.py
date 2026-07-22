"""Run one frozen benchmark process or anonymize two external result reports."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from agens_novel.artifacts.sink import ensure_evaluation_sink_ready
from agens_novel.evaluation.benchmark import build_blind_review_packet, run_frozen_benchmark
from agens_novel.evaluation.ledger import (
    EvaluationBudget,
    EvaluationLedger,
    evaluation_budget_root,
)
from agens_novel.evaluation.manifest import write_inventory_manifest, write_manifest
from agens_novel.evaluation.model_config import EvaluationModelConfig
from agens_novel.evaluation.scenarios import canonical_v3_scenarios


def main() -> int:
    parser = argparse.ArgumentParser()
    subcommands = parser.add_subparsers(dest="command", required=True)
    run = subcommands.add_parser("run")
    run.add_argument("--max-total-calls", type=int, default=_limit("AGENS_EVALUATION_MAX_TOTAL_CALLS", 800))
    run.add_argument("--max-narrator-calls", type=int, default=_limit("AGENS_EVALUATION_MAX_NARRATOR_CALLS", 650))
    run.add_argument("--max-elapsed-seconds", type=float, default=1800.0)
    blind = subcommands.add_parser("blind")
    blind.add_argument("--first", type=Path, required=True)
    blind.add_argument("--second", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "run":
        return _run(
            max_total_calls=args.max_total_calls,
            max_narrator_calls=args.max_narrator_calls,
            max_elapsed_seconds=args.max_elapsed_seconds,
        )
    return _blind(args.first, args.second)


def _run(
    *,
    max_total_calls: int,
    max_narrator_calls: int,
    max_elapsed_seconds: float,
) -> int:
    config = EvaluationModelConfig.from_environment()
    write_manifest(
        config,
        mode="frozen-benchmark-v3",
        story_version=3,
        scenarios=canonical_v3_scenarios(),
    )
    root = ensure_evaluation_sink_ready()
    if root is None:
        raise RuntimeError("evaluation artifact root is unavailable")
    budget = EvaluationBudget(
        evaluation_budget_root(root),
        max_total_calls=max_total_calls,
        max_narrator_calls=max_narrator_calls,
    )
    report, _path = run_frozen_benchmark(
        config,
        ledger=EvaluationLedger(
            provider=config.provider,
            model=config.model,
            max_total_calls=max_total_calls,
            max_narrator_calls=max_narrator_calls,
            max_elapsed_seconds=max_elapsed_seconds,
            shared_budget=budget,
        ),
    )
    write_inventory_manifest()
    print(
        json.dumps(
            {
                "provider": report["provider"],
                "model": report["model"],
                "snapshot_count": len(report["results"]),
                "strict_count": sum(bool(item["strict"]) for item in report["results"]),
                "call_count": report["ledger"]["call_count"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


def _blind(first_path: Path, second_path: Path) -> int:
    first = _read_report(first_path)
    second = _read_report(second_path)
    packet, _path = build_blind_review_packet(first, second)
    print(json.dumps({"pair_count": packet["pair_count"]}, ensure_ascii=False, sort_keys=True))
    return 0


def _read_report(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("benchmark report must be a JSON object")
    return value


def _limit(name: str, default: int) -> int:
    value = os.environ.get(name, "").strip()
    return int(value) if value else default


if __name__ == "__main__":
    raise SystemExit(main())
