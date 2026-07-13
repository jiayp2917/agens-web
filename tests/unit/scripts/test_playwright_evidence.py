from __future__ import annotations

import csv
import json
from pathlib import Path

from scripts import playwright_evidence
from scripts.playwright_evidence import write_playwright_evidence

ROOT = Path(__file__).resolve().parents[3]


def test_write_playwright_evidence_outputs_parseable_files(tmp_path) -> None:
    paths = write_playwright_evidence(
        tmp_path,
        "local 20 turn",
        {
            "total_turns": 1,
            "issues": [{"level": "P1", "text": "visible issue"}],
            "fallback_count": 0,
            "start_fallback": False,
            "start_model_ok": True,
            "start_choices_count": 4,
            "start_world_name_set": True,
            "start_chronicle_count": 3,
            "start_initial_situation_set": True,
        },
        [
            {
                "turn_index": 1,
                "phase": "main",
                "choice": "A",
                "choice_letter": "A",
                "http_status": 200,
                "fallback": False,
                "game_over": False,
                "finale": False,
                "turn_count": 1,
                "elapsed_ms": 1234,
                "choices_count": 4,
                "status_age": "18岁",
                "status_realm": "练气2层",
                "forbidden_hits": ["history_suppression_notice"],
                "narrator_status": "incomplete_output",
                "judge_status": "",
                "narrator_elapsed_ms": 900,
                "judge_elapsed_ms": 200,
                "repair_elapsed_ms": 100,
                "repaired_output": True,
                "retried_after_incomplete_output": True,
                "narrator_incomplete_output": True,
                "contract_missing_narrative": False,
                "contract_missing_state_update": True,
                "contract_choices_count_ok": False,
                "prompt_chars": 1200,
                "game_state_chars": 300,
                "history_count": 6,
                "prompt_tokens": 500,
                "completion_tokens": 80,
                "total_tokens": 580,
                "note": "ok",
            }
        ],
    )

    payload = json.loads(open(paths["json"], encoding="utf-8").read())
    assert payload["summary"]["total_turns"] == 1
    assert payload["summary"]["start_fallback"] is False
    assert payload["summary"]["start_model_ok"] is True
    assert payload["summary"]["start_choices_count"] == 4
    assert payload["summary"]["start_world_name_set"] is True
    assert payload["summary"]["start_chronicle_count"] == 3
    assert payload["summary"]["start_initial_situation_set"] is True
    assert payload["issues"] == [{"level": "P1", "text": "visible issue"}]
    assert payload["turns"][0]["fallback"] is False

    ndjson_rows = [
        json.loads(line)
        for line in open(paths["ndjson"], encoding="utf-8").read().splitlines()
    ]
    assert ndjson_rows[0]["turn_count"] == 1

    with open(paths["csv"], encoding="utf-8-sig", newline="") as fp:
        rows = list(csv.DictReader(fp))
    assert rows[0]["choice"] == "A"
    assert rows[0]["phase"] == "main"
    assert rows[0]["choice_letter"] == "A"
    assert rows[0]["game_over"] == "False"
    assert rows[0]["status_age"] == "18岁"
    assert rows[0]["status_realm"] == "练气2层"
    assert rows[0]["forbidden_hits"] == "[\"history_suppression_notice\"]"
    assert rows[0]["narrator_elapsed_ms"] == "900"
    assert rows[0]["narrator_status"] == "incomplete_output"
    assert rows[0]["repair_elapsed_ms"] == "100"
    assert rows[0]["retried_after_incomplete_output"] == "True"
    assert rows[0]["narrator_incomplete_output"] == "True"
    assert rows[0]["contract_missing_state_update"] == "True"
    assert rows[0]["contract_choices_count_ok"] == "False"
    assert rows[0]["prompt_chars"] == "1200"
    assert rows[0]["prompt_tokens"] == "500"


def test_write_playwright_evidence_keeps_nested_objects_parseable(tmp_path) -> None:
    paths = write_playwright_evidence(
        tmp_path,
        "nested",
        {"metadata": {"raw": object()}},
        [{"turn_index": 1, "note": {"raw": object()}}],
    )

    payload = json.loads(open(paths["json"], encoding="utf-8").read())
    assert isinstance(payload["summary"]["metadata"], dict)
    assert isinstance(payload["turns"][0]["note"], dict)
    assert isinstance(payload["turns"][0]["note"]["raw"], str)


def test_write_playwright_evidence_csv_preserves_selected_choice_alias(tmp_path) -> None:
    paths = write_playwright_evidence(
        tmp_path,
        "choice alias",
        {"total_turns": 1},
        [
            {
                "turn_index": 1,
                "selected_choice": "沿山路拜访药谷弟子",
                "http_status": 200,
                "fallback": False,
                "turn_count": 1,
                "elapsed_ms": 100,
                "choices_count": 4,
            }
        ],
    )

    with open(paths["csv"], encoding="utf-8-sig", newline="") as fp:
        rows = list(csv.DictReader(fp))
    assert rows[0]["choice"] == "沿山路拜访药谷弟子"


def test_playwright_evidence_cli_writes_sanitized_outputs(tmp_path, monkeypatch, capsys) -> None:
    source = tmp_path / "source.json"
    out_dir = tmp_path / "out"
    source.write_text(
        json.dumps({
            "summary": {"total_turns": 1},
            "turns": [{"turn_index": 1, "fallback": True, "note": "stopped"}],
        }),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "playwright_evidence.py",
            "--input",
            str(source),
            "--output-dir",
            str(out_dir),
            "--name",
            "../bad name",
        ],
    )

    assert playwright_evidence.main() == 0
    paths = json.loads(capsys.readouterr().out)
    assert all(str(out_dir.resolve()) in value for value in paths.values())
    assert all(".." not in str(value) for value in paths.values())
    assert json.loads(open(paths["json"], encoding="utf-8").read())["summary"]["total_turns"] == 1


