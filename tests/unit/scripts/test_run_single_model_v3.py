"""Tests for the resumable single-model v3 Chrome orchestrator."""

from __future__ import annotations

import importlib.util
import json
import sys
from argparse import Namespace
from pathlib import Path
from unittest.mock import Mock

from agens_novel.evaluation.release_state import ReleaseRunStateV1

ROOT = Path(__file__).resolve().parents[3]
_SPEC = importlib.util.spec_from_file_location(
    "run_single_model_v3",
    ROOT / "scripts" / "run_single_model_v3.py",
)
assert _SPEC is not None and _SPEC.loader is not None
runner = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = runner
_SPEC.loader.exec_module(runner)


def test_single_model_plans_cover_desktop_mobile_and_post_arc() -> None:
    plans = runner._selected_plans("all")

    assert [plan.key for plan in plans] == ["high_steady", "low_risk", "middle_mixed"]
    assert plans[0].double_click_probe is True
    assert plans[1].conflict_probe is True
    assert plans[2].viewport == "390x844"
    assert plans[2].turns == 95


def test_single_model_command_uses_one_named_database_per_scenario(tmp_path, monkeypatch) -> None:
    from agens_novel.artifacts import sink

    monkeypatch.setattr(sink, "_restrict_windows_acl", lambda _root: None)
    state = ReleaseRunStateV1.create(
        tmp_path / "external",
        label="single-model",
        commit="82062a2",
        budget_root=tmp_path / "budget",
    )
    args = Namespace(
        database_url_template="postgresql+psycopg://evaluation@127.0.0.1:55432/agens_web_{scenario}_chrome_eval",
        transport="json_schema",
        timeout_seconds=1800,
    )

    command = runner._scenario_command(args, state, runner._selected_plans("middle_mixed")[0], port=8112)

    assert any("agens_web_middle_mixed_chrome_eval" in item for item in command)
    assert "--record-only" in command
    assert command[command.index("--turns") + 1] == "95"
    assert command[command.index("--viewport") + 1] == "390x844"


def test_public_result_ignores_non_json_process_output() -> None:
    assert runner._public_result("noise\n{\"accepted\": true}\n") == {"accepted": True}
    assert runner._public_result("noise") == {}


def test_single_model_runner_does_not_launch_an_already_accepted_scenario(
    tmp_path, monkeypatch, capsys
) -> None:
    from agens_novel.artifacts import sink

    monkeypatch.setattr(sink, "_restrict_windows_acl", lambda _root: None)
    state = ReleaseRunStateV1.create(
        tmp_path / "external",
        label="single-model",
        commit="82062a2",
        budget_root=tmp_path / "budget",
    )
    state.checkpoint(
        "chrome-agens-v3-high_steady",
        status="passed",
        details={"turns_completed": 90},
    )
    args = Namespace(scenario="high_steady", port_base=8110)
    run = Mock()
    monkeypatch.setattr(runner, "_arguments", lambda: args)
    monkeypatch.setattr(runner, "_open_or_create_state", lambda _args: state)
    monkeypatch.setattr(runner, "_configure_evaluation_environment", lambda _state: None)
    monkeypatch.setattr(runner, "write_inventory_manifest", lambda: None)
    monkeypatch.setattr(runner.subprocess, "run", run)

    assert runner.main() == 0
    assert run.call_count == 0

    summary = json.loads(capsys.readouterr().out)
    assert summary["accepted"] is True
    assert summary["passed_count"] == 1
