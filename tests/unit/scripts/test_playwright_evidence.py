from __future__ import annotations

import csv
import json

from scripts import playwright_evidence
from scripts.playwright_evidence import write_playwright_evidence


def test_write_playwright_evidence_outputs_parseable_files(tmp_path) -> None:
    paths = write_playwright_evidence(
        tmp_path,
        "local 20 turn",
        {"total_turns": 1, "fallback_count": 0},
        [
            {
                "turn_index": 1,
                "choice": "A",
                "http_status": 200,
                "fallback": False,
                "turn_count": 1,
                "elapsed_ms": 1234,
                "choices_count": 4,
                "note": "ok",
            }
        ],
    )

    payload = json.loads(open(paths["json"], encoding="utf-8").read())
    assert payload["summary"]["total_turns"] == 1
    assert payload["turns"][0]["fallback"] is False

    ndjson_rows = [
        json.loads(line)
        for line in open(paths["ndjson"], encoding="utf-8").read().splitlines()
    ]
    assert ndjson_rows[0]["turn_count"] == 1

    with open(paths["csv"], encoding="utf-8-sig", newline="") as fp:
        rows = list(csv.DictReader(fp))
    assert rows[0]["choice"] == "A"


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