def test_playwright_evidence_cli_preserves_top_level_issues(tmp_path, monkeypatch, capsys) -> None:
    source = tmp_path / "strict-source.json"
    out_dir = tmp_path / "out"
    source.write_text(
        json.dumps({
            "summary": {"total_turns": 1},
            "issues": [{"level": "P1", "text": "visible repeat"}],
            "turns": [{"turn_index": 1, "fallback": False}],
        }),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "playwright_evidence.py",
            "--input",
            str(source),
            "--output-dir",
            str(out_dir),
            "--name",
            "strict-source",
        ],
    )

    assert playwright_evidence.main() == 0
    paths = json.loads(capsys.readouterr().out)
    payload = json.loads(open(paths["json"], encoding="utf-8").read())
    assert payload["issues"] == [{"level": "P1", "text": "visible repeat"}]


def test_content_audit_playtest_treats_p1_as_failed_content_gate() -> None:
    source = (ROOT / "scripts" / "local_visible_playtest.cjs").read_text(encoding="utf-8")

    assert "CONTENT_AUDIT_FAIL_ON_P1" in source
    assert 'summary.result = "failed_content"' in source


def test_visible_playtest_golden_strategy_uses_real_profile_controls_and_breakthroughs() -> None:
    source = (ROOT / "scripts" / "local_visible_playtest.cjs").read_text(encoding="utf-8")

    assert 'normalized === "golden"' in source
    assert "configureGoldenProfile(page)" in source
    assert "root_bone: 7" in source
    assert "comprehension: 7" in source
    assert "luck: 7" in source
    assert "willpower: 3" in source
    assert "hasBreakthroughIntent(choice.text)" in source


def test_content_audit_playtest_allows_terminal_turn_without_choices() -> None:
    source = (ROOT / "scripts" / "local_visible_playtest.cjs").read_text(encoding="utf-8")

    assert "const terminalTurn = Boolean(turnRecord.game_over || turnRecord.finale);" in source
    assert "!terminalTurn && ((afterSnapshot.choices || []).length !== 4" in source
    assert 'summary.result = "passed_terminal"' in source
    assert "summary.p1_issues > 0" in source


def test_content_audit_batch_continues_p1_only_runs_but_fails_summary() -> None:
    source = (ROOT / "scripts" / "local_visible_content_audit.cjs").read_text(encoding="utf-8")

    assert "p1OnlyFailure" in source
    assert "completed_with_p1" in source
    assert "batch.p1_issues += p1Issues" in source


def test_content_audit_issues_keep_category_when_payload_has_visible_text() -> None:
    source = (ROOT / "scripts" / "local_visible_playtest.cjs").read_text(encoding="utf-8")

    assert "record.visible_text = record.text" in source
    assert "delete record.text" in source
    assert "issues.push({ ...record, level, text })" in source
    assert "issues.push({ level, text, ...data })" not in source


def test_content_audit_flags_judge_failed_as_p1() -> None:
    source = (ROOT / "scripts" / "local_visible_playtest.cjs").read_text(encoding="utf-8")

    assert 'judge_request_failed: judgeStatus === "judge_failed"' in source
    assert "summary.judge_failed_count" in source
    assert "judge model request failed; rule-only settlement used" in source
    assert "auditModelDiagnostics(turnRecord" in source


def test_content_audit_visible_text_heuristics_are_not_broad_brace_scans() -> None:
    source = (ROOT / "scripts" / "local_visible_playtest.cjs").read_text(encoding="utf-8")

    assert "json_like_object" in source
    assert "state_delta|state_update|character|world|meta|choices" in source
    assert "/[{][\\s\\S]*[}]/u" not in source
    assert "function chineseNumber" in source


def test_content_audit_forbids_chinese_fallback_notices() -> None:
    source = (ROOT / "scripts" / "local_visible_playtest.cjs").read_text(encoding="utf-8")

    assert "model_unavailable_notice" in source
    assert "local_story_notice" in source
    assert "heaven_disorder_notice" in source
    assert "upstream_model_notice" in source
    assert "basic_rule_settlement_notice" in source
    assert "模型(?:暂)?不可用" in source
    assert "本地故事继续" in source
    assert "quoted_choice_fragment" in source


def test_content_audit_does_not_exempt_internal_save_slot_names() -> None:
    source = (ROOT / "scripts" / "local_visible_playtest.cjs").read_text(encoding="utf-8")

    assert "slot_\\d+" not in source


def test_content_audit_recomputes_issue_counts_after_writer_failure() -> None:
    source = (ROOT / "scripts" / "local_visible_playtest.cjs").read_text(encoding="utf-8")

    assert "function updateIssueCounts(summary, issues)" in source
    assert 'issue("P0", "strict evidence writer failed"' in source
    assert "updateIssueCounts(summary, issues);" in source
    assert 'summary.result = "failed_or_partial";' in source


def test_content_audit_does_not_treat_previous_latest_as_new_turn() -> None:
    source = (ROOT / "scripts" / "local_visible_playtest.cjs").read_text(encoding="utf-8")

    assert "function chronicleSignature" in source
    assert "non-fallback turn produced no new visible chronicle entry" in source
    assert "return latest.length ? latest : after.slice(-1)" not in source
    assert "所需|准备|底蕴|线索|打听|寻找|静候|机缘" in source
