"""Strict evidence writers for headed Chrome / Playwright validation.

The browser driver can collect records in memory and call these helpers at the
end of a run. The JSON file is parseable as one document; NDJSON/CSV provide a
compact audit trail for turn-by-turn checks.
"""

from __future__ import annotations

import csv
import argparse
import json
from pathlib import Path
from typing import Any


def write_playwright_evidence(
    output_dir: str | Path,
    name: str,
    summary: dict[str, Any],
    turns: list[dict[str, Any]],
) -> dict[str, str]:
    """Write strict JSON plus NDJSON/CSV turn summaries.

    Returns absolute file paths keyed by ``json``, ``ndjson`` and ``csv``.
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    safe_name = _safe_name(name)
    payload = {
        "summary": _json_safe(summary),
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
        "choice",
        "http_status",
        "fallback",
        "turn_count",
        "elapsed_ms",
        "choices_count",
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
    return turn.get(field, "")


def _safe_name(name: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in name.strip())
    return cleaned.strip("-") or "playwright-evidence"


def main() -> int:
    parser = argparse.ArgumentParser(description="Write strict Playwright/Chrome evidence files.")
    parser.add_argument("--input", required=True, help="JSON file containing summary and turns.")
    parser.add_argument("--output-dir", default="output/playwright")
    parser.add_argument("--name", required=True)
    args = parser.parse_args()

    raw = json.loads(Path(args.input).read_text(encoding="utf-8"))
    summary = raw.get("summary") if isinstance(raw, dict) else {}
    turns = raw.get("turns") if isinstance(raw, dict) else []
    if not isinstance(summary, dict):
        summary = {}
    if not isinstance(turns, list):
        turns = []
    paths = write_playwright_evidence(args.output_dir, args.name, summary, turns)
    print(json.dumps(paths, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
