"""Run or resume the three pre-registered Agens v3 Chrome scenarios."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agens_novel.evaluation.manifest import write_inventory_manifest, write_manifest
from agens_novel.evaluation.model_config import EvaluationModelConfig
from agens_novel.evaluation.release_state import ReleaseRunStateV1

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class ScenarioPlan:
    key: str
    turns: int
    viewport: str
    save_load_turn: int
    refresh_probe: bool = False
    double_click_probe: bool = False
    conflict_probe: bool = False


_SCENARIO_PLANS = (
    ScenarioPlan("high_steady", turns=90, viewport="1440x1000", save_load_turn=30, double_click_probe=True),
    ScenarioPlan("low_risk", turns=90, viewport="1440x1000", save_load_turn=30, conflict_probe=True),
    ScenarioPlan("middle_mixed", turns=95, viewport="390x844", save_load_turn=45, refresh_probe=True),
)


def main() -> int:
    args = _arguments()
    state = _open_or_create_state(args)
    _configure_evaluation_environment(state)
    plans = _selected_plans(args.scenario)
    results: list[dict[str, Any]] = []

    for index, plan in enumerate(plans):
        phase = f"chrome-agens-v3-{plan.key}"
        checkpoint = state.latest_checkpoint(phase)
        if checkpoint and checkpoint.get("status") == "passed":
            details = checkpoint.get("details")
            safe_details = details if isinstance(details, dict) else {}
            results.append(
                {
                    "scenario": plan.key,
                    "accepted": True,
                    "skipped": True,
                    "turns_requested": plan.turns,
                    "turns_completed": int(safe_details.get("turns_completed") or plan.turns),
                }
            )
            continue
        command = _scenario_command(args, state, plan, port=args.port_base + index)
        completed = subprocess.run(
            command,
            cwd=ROOT,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            check=False,
        )
        result = _public_result(completed.stdout)
        accepted = completed.returncode == 0 and bool(result.get("accepted"))
        if not accepted:
            state.checkpoint(
                phase,
                status="failed",
                details={"exit_code": int(completed.returncode), "accepted": False},
            )
        results.append(
            {
                "scenario": plan.key,
                "accepted": accepted,
                "skipped": bool(result.get("skipped")),
                "turns_requested": plan.turns,
                "turns_completed": int(result.get("turns_completed") or 0),
            }
        )
        if not accepted:
            break

    passed_count = sum(item["accepted"] for item in results)
    accepted = len(results) == len(plans) and passed_count == len(plans)
    summary_phase = "v3-summary" if args.scenario == "all" else f"v3-summary-{args.scenario}"
    state.checkpoint(
        summary_phase,
        status="passed" if accepted else "failed",
        details={
            "scenario_count": len(plans),
            "completed_count": len(results),
            "passed_count": passed_count,
        },
    )
    write_inventory_manifest()
    print(
        json.dumps(
            {
                "run_id": state.run_id,
                "accepted": accepted,
                "scenario_count": len(plans),
                "passed_count": passed_count,
                "resume_state": str(state.path),
            },
            ensure_ascii=True,
            sort_keys=True,
        )
    )
    return 0 if accepted else 2


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-parent", type=Path)
    parser.add_argument("--resume-state", type=Path)
    parser.add_argument("--database-url-template", required=True)
    parser.add_argument("--scenario", choices=("all", *(plan.key for plan in _SCENARIO_PLANS)), default="all")
    parser.add_argument("--transport", choices=("json_schema",), default="json_schema")
    parser.add_argument("--timeout-seconds", type=int, default=1800)
    parser.add_argument("--port-base", type=int, default=8110)
    args = parser.parse_args()
    if bool(args.artifact_parent) == bool(args.resume_state):
        parser.error("provide exactly one of --artifact-parent or --resume-state")
    if "{scenario}" not in args.database_url_template:
        parser.error("--database-url-template must contain {scenario}")
    if args.timeout_seconds < 30:
        parser.error("--timeout-seconds must be at least 30")
    return args


def _open_or_create_state(args: argparse.Namespace) -> ReleaseRunStateV1:
    if args.resume_state:
        return ReleaseRunStateV1.open(args.resume_state)
    if os.environ.get("AGENS_ENV", "").strip().lower() in {"prod", "production"}:
        raise RuntimeError("single-model v3 evaluation is local-only")
    state = ReleaseRunStateV1.create(
        args.artifact_parent,
        label="agens-single-v3",
        commit=_git_commit(),
        budget_root=args.artifact_parent,
    )
    state.checkpoint("manifest", status="created", details={"provider": "agens", "story_version": 3})
    return state


def _configure_evaluation_environment(state: ReleaseRunStateV1) -> None:
    os.environ["AGENS_EVALUATION_MODE"] = "1"
    os.environ["AGENS_ARTIFACT_ROOT"] = str(state.root)
    os.environ["AGENS_EVALUATION_PROVIDER"] = "agens"
    os.environ["AGENS_EVALUATION_RECORD_ONLY"] = "1"
    if not state.is_passed("manifest-written"):
        config = EvaluationModelConfig.from_environment()
        write_manifest(
            config,
            mode="single-model-v3",
            story_version=3,
        )
        state.checkpoint("manifest-written", status="passed", details={"story_version": 3})


def _selected_plans(key: str) -> tuple[ScenarioPlan, ...]:
    if key == "all":
        return _SCENARIO_PLANS
    return tuple(plan for plan in _SCENARIO_PLANS if plan.key == key)


def _scenario_command(
    args: argparse.Namespace,
    state: ReleaseRunStateV1,
    plan: ScenarioPlan,
    *,
    port: int,
) -> list[str]:
    database_url = args.database_url_template.replace("{scenario}", plan.key)
    command = [
        sys.executable,
        str(ROOT / "scripts" / "run_chrome_evaluation.py"),
        "--provider",
        "agens",
        "--transport",
        args.transport,
        "--scenario",
        plan.key,
        "--story-version",
        "3",
        "--database-url",
        database_url,
        "--artifact-parent",
        str(state.root),
        "--port",
        str(port),
        "--turns",
        str(plan.turns),
        "--viewport",
        plan.viewport,
        "--save-load-turn",
        str(plan.save_load_turn),
        "--timeout-seconds",
        str(args.timeout_seconds),
        "--name",
        plan.key,
        "--record-only",
        "--release-state",
        str(state.path),
    ]
    if plan.refresh_probe:
        command.append("--refresh-probe")
    if plan.double_click_probe:
        command.append("--double-click-probe")
    if plan.conflict_probe:
        command.append("--conflict-probe")
    return command


def _public_result(stdout: str) -> dict[str, Any]:
    for line in reversed(str(stdout or "").splitlines()):
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    return {}


def _git_commit() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError("could not identify the local evaluation commit")
    return result.stdout.strip()


if __name__ == "__main__":
    raise SystemExit(main())
