"""Run one frozen benchmark process or anonymize two external result reports."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from agens_novel.artifacts.sink import ensure_evaluation_sink_ready
from agens_novel.evaluation.benchmark import (
    build_blind_review_packet,
    frozen_benchmark_acceptance,
    run_frozen_benchmark,
)
from agens_novel.evaluation.ledger import EvaluationBudget, EvaluationLedger, evaluation_budget_root
from agens_novel.evaluation.manifest import write_inventory_manifest, write_manifest
from agens_novel.evaluation.model_config import EvaluationModelConfig
from agens_novel.evaluation.scenarios import canonical_v3_scenarios


def main() -> int:
    parser = argparse.ArgumentParser()
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("run")
    blind = subcommands.add_parser("blind")
    blind.add_argument("--first", type=Path, required=True)
    blind.add_argument("--second", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "run":
        return _run()
    return _blind(args.first, args.second)


def _run() -> int:
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
    budget = EvaluationBudget(evaluation_budget_root(root))
    report, _path = run_frozen_benchmark(
        config,
        ledger=EvaluationLedger(
            provider=config.provider,
            model=config.model,
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
                "strict_count": report["acceptance"]["strict_count"],
                "p0_issues": report["acceptance"]["p0_issues"],
                "p1_issues": report["acceptance"]["p1_issues"],
                "accepted": report["acceptance"]["accepted"],
                "call_count": report["ledger"]["call_count"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if frozen_benchmark_acceptance(report)["accepted"] else 2


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
if __name__ == "__main__":
    raise SystemExit(main())
