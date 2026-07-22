"""Create a resumable external release state and authorize one budget upgrade."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from agens_novel.evaluation.ledger import EvaluationBudget
from agens_novel.evaluation.release_state import ReleaseRunStateV1

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-parent", type=Path, required=True)
    parser.add_argument("--budget-root", type=Path, required=True)
    parser.add_argument("--label", default="v3-release")
    parser.add_argument("--max-total-calls", type=int, default=950)
    parser.add_argument("--max-narrator-calls", type=int, default=850)
    args = parser.parse_args()

    budget = EvaluationBudget.open_existing(args.budget_root)
    summary = budget.upgrade_limits(
        max_total_calls=args.max_total_calls,
        max_narrator_calls=args.max_narrator_calls,
        reason="authorized_v3_release_evaluation",
    )
    state = ReleaseRunStateV1.create(
        args.artifact_parent,
        label=args.label,
        commit=_git_commit(),
        budget_root=args.budget_root,
    )
    state.checkpoint("budget", status="upgraded", details=summary)
    print(
        json.dumps(
            {
                "run_id": state.run_id,
                "reserved_total": summary["reserved_total"],
                "reserved_narrator": summary["reserved_narrator"],
                "max_total_calls": summary["max_total_calls"],
                "max_narrator_calls": summary["max_narrator_calls"],
            },
            ensure_ascii=True,
            sort_keys=True,
        )
    )
    return 0


def _git_commit() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        raise RuntimeError("could not identify the release commit")
    return result.stdout.strip()


if __name__ == "__main__":
    raise SystemExit(main())
