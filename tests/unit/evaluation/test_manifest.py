"""Tests for non-secret, reproducible evaluation manifests."""

from __future__ import annotations

from agens_novel import paths
from agens_novel.artifacts import sink
from agens_novel.evaluation.manifest import build_manifest, write_manifest
from agens_novel.evaluation.model_config import EvaluationModelConfig
from agens_novel.evaluation.scenarios import canonical_v3_scenarios


def _config(tmp_path, monkeypatch) -> EvaluationModelConfig:
    monkeypatch.setenv("AGENS_EVALUATION_MODE", "1")
    monkeypatch.setenv("AGENS_ARTIFACT_ROOT", str(tmp_path / "evidence"))
    monkeypatch.setenv("AGENS_EVALUATION_PROVIDER", "DeepSeek")
    monkeypatch.setenv("AGENS_EVALUATION_MODEL", "deepseek-v4-flash")
    monkeypatch.setenv("AGENS_EVALUATION_BASE_URL", "https://provider.invalid/v1")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-evaluation-key")
    monkeypatch.setattr(sink, "_restrict_windows_acl", lambda _root: None)
    return EvaluationModelConfig.from_environment()


def test_manifest_contains_reproducible_safe_metadata(tmp_path, monkeypatch) -> None:
    project_root = tmp_path / "repo"
    for relative in (
        "pyproject.toml",
        "uv.lock",
        "src/agens_novel/agents/narrator/nodes.py",
        "src/agens_novel/agents/world_builder/nodes.py",
        "src/agens_novel/agents/judge/nodes.py",
        "src/agens_novel/engine/rule_contracts.py",
        "src/agens_novel/engine/turn_rules.py",
        "src/agens_novel/rule_rng.py",
        "src/agens_novel/engine/story_catalog.py",
    ):
        path = project_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(relative, encoding="utf-8")
    monkeypatch.setattr(paths, "PROJECT_ROOT", project_root)
    config = _config(tmp_path, monkeypatch)

    manifest = build_manifest(
        config,
        mode="formal-v3",
        story_version=3,
        scenarios=canonical_v3_scenarios(),
    )

    assert manifest["contracts"]["narrator"] == "NarratorEnvelopeV1"
    assert manifest["hashes"]["prompts"]
    assert manifest["scenarios"][0]["run_seed"] == "v3-eval-frontier-high-steady-000"
    assert "base_url" not in str(manifest)
    assert "test-evaluation-key" not in str(manifest)


def test_manifest_writes_redacted_inventory_only_to_external_root(tmp_path, monkeypatch) -> None:
    config = _config(tmp_path, monkeypatch)

    write_manifest(config, mode="provider-probe")

    inventory = sink.external_inventory(tmp_path / "evidence")
    assert inventory["file_count"] >= 2
    assert sink.sensitive_marker_counts(tmp_path / "evidence") == {
        "secret_like": 0,
        "url_like": 0,
    }
