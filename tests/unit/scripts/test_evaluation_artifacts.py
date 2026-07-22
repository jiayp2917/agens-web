"""Tests for browser evidence isolation in evaluation mode."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HELPER = "./scripts/evaluation_artifacts.cjs"


def test_browser_artifacts_require_an_external_root(tmp_path) -> None:
    environment = {**os.environ, "AGENS_EVALUATION_MODE": "1"}
    external = tmp_path / "evidence"
    environment["AGENS_ARTIFACT_ROOT"] = str(external)

    outside = _node(
        "const path=require('path');const {browserArtifactDir}=require(process.argv[1]);"
        "const result=browserArtifactDir(process.cwd());"
        "console.log(JSON.stringify({outside:path.relative(process.cwd(),result).startsWith('..')}));",
        environment,
    )
    assert json.loads(outside.stdout)["outside"] is True

    environment["AGENS_ARTIFACT_ROOT"] = str(ROOT / "runtime" / "evidence")
    inside = _node(
        "const {browserArtifactDir}=require(process.argv[1]);"
        "try{browserArtifactDir(process.cwd());console.log('accepted')}catch{console.log('rejected')}",
        environment,
    )
    assert inside.stdout.strip() == "rejected"


def _node(script: str, environment: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["node", "-e", script, HELPER],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        check=True,
        text=True,
    )
