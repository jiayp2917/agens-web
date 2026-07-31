"""Strict evidence writers for headed Chrome / Playwright validation.

The browser driver can collect records in memory and call these helpers at the
end of a run. The JSON file is parseable as one document; NDJSON/CSV provide a
compact audit trail for turn-by-turn checks.
"""

from __future__ import annotations

import argparse
import csv
import json
import tempfile
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parents[1]


def write_playwright_evidence(
    output_dir: str | Path,
    name: str,
    summary: dict[str, Any],
    turns: list[dict[str, Any]],
) -> dict[str, str]:
    """Write strict JSON plus NDJSON/CSV turn summaries.

    Returns absolute file paths keyed by ``json``, ``ndjson`` and ``csv``.
    """
    out = _outside_repository_output_dir(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    safe_name = _safe_name(name)
    issues = summary.get("issues") if isinstance(summary.get("issues"), list) else []
    payload = {
        "summary": _json_safe(summary),
        "issues": _json_safe(issues),
        "turns": [_json_safe(turn) for turn in turns],
    }
    json_path = out / f"{safe_name}.json"
    ndjson_path = out / f"{safe_name}.ndjson"
    csv_path = out / f"{safe_name}.csv"

    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    with ndjson_path.open("w", encoding="utf-8", newline="\n") as fp:
        for turn in payload["turns"]:
            fp.write(json.dumps(turn, ensure_ascii=False, separators=(",", ":")) + "\n")
    _write_turn_csv(csv_path, payload["turns"])

    return {
        "json": str(json_path.resolve()),
        "ndjson": str(ndjson_path.resolve()),
        "csv": str(csv_path.resolve()),
    }


def _write_turn_csv(path: Path, turns: list[dict[str, Any]]) -> None:
    fields = [
        "turn_index",
        "phase",
        "choice_letter",
        "choice",
        "http_status",
        "fallback",
        "game_over",
        "finale",
        "turn_count",
        "elapsed_ms",
        "choices_count",
        "status_age",
        "status_realm",
        "status_lifespan",
        "latest_chronicle_age",
        "latest_chronicle_text",
        "forbidden_count",
        "forbidden_hits",
        "repeated_exact",
        "max_previous_similarity",
        "world_intel_changed",
        "invalid_breakthrough_choices",
        "choice_response_count",
        "narrator_status",
        "judge_status",
        "narrator_elapsed_ms",
        "judge_elapsed_ms",
        "repair_elapsed_ms",
        "repaired_output",
        "retried_after_incomplete_output",
        "narrator_incomplete_output",
        "contract_missing_narrative",
        "contract_missing_state_update",
        "contract_choices_count_ok",
        "prompt_chars",
        "game_state_chars",
        "history_count",
        "prompt_tokens",
        "completion_tokens",
        "total_tokens",
        "note",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as fp:
        writer = csv.DictWriter(fp, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for turn in turns:
            writer.writerow({field: _csv_field(turn, field) for field in fields})


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(val) for key, val in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    try:
        json.dumps(value, ensure_ascii=False)
    except TypeError:
        return str(value)
    return value


def _csv_field(turn: dict[str, Any], field: str) -> Any:
    if field == "choice" and not turn.get("choice"):
        return turn.get("selected_choice", "")
    value = turn.get(field, "")
    if isinstance(value, (dict, list)):
        return json.dumps(_json_safe(value), ensure_ascii=False, separators=(",", ":"))
    return value


def _safe_name(name: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in name.strip())
    return cleaned.strip("-") or "playwright-evidence"


def _outside_repository_output_dir(output_dir: str | Path) -> Path:
    out = Path(output_dir).expanduser().resolve()
    try:
        out.relative_to(_PROJECT_ROOT)
    except ValueError:
        return out
    raise ValueError("Playwright evidence output must be outside the repository")


def main() -> int:
    parser = argparse.ArgumentParser(description="Write strict Playwright/Chrome evidence files.")
    parser.add_argument("--input", required=True, help="JSON file containing summary and turns.")
    parser.add_argument("--output-dir", default=str(Path(tempfile.gettempdir()) / "agens-web-playwright"))
    parser.add_argument("--name", required=True)
    args = parser.parse_args()

    raw = json.loads(Path(args.input).read_text(encoding="utf-8"))
    summary = raw.get("summary") if isinstance(raw, dict) else {}
    turns = raw.get("turns") if isinstance(raw, dict) else []
    if not isinstance(summary, dict):
        summary = {}
    if not isinstance(turns, list):
        turns = []
    if isinstance(raw, dict) and isinstance(raw.get("issues"), list) and not isinstance(summary.get("issues"), list):
        summary = {**summary, "issues": raw["issues"]}
    paths = write_playwright_evidence(args.output_dir, args.name, summary, turns)
    print(json.dumps(paths, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
