from __future__ import annotations

import csv
import json

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
