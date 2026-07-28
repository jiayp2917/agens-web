"""Non-network checks for the isolated headed-Chrome orchestrator."""

from __future__ import annotations

import importlib.util
import json
import os
from argparse import Namespace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from agens_novel.evaluation.scenarios import canonical_v3_scenarios

ROOT = Path(__file__).resolve().parents[3]
_SPEC = importlib.util.spec_from_file_location(
    "run_chrome_evaluation",
    ROOT / "scripts" / "run_chrome_evaluation.py",
)
assert _SPEC is not None and _SPEC.loader is not None
runner = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(runner)


def _args(provider: str = "agens") -> Namespace:
    return Namespace(
        provider=provider,
        transport="json_schema",
        scenario="high_steady",
        story_version=3,
        database_url="postgresql+psycopg://evaluation@127.0.0.1:55432/agens_web_chrome_eval",
        port=8100,
        turns=90,
        opening_only=False,
        timeout_seconds=1800,
        save_load_turn=0,
        refresh_probe=False,
        double_click_probe=False,
        conflict_probe=False,
        viewport="1440x1000",
        record_only=False,
        release_state=None,
    )


def test_chrome_evaluation_only_accepts_named_local_databases() -> None:
    runner._validate_database_url(_args().database_url)
    with pytest.raises(ValueError, match="isolated local"):
        runner._validate_database_url("postgresql://evaluation@db.internal/agens_web_chrome_eval")
    with pytest.raises(ValueError, match="database name"):
        runner._validate_database_url("postgresql://evaluation@127.0.0.1/agens_web_test")


def test_chrome_evaluation_reserves_a_unique_artifact_root(tmp_path, monkeypatch) -> None:
    from agens_novel.artifacts import sink

    monkeypatch.setattr(sink, "_restrict_windows_acl", lambda _root: None)
    monkeypatch.delenv("AGENS_EVALUATION_MODE", raising=False)
    monkeypatch.delenv("AGENS_ARTIFACT_ROOT", raising=False)

    first_id, first = runner._prepare_artifact_root(tmp_path / "evidence", label="agens-smoke")
    second_id, second = runner._prepare_artifact_root(tmp_path / "evidence", label="agens-smoke")

    assert first_id != second_id
    assert first != second
    assert first.is_dir() and second.is_dir()
    assert "AGENS_EVALUATION_MODE" not in os.environ
    assert "AGENS_ARTIFACT_ROOT" not in os.environ


def test_orchestrator_summary_uses_the_external_child_root(tmp_path, monkeypatch) -> None:
    from agens_novel.artifacts import sink

    monkeypatch.setattr(sink, "_restrict_windows_acl", lambda _root: None)
    monkeypatch.setenv("AGENS_EVALUATION_MODE", "1")
    monkeypatch.delenv("AGENS_ARTIFACT_ROOT", raising=False)
    monkeypatch.delenv("AGENS_EVALUATION_RUN_LABEL", raising=False)

    path = runner._write_orchestrator_summary(
        tmp_path / "external-evidence",
        "deepseek-opening",
        {"result": "passed", "turns_completed": 0},
    )

    assert path.is_file()
    assert path.is_relative_to(tmp_path / "external-evidence")
    assert "AGENS_ARTIFACT_ROOT" not in os.environ
    assert "AGENS_EVALUATION_RUN_LABEL" not in os.environ


