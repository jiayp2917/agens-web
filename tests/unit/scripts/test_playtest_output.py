"""Tests for transient local browser-output directories."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HELPER = "./scripts/playtest_output.cjs"


def _node(source: str, environment: dict[str, str]) -> dict[str, object]:
    result = subprocess.run(
        ["node", "-e", source, HELPER],
        cwd=ROOT,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)
    assert isinstance(payload, dict)
    return payload


def test_default_browser_output_is_transient_and_outside_repository() -> None:
    payload = _node(
        "const path=require('path');const {browserOutputDir}=require(process.argv[1]);"
        "const output=browserOutputDir(process.cwd());"
        "console.log(JSON.stringify({outside:path.relative(process.cwd(),output).startsWith('..')}));",
        dict(os.environ),
    )

    assert payload == {"outside": True}


def test_configured_browser_output_must_stay_outside_repository(tmp_path: Path) -> None:
    environment = {**os.environ, "AGENS_PLAYTEST_OUTPUT_DIR": str(tmp_path)}
    first = _node(
        "const {browserOutputDir}=require(process.argv[1]);"
        "console.log(JSON.stringify({output:browserOutputDir(process.cwd())}));",
        environment,
    )
    second = _node(
        "const {browserOutputDir}=require(process.argv[1]);"
        "console.log(JSON.stringify({output:browserOutputDir(process.cwd())}));",
        environment,
    )

    assert Path(str(first["output"])).is_relative_to(tmp_path)
    assert first["output"] != second["output"]


def test_repository_output_directory_is_rejected() -> None:
    environment = {**os.environ, "AGENS_PLAYTEST_OUTPUT_DIR": str(ROOT / "output" / "playwright")}
    result = subprocess.run(
        ["node", "-e", "const {browserOutputDir}=require(process.argv[1]);browserOutputDir(process.cwd())", HELPER],
        cwd=ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
