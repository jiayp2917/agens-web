"""Non-network coverage for the resumable model qualification orchestrator."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from subprocess import CompletedProcess

import pytest

from agens_novel.evaluation.governance_state import GovernanceRunStateV1

ROOT = Path(__file__).resolve().parents[3]
_SPEC = importlib.util.spec_from_file_location("qualify_model", ROOT / "scripts" / "qualify_model.py")
assert _SPEC is not None and _SPEC.loader is not None
runner = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = runner
_SPEC.loader.exec_module(runner)


def test_qualification_runs_each_independent_phase_and_writes_safe_checkpoints(
    tmp_path, monkeypatch
) -> None:
    from agens_novel.artifacts import sink
    from agens_novel.evaluation import governance_state

    monkeypatch.setattr(sink, "_restrict_windows_acl", lambda _root: None)
    monkeypatch.setattr(governance_state, "_restrict_windows_acl", lambda _root: None)
    commands: list[list[str]] = []

    def fake_run(command, **_kwargs):
        command_list = list(command)
        if command_list[:3] == ["git", "rev-parse", "--short"]:
            return CompletedProcess(command_list, 0, "567254c\n", "")
        commands.append(command_list)
        return CompletedProcess(command_list, 0, '{"accepted":true,"call_count":1}\n', "")

    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "qualify_model.py",
            "--provider",
            "agens",
            "--database-url",
            "postgresql+psycopg://evaluation@127.0.0.1:55432/agens_web_local",
            "--artifact-parent",
            str(tmp_path / "external-evidence"),
        ],
    )

    assert runner.main() == 0
    assert len(commands) == 7
    chrome_commands = [command for command in commands if command[1].endswith("run_chrome_evaluation.py")]
    assert len(chrome_commands) == 6
    opening = next(command for command in chrome_commands if command[command.index("--name") + 1] == "opening_canary")
    assert opening[opening.index("--turns") + 1] == "0"
    assert "--opening-only" in opening
    middle = next(command for command in chrome_commands if command[command.index("--name") + 1] == "v3_middle_mixed")
    assert {"--refresh-probe", "--double-click-probe", "--conflict-probe"}.issubset(middle)
    assert any(command[1].endswith("run_frozen_benchmark.py") for command in commands)

    state_path = next((tmp_path / "external-evidence" / "qualification-state").glob("*/governance-run-state.json"))
    state = GovernanceRunStateV1.open(state_path)
    payload = state.read()
    completed = {
        entry["phase"]: entry["checkpoint"]
        for entry in payload["checkpoints"]
        if entry["phase"] != "created"
    }
    assert set(completed) == {
        "opening_canary",
        "v2_smoke",
        "v3_high_steady",
        "v3_low_risk",
        "v3_middle_mixed",
        "v3_post_arc",
        "frozen_benchmark",
    }
    assert set(completed.values()) == {"passed"}
    assert "prompt" not in json.dumps(payload).lower()


def test_qualification_reuses_passed_checkpoint_without_repeating_the_phase(tmp_path, monkeypatch) -> None:
    from agens_novel.evaluation import governance_state

    monkeypatch.setattr(governance_state, "_restrict_windows_acl", lambda _root: None)
    state = GovernanceRunStateV1.create(
        tmp_path / "external" / "states",
        commit="567254c",
        database_label="agens_web_local",
        model_label="agens",
        scenario_label="v2_v3",
        evidence_root=tmp_path / "external" / "evidence",
    )
    state.checkpoint("opening_canary", "passed")

    assert runner._phase_passed(state, "opening_canary") is True
    assert runner._phase_passed(state, "v2_smoke") is False


def test_dry_run_creates_only_planned_external_checkpoints(tmp_path, monkeypatch) -> None:
    from agens_novel.evaluation import governance_state

    monkeypatch.setattr(governance_state, "_restrict_windows_acl", lambda _root: None)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "qualify_model.py",
            "--provider",
            "agens",
            "--database-url",
            "postgresql+psycopg://evaluation@127.0.0.1:55432/agens_web_local",
            "--artifact-parent",
            str(tmp_path / "external-evidence"),
            "--dry-run",
        ],
    )

    assert runner.main() == 0
    state_path = next(
        (tmp_path / "external-evidence" / "qualification-state").glob(
            "*/governance-run-state.json"
        )
    )
    payload = GovernanceRunStateV1.open(state_path).read()
    entries = [entry for entry in payload["checkpoints"] if entry["phase"] != "created"]
    assert len(entries) == 7
    assert {entry["checkpoint"] for entry in entries} == {"planned"}
    assert all(entry["test_summary"] == {"mode": "dry_run"} for entry in entries)


def test_qualification_rejects_any_database_except_the_local_browser_database() -> None:
    runner._validate_local_database("postgresql+psycopg://evaluation@127.0.0.1:55432/agens_web_local")
    with pytest.raises(ValueError, match="agens_web_local"):
        runner._validate_local_database("postgresql+psycopg://evaluation@127.0.0.1:55432/agens_web_test_01")
    with pytest.raises(ValueError, match="isolated local"):
        runner._validate_local_database("postgresql+psycopg://evaluation@db.internal/agens_web_local")
