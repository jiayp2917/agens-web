"""Run one resumable local model qualification without storing provider content."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy.engine import make_url

from agens_novel.artifacts import sink
from agens_novel.evaluation.governance_state import GovernanceRunStateV1

ROOT = Path(__file__).resolve().parents[1]
_PROVIDERS = {"agens", "deepseek"}
_TRANSPORTS = {"json_schema", "json_object"}
_SAFE_SUMMARY_KEYS = {
    "accepted",
    "call_count",
    "narrator_call_count",
    "turns_completed",
    "turns_requested",
    "strict",
    "opening_strict",
    "fallback",
    "repair",
    "recovery",
    "p0_issues",
    "p1_issues",
}


@dataclass(frozen=True)
class QualificationPhase:
    name: str
    command: tuple[str, ...]


def main() -> int:
    args = _arguments()
    state, evidence_root = _open_state(args)
    phases = _phases(args, evidence_root)
    if args.dry_run:
        planned = _record_dry_run(state, phases)
        print(
            json.dumps(
                {
                    "run_id": state.run_id,
                    "provider": args.provider,
                    "phase_count": len(phases),
                    "planned_phases": planned,
                    "dry_run": True,
                    "accepted": False,
                },
                ensure_ascii=True,
                sort_keys=True,
            )
        )
        return 0
    environment = _evaluation_environment(args, evidence_root)
    failed: list[str] = []

    for phase in phases:
        if _phase_passed(state, phase.name):
            continue
        state.checkpoint(phase.name, "started", recovery_point=phase.name)
        summary = _run_phase(phase, environment)
        accepted = bool(summary.pop("accepted", False))
        state.checkpoint(
            phase.name,
            "passed" if accepted else "failed",
            recovery_point="next_phase" if accepted else phase.name,
            test_summary=summary,
        )
        if not accepted:
            failed.append(phase.name)

    print(
        json.dumps(
            {
                "run_id": state.run_id,
                "provider": args.provider,
                "phase_count": len(phases),
                "failed_phases": failed,
                "accepted": not failed,
            },
            ensure_ascii=True,
            sort_keys=True,
        )
    )
    return 0 if not failed else 2


def _phase_passed(state: GovernanceRunStateV1, phase: str) -> bool:
    checkpoints = state.read().get("checkpoints")
    if not isinstance(checkpoints, list):
        return False
    for entry in reversed(checkpoints):
        if isinstance(entry, dict) and entry.get("phase") == phase:
            return entry.get("checkpoint") == "passed"
    return False


def _record_dry_run(
    state: GovernanceRunStateV1,
    phases: tuple[QualificationPhase, ...],
) -> list[str]:
    """Record planned work without treating it as a provider qualification."""
    planned: list[str] = []
    for phase in phases:
        if _phase_passed(state, phase.name):
            continue
        state.checkpoint(
            phase.name,
            "planned",
            recovery_point=phase.name,
            test_summary={"mode": "dry_run"},
        )
        planned.append(phase.name)
    return planned


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", required=True, choices=sorted(_PROVIDERS))
    parser.add_argument("--transport", default="json_object", choices=sorted(_TRANSPORTS))
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--artifact-parent", type=Path)
    parser.add_argument("--resume-state", type=Path)
    parser.add_argument("--port", type=int, default=8100)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if bool(args.artifact_parent) == bool(args.resume_state):
        parser.error("provide exactly one of --artifact-parent or --resume-state")
    _validate_local_database(args.database_url)
    return args


def _open_state(args: argparse.Namespace) -> tuple[GovernanceRunStateV1, Path]:
    if args.resume_state:
        state = GovernanceRunStateV1.open(args.resume_state)
        return state, Path(str(state.read()["evidence_root"])).resolve()

    evidence_root = Path(args.artifact_parent).resolve()
    state = GovernanceRunStateV1.create(
        evidence_root / "qualification-state",
        commit=_git_commit(),
        database_label=_database_label(args.database_url),
        model_label=args.provider,
        scenario_label="v2_v3",
        evidence_root=evidence_root,
    )
    return state, evidence_root


def _evaluation_environment(args: argparse.Namespace, evidence_root: Path) -> dict[str, str]:
    environment = os.environ.copy()
    environment.update(
        {
            "AGENS_EVALUATION_MODE": "1",
            "AGENS_EVALUATION_PROVIDER": args.provider,
            "AGENS_EVALUATION_RESPONSE_MODE": args.transport,
            "AGENS_EVALUATION_ARTIFACT_PARENT": str(evidence_root),
            "AGENS_ENV": "development",
            "PYTHONPATH": str(ROOT / "src"),
        }
    )
    if args.provider == "agens":
        environment.pop("DEEPSEEK_API_KEY", None)
    else:
        environment.pop("AGNES_API_KEY", None)
    return environment


def _phases(args: argparse.Namespace, evidence_root: Path) -> tuple[QualificationPhase, ...]:
    canary = _chrome_phase(
        "opening_canary",
        args,
        evidence_root,
        scenario="high_steady",
        story_version=2,
        turns=0,
        opening_only=True,
    )
    smoke = _chrome_phase(
        "v2_smoke", args, evidence_root, scenario="high_steady", story_version=2, turns=20
    )
    v3 = tuple(
        _chrome_phase(
            f"v3_{scenario}", args, evidence_root, scenario=scenario, story_version=3, turns=90
        )
        for scenario in ("high_steady", "low_risk", "middle_mixed")
    )
    post_arc = _chrome_phase(
        "v3_post_arc", args, evidence_root, scenario="middle_mixed", story_version=3, turns=95
    )
    benchmark = QualificationPhase(
        "frozen_benchmark",
        (sys.executable, str(ROOT / "scripts" / "run_frozen_benchmark.py"), "run"),
    )
    return (canary, smoke, *v3, post_arc, benchmark)


def _chrome_phase(
    name: str,
    args: argparse.Namespace,
    evidence_root: Path,
    *,
    scenario: str,
    story_version: int,
    turns: int,
    opening_only: bool = False,
) -> QualificationPhase:
    command = [
        sys.executable,
        str(ROOT / "scripts" / "run_chrome_evaluation.py"),
        "--provider",
        args.provider,
        "--transport",
        args.transport,
        "--scenario",
        scenario,
        "--story-version",
        str(story_version),
        "--database-url",
        args.database_url,
        "--artifact-parent",
        str(evidence_root),
        "--port",
        str(args.port),
        "--turns",
        str(turns),
        "--record-only",
        "--name",
        name,
    ]
    if opening_only:
        command.append("--opening-only")
    if scenario == "middle_mixed":
        command.extend(
            (
                "--viewport",
                "390x844",
                "--save-load-turn",
                "45",
                "--refresh-probe",
                "--double-click-probe",
                "--conflict-probe",
            )
        )
    return QualificationPhase(name, tuple(command))


def _run_phase(phase: QualificationPhase, environment: dict[str, str]) -> dict[str, Any]:
    command = list(phase.command)
    overlay: dict[str, str] = {}
    if phase.name == "frozen_benchmark":
        run_id, artifact_root = sink.create_evaluation_run_root(
            Path(environment["AGENS_EVALUATION_ARTIFACT_PARENT"]),
            label="frozen-benchmark",
        )
        overlay = {
            "AGENS_ARTIFACT_ROOT": str(artifact_root),
            "AGENS_EVALUATION_RUN_LABEL": run_id,
        }
    result = subprocess.run(
        command,
        cwd=ROOT,
        env={**environment, **overlay},
        capture_output=True,
        text=True,
        check=False,
    )
    report = _safe_child_summary(result.stdout)
    return {"accepted": result.returncode == 0 and bool(report.get("accepted")), "exit_code": result.returncode, **report}


def _safe_child_summary(stdout: str) -> dict[str, Any]:
    for line in reversed(stdout.splitlines()):
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return {
                key: value
                for key, value in payload.items()
                if key in _SAFE_SUMMARY_KEYS and isinstance(value, (bool, int, float, str))
            }
    return {}


def _validate_local_database(raw_url: str) -> None:
    url = make_url(raw_url)
    host = str(url.host or "").lower()
    database = str(url.database or "").lower()
    if not url.drivername.startswith("postgresql") or host not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("qualification requires an isolated local PostgreSQL database")
    if database != "agens_web_local":
        raise ValueError("qualification database must be agens_web_local")


def _database_label(raw_url: str) -> str:
    return str(make_url(raw_url).database or "")


def _git_commit() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError("could not identify qualification commit")
    return result.stdout.strip()


if __name__ == "__main__":
    raise SystemExit(main())
