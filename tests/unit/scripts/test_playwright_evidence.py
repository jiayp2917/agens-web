from __future__ import annotations

import csv
import json
import shutil
import subprocess
from pathlib import Path

import pytest

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


def test_write_playwright_evidence_rejects_a_repository_directory() -> None:
    with pytest.raises(ValueError, match="outside the repository"):
        write_playwright_evidence(ROOT / "output" / "playwright", "blocked", {}, [])


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


def _node_json(script: str) -> dict | list:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is required to execute the browser-audit contract")
    completed = subprocess.run(
        [node, "-e", script],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=ROOT,
    )
    return json.loads(completed.stdout)


def test_playtest_replay_preserves_pass_failure_fallback_duplicate_and_authority_results() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is required to replay browser acceptance fixtures")
    completed = subprocess.run(
        [
            node,
            str(ROOT / "scripts" / "playtest" / "replay_acceptance.cjs"),
            str(ROOT / "tests" / "fixtures" / "playtest_replay" / "acceptance_cases.json"),
        ],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=ROOT,
    )
    results = {item["name"]: item for item in json.loads(completed.stdout)}

    assert results["passed"] == {
        "name": "passed",
        "result": "passed",
        "p0_issues": 0,
        "p1_issues": 0,
        "fallback_count": 0,
        "failed": False,
    }
    assert results["failed_http"]["result"] == "failed_audit"
    assert results["fallback"]["result"] == "failed_or_partial"
    assert results["fallback"]["failed"] is True
    assert results["duplicate_narrative"]["result"] == "failed_content"
    assert results["authority_conflict"]["result"] == "failed_audit"


def test_visible_content_audit_keeps_realm_and_breakthrough_contracts() -> None:
    module_path = json.dumps(str(ROOT / "scripts" / "playtest" / "visible_content_audit.cjs"))
    payload = _node_json(
        f"""
const audit = require({module_path});
console.log(JSON.stringify({{
  worldClaims: audit.narrativeRealmClaims("潮音阁重修课业翱，练气二层根基有了可见标尺。"),
  mixedClaims: audit.narrativeRealmClaims("完成宗门任务后，他突破至练气三层。"),
  playerClaims: audit.narrativeRealmClaims("其筑基初期根基已经稳固。"),
  transitionMatches: audit.narrativeRealmClaims("其在大乘圆满之际成功破境迈入渡劫期。")
    .some((claim) => audit.realmClaimMatchesCurrent(claim, "渡劫初期")),
  stabilizeIntent: audit.hasBreakthroughIntent("闭关温养灵力，稳固渡劫根基"),
  ascensionIntent: audit.hasBreakthroughIntent("正式冲击飞升，承担破境失败风险"),
  clueIntent: audit.hasBreakthroughIntent("寻找飞升线索，补足渡劫准备"),
  fallbackHits: audit.forbiddenHits("模型暂不可用，已转入本地故事继续。"),
  harmlessHits: audit.forbiddenHits("普通叙事提到了 slot_1，但没有内部提示。"),
}}));
"""
    )

    assert payload["worldClaims"] == []
    assert payload["mixedClaims"] == ["练气3层"]
    assert payload["playerClaims"] == ["筑基初期"]
    assert payload["transitionMatches"] is True
    assert payload["stabilizeIntent"] is False
    assert payload["ascensionIntent"] is True
    assert payload["clueIntent"] is False
    assert {"model_unavailable_notice", "local_story_notice"} <= set(payload["fallbackHits"])
    assert payload["harmlessHits"] == ["english_word"]


def test_acceptance_report_preserves_visible_issue_category_and_judge_failure() -> None:
    report_path = json.dumps(str(ROOT / "scripts" / "playtest" / "acceptance_report.cjs"))
    payload = _node_json(
        f"""
const report = require({report_path});
const issues = [];
const issue = report.createIssueCollector(issues);
issue("P1", "visible content issue", {{text: "仅用于脱敏回放"}});
report.auditModelDiagnostics({{turn_index: 1, judge_request_failed: true, judge_status: "judge_failed"}}, "main", issue);
console.log(JSON.stringify(issues));
"""
    )

    assert payload[0]["level"] == "P1"
    assert payload[0]["text"] == "visible content issue"
    assert payload[0]["visible_text"] == "仅用于脱敏回放"
    assert payload[1]["text"] == "judge model request failed; rule-only settlement used"


def test_browser_driver_keeps_slot_strategy_and_content_batch_configuration() -> None:
    driver_path = json.dumps(str(ROOT / "scripts" / "playtest" / "browser_driver.cjs"))
    batch_path = json.dumps(str(ROOT / "scripts" / "local_visible_content_audit.cjs"))
    payload = _node_json(
        f"""
const driver = require({driver_path});
const batch = require({batch_path});
const choices = [
  {{letter: "A", text: "稳步修行"}},
  {{letter: "B", text: "拜访执事"}},
  {{letter: "C", text: "冒险探查"}},
  {{letter: "D", text: "静候机缘"}},
];
console.log(JSON.stringify({{
  fixed: driver.routeIndexForTurn(2, choices, {{}}, {{choiceStrategy: "fixed-c"}}).letter,
  slot: driver.routeIndexForTurn(2, choices, {{}}, {{slotSequence: "BD"}}).letter,
  viewport: driver.parseViewport("1440x1000"),
  slots: driver.parseSlotSequence("A, B C D"),
  runs: batch.buildRuns().map((run) => run.key),
  parsed: batch.parseChildOutput('{{"summary":{{"result":"passed"}}}}'),
}}));
"""
    )

    assert payload["fixed"] == "C"
    assert payload["slot"] == "D"
    assert payload["viewport"] == {"width": 1440, "height": 1000}
    assert payload["slots"] == "ABCD"
    assert payload["runs"] == [
        "base-cycle-20",
        "route-a-20",
        "route-b-20",
        "route-c-20",
        "route-d-20",
        "mixed-player-60",
        "double-click-1",
    ]
    assert payload["parsed"] == {"summary": {"result": "passed"}}


def test_legacy_playtest_exports_delegate_to_the_split_modules() -> None:
    legacy_path = json.dumps(str(ROOT / "scripts" / "local_visible_playtest.cjs"))
    visible_path = json.dumps(str(ROOT / "scripts" / "playtest" / "visible_content_audit.cjs"))
    payload = _node_json(
        f"""
const legacy = require({legacy_path});
const visible = require({visible_path});
console.log(JSON.stringify({{
  sameNarrativeHelper: legacy.narrativeRealmClaims === visible.narrativeRealmClaims,
  redacted: legacy.redactEvidence({{api_key: "not-a-real-key", narrative: "safe"}}),
}}));
"""
    )

    assert payload["sameNarrativeHelper"] is True
    assert payload["redacted"] == {"api_key": "[redacted]", "narrative": "safe"}