def test_browser_process_receives_no_provider_key(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("AGNES_API_KEY", "fake-agens-key")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "fake-deepseek-key")
    scenario = canonical_v3_scenarios()[0]

    environment = runner._browser_environment(
        _args(),
        tmp_path / "evidence",
        "agens-high-steady-test",
        scenario,
    )

    assert "AGNES_API_KEY" not in environment
    assert "DEEPSEEK_API_KEY" not in environment
    assert environment["AGENS_PLAYTEST_SLOT_SEQUENCE"] == "A" * 90
    assert environment["AGENS_PLAYTEST_CANONICAL_SCENARIO"] == scenario.key
    assert environment["AGENS_PLAYTEST_STORY_VERSION"] == "3"
    assert environment["AGENS_PLAYTEST_VIEWPORT"] == "1440x1000"
    assert environment["AGENS_PLAYTEST_URL"].endswith(":8100/")
    assert environment["AGENS_PLAYTEST_SAVE_LOAD_TURN"] == "0"
    assert environment["AGENS_PLAYTEST_POST_LOAD_TURNS"] == "0"
    assert environment["AGENS_PLAYTEST_DOUBLE_CLICK_PROBE"] == "0"
    assert environment["AGENS_PLAYTEST_OPENING_ONLY"] == "0"


def test_server_environment_can_enable_record_only_v2_evaluation(tmp_path) -> None:
    args = _args()
    args.story_version = 2
    args.record_only = True

    environment = runner._server_environment(args, tmp_path / "evidence", "agens-test")

    assert environment["AGENS_EVALUATION_STORY_VERSION"] == "2"
    assert environment["AGENS_EVALUATION_RECORD_ONLY"] == "1"


def test_opening_only_browser_environment_disables_persisted_turn_audit(tmp_path) -> None:
    args = _args()
    args.turns = 0
    args.opening_only = True

    environment = runner._browser_environment(
        args,
        tmp_path / "evidence",
        "agens-opening-test",
        canonical_v3_scenarios()[0],
    )

    assert environment["AGENS_PLAYTEST_OPENING_ONLY"] == "1"
    assert environment["AGENS_PLAYTEST_REQUIRE_PERSISTED_AUDIT"] == "0"


def test_backend_process_keeps_only_the_selected_provider_key(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("AGNES_API_KEY", "fake-agens-key")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "fake-deepseek-key")

    agens = runner._server_environment(_args("agens"), tmp_path / "evidence", "agens-test")
    deepseek_args = _args("deepseek")
    deepseek_args.transport = "json_object"
    deepseek = runner._server_environment(deepseek_args, tmp_path / "evidence", "deepseek-test")

    assert "AGNES_API_KEY" in agens
    assert "DEEPSEEK_API_KEY" not in agens
    assert agens["AGENS_START_MODEL_WORLD"] == "1"
    assert "DEEPSEEK_API_KEY" in deepseek
    assert "AGNES_API_KEY" not in deepseek


def test_browser_summary_is_decoded_as_utf8_not_the_windows_console_encoding() -> None:
    payload = runner._final_json(runner._decode_browser_stdout(b'{"summary":{"result":"passed"}}'))

    assert payload["summary"]["result"] == "passed"


def test_chrome_acceptance_requires_clean_exact_turn_summary() -> None:
    result = {
        "result": "passed",
        "turns_completed": 20,
        "p0_issues": 0,
        "p1_issues": 0,
        "strict": True,
        "opening_strict": True,
        "fallback": 0,
        "repair": 0,
        "recovery": 0,
        "authority_match": True,
        "accepted_turns": [{}] * 20,
        "exit_code": 0,
    }

    assert runner._acceptance_passed(result, turns_requested=20)
    assert not runner._acceptance_passed({**result, "turns_completed": 23}, turns_requested=20)
    assert not runner._acceptance_passed({**result, "authority_match": False}, turns_requested=20)
    assert not runner._acceptance_passed({**result, "strict": False}, turns_requested=20)
    assert not runner._acceptance_passed({**result, "opening_strict": False}, turns_requested=20)


def test_chrome_opening_only_acceptance_requires_zero_clean_strict_opening() -> None:
    result = {
        "result": "passed",
        "turns_completed": 0,
        "p0_issues": 0,
        "p1_issues": 0,
        "opening_strict": True,
        "fallback": 0,
        "repair": 0,
        "recovery": 0,
        "accepted_turns": [],
        "exit_code": 0,
    }

    assert runner._acceptance_passed(result, turns_requested=0, opening_only=True)
    assert not runner._acceptance_passed({**result, "turns_completed": 1}, turns_requested=0, opening_only=True)
    assert not runner._acceptance_passed({**result, "p0_issues": 1}, turns_requested=0, opening_only=True)
    assert not runner._acceptance_passed({**result, "opening_strict": False}, turns_requested=0, opening_only=True)


