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


def test_browser_playtest_uses_external_evidence_and_redacts_sensitive_values(tmp_path) -> None:
    script = (ROOT / "scripts" / "local_visible_playtest.cjs").read_text(encoding="utf-8")
    assert '"output/playwright"' not in script

    output = _node(
        "const {redactEvidence}=require(process.argv[1]);"
        "console.log(JSON.stringify(redactEvidence({base_url:'https://provider.invalid/v1',"
        "api_key:'not-a-real-key',narrative:'safe narrative',nested:{token:'test-token-value'}})));",
        {**os.environ, "AGENS_ARTIFACT_ROOT": str(tmp_path / "evidence")},
        helper="./scripts/local_visible_playtest.cjs",
    )
    value = json.loads(output.stdout)
    assert value["base_url"] == "[redacted]"
    assert value["api_key"] == "[redacted]"
    assert value["nested"]["token"] == "[redacted]"
    assert value["narrative"] == "safe narrative"


def _node(
    script: str,
    environment: dict[str, str],
    *,
    helper: str = HELPER,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["node", "-e", script, helper],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        check=True,
        text=True,
    )
