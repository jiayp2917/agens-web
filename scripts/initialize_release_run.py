"""Create a resumable external release state for record-only evaluation."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from agens_novel.evaluation.release_state import ReleaseRunStateV1

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-parent", type=Path, required=True)
    parser.add_argument("--label", default="v3-release")
    args = parser.parse_args()

    state = ReleaseRunStateV1.create(
        args.artifact_parent,
        label=args.label,
        commit=_git_commit(),
        budget_root=args.artifact_parent,
    )
    state.checkpoint("evaluation_ledger", status="recording", details={})
    print(
        json.dumps(
            {
                "run_id": state.run_id,
                "evaluation_accounting": "record_only",
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