def test_v3_chrome_acceptance_requires_rule_owned_arc_summary() -> None:
    result = {
        "result": "passed",
        "turns_completed": 95,
        "p0_issues": 0,
        "p1_issues": 0,
        "strict": True,
        "opening_strict": True,
        "fallback": 0,
        "repair": 0,
        "recovery": 0,
        "authority_match": True,
        "accepted_turns": [{}] * 95,
        "exit_code": 0,
        "story_status": "post_arc",
        "story_resolution": "resolved",
        "post_arc_turns": 5,
        "commitment_count": 2,
        "commitment_statuses": ["fulfilled", "fulfilled"],
        "recent_motif_count": 5,
        "recent_motifs_unique": True,
        "consequence_count": 30,
        "route_consequences_have_dimensions": True,
    }

    assert runner._acceptance_passed(
        result,
        turns_requested=95,
        story_version=3,
        scenario="middle_mixed",
    )
    assert not runner._acceptance_passed(
        {**result, "story_resolution": "failed"},
        turns_requested=95,
        story_version=3,
        scenario="middle_mixed",
    )


def test_chrome_checkpoint_phase_is_stable_per_provider_scenario_and_version() -> None:
    assert runner._checkpoint_phase("agens", "high_steady", 3) == "chrome-agens-v3-high_steady"


def test_chrome_evidence_joins_only_matching_persisted_and_visible_turns() -> None:
    evidence = runner._accepted_turn_evidence(
        [
            {
                "turn": 1,
                "slot": "A",
                "strict": {"first_pass": True, "final": True},
                "timing_ms": {"end_to_end": 10, "full_response": 8, "ttft": None},
            },
            {"turn": 2},
        ],
        [
            {
                "turn": 1,
                "slot": "A",
                "event_id": "frontier-v3-1-record",
                "narrative": "已接受正文。",
                "choices": ["一", "二", "三", "四"],
                "authority_hash": "hash",
            }
        ],
    )

    assert evidence == [
        {
            "turn": 1,
            "slot": "A",
            "intent_category": "",
            "event_id": "frontier-v3-1-record",
            "motif": "",
            "rule_outcome": "",
            "narrative": "已接受正文。",
            "choices": ["一", "二", "三", "四"],
            "authority_hash": "hash",
            "strict": {"first_pass": True, "final": True},
            "retry": False,
            "repair": False,
            "fallback": False,
            "recovery": False,
            "timing_ms": {"end_to_end": 10, "full_response": 8, "ttft": None},
        }
    ]


def test_strict_summary_uses_per_turn_acceptance() -> None:
    assert runner._strict_summary({"turns_completed": 2, "accepted_live_turns": 2})
    assert not runner._strict_summary({"turns_completed": 2, "accepted_live_turns": 1})


def test_browser_summary_counts_opening_fallback_as_a_failure() -> None:
    payload = {
        "summary": {
            "result": "failed_or_partial",
            "turns_completed": 0,
            "p0_issues": 1,
            "p1_issues": 0,
            "accepted_live_turns": 0,
            "start_fallback": True,
            "start_model_ok": False,
            "fallback_count": 0,
            "repaired_output_count": 0,
            "contract_recovery_count": 0,
            "persisted_turn_audit": {"authority_match": None},
        }
    }
    completed = SimpleNamespace(
        stdout=json.dumps(payload).encode("utf-8"),
        returncode=1,
    )

    with patch.object(runner.subprocess, "run", return_value=completed):
        result = runner._run_browser({}, timeout_seconds=1)

    assert result["fallback"] == 1
    assert result["opening_strict"] is False
    assert result["authority_match"] is None
    assert not runner._acceptance_passed(result, turns_requested=20)
