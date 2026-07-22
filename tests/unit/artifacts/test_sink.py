"""Tests for the external-only evaluation artifact sink."""

from __future__ import annotations

import json
import os
import time

import pytest

from agens_novel import paths
from agens_novel.artifacts import sink, store


def test_product_store_is_a_noop_without_evaluation_mode(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("AGENS_EVALUATION_MODE", raising=False)
    monkeypatch.setattr(paths, "PROJECT_ROOT", tmp_path / "repo")

    written = store.write_output("narrator", "run-1", "ordinary response")

    assert str(written) == os.devnull
    assert not (tmp_path / "repo" / "runtime" / "artifacts").exists()


def test_evaluation_store_has_no_input_snapshot_writer() -> None:
    assert not hasattr(store, "write_input_snapshot")


def test_evaluation_root_must_be_outside_repository(tmp_path, monkeypatch) -> None:
    project_root = tmp_path / "repo"
    project_root.mkdir()
    monkeypatch.setattr(paths, "PROJECT_ROOT", project_root)
    monkeypatch.setenv("AGENS_EVALUATION_MODE", "1")
    monkeypatch.setenv("AGENS_ARTIFACT_ROOT", str(project_root / "evidence"))

    with pytest.raises(sink.ArtifactPolicyError, match="outside the repository"):
        sink.ensure_evaluation_sink_ready()


def test_evaluation_root_rejects_existing_input_snapshots(tmp_path, monkeypatch) -> None:
    project_root = tmp_path / "repo"
    external_root = tmp_path / "evidence"
    project_root.mkdir()
    external_root.mkdir()
    (external_root / "input.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(paths, "PROJECT_ROOT", project_root)
    monkeypatch.setenv("AGENS_EVALUATION_MODE", "1")
    monkeypatch.setenv("AGENS_ARTIFACT_ROOT", str(external_root))
    monkeypatch.setattr(sink, "_restrict_windows_acl", lambda _root: None)

    with pytest.raises(sink.ArtifactPolicyError, match="forbidden input snapshots"):
        sink.ensure_evaluation_sink_ready()


def test_create_evaluation_run_root_is_unique_and_external(tmp_path, monkeypatch) -> None:
    project_root = tmp_path / "repo"
    parent = tmp_path / "evidence"
    project_root.mkdir()
    monkeypatch.setattr(paths, "PROJECT_ROOT", project_root)
    monkeypatch.setattr(sink, "_restrict_windows_acl", lambda _root: None)

    first_id, first = sink.create_evaluation_run_root(parent, label="canary")
    second_id, second = sink.create_evaluation_run_root(parent, label="canary")

    assert first_id != second_id
    assert first != second
    assert first.is_dir() and second.is_dir()


def test_evaluation_writes_redacted_response_only_to_external_root(tmp_path, monkeypatch) -> None:
    project_root = tmp_path / "repo"
    external_root = tmp_path / "evidence"
    project_root.mkdir()
    monkeypatch.setattr(paths, "PROJECT_ROOT", project_root)
    monkeypatch.setenv("AGENS_EVALUATION_MODE", "1")
    monkeypatch.setenv("AGENS_ARTIFACT_ROOT", str(external_root))
    monkeypatch.setattr(sink, "_restrict_windows_acl", lambda _root: None)

    response = (
        "provider_key=fake-test-key Bearer test-token-12345678 "
        "sk-exampletoken123 https://provider.invalid/v1"
    )
    path = store.write_output("narrator", "run-2", response)
    audit = store.write_audit(
        "narrator",
        "run-2",
        {
            "base_url": "https://provider.invalid/v1",
            "session_token": "fake-session-token",
            "usage": {"prompt_tokens": 5, "completion_tokens": 7, "total_tokens": 12},
        },
    )

    assert path.is_file()
    assert audit.is_file()
    stored_response = path.read_text(encoding="utf-8")
    stored_audit = audit.read_text(encoding="utf-8")
    assert "fake-test-key" not in stored_response
    assert "test-token-12345678" not in stored_response
    assert "sk-exampletoken123" not in stored_response
    assert "provider.invalid" not in stored_response
    assert "provider.invalid" not in stored_audit
    assert "fake-session-token" not in stored_audit
    assert json.loads(stored_audit)["usage"] == {
        "prompt_tokens": 5,
        "completion_tokens": 7,
        "total_tokens": 12,
    }
    assert not (project_root / "runtime" / "artifacts").exists()


def test_cleanup_is_dry_run_until_explicitly_confirmed(tmp_path) -> None:
    expired = tmp_path / "expired.json"
    expired.write_text("{}", encoding="utf-8")
    old_time = time.time() - 31 * 24 * 60 * 60
    os.utime(expired, (old_time, old_time))

    dry_run = sink.cleanup_expired(tmp_path, retention_days=30)
    deleted = sink.cleanup_expired(tmp_path, retention_days=30, confirm=True)

    assert dry_run == {
        "enabled": True,
        "candidate_count": 1,
        "deleted_count": 0,
        "dry_run": True,
    }
    assert deleted["deleted_count"] == 1
    assert not expired.exists()


def test_sensitive_marker_scan_reports_only_category_counts(tmp_path) -> None:
    evidence = tmp_path / "evidence.txt"
    evidence.write_text("api_key=fake-value https://provider.invalid/v1", encoding="utf-8")

    counts = sink.sensitive_marker_counts(tmp_path)

    assert counts == {"secret_like": 1, "url_like": 1}
