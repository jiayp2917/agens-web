from __future__ import annotations

import pytest

from agens_novel.evaluation.release_state import ReleaseRunStateV1


def test_release_state_is_external_and_preserves_safe_checkpoints(tmp_path, monkeypatch) -> None:
    from agens_novel.artifacts import sink

    monkeypatch.setattr(sink, "_restrict_windows_acl", lambda _root: None)
    state = ReleaseRunStateV1.create(
        tmp_path / "external",
        label="release",
        commit="82062a2",
        budget_root=tmp_path / "budget",
    )

    state.checkpoint("offline-gates", status="passed", details={"test_count": 71})

    assert state.read()["commit"] == "82062a2"
    assert state.read()["checkpoints"][-1]["details"]["test_count"] == 71


def test_release_state_rejects_sensitive_checkpoint_keys(tmp_path, monkeypatch) -> None:
    from agens_novel.artifacts import sink

    monkeypatch.setattr(sink, "_restrict_windows_acl", lambda _root: None)
    state = ReleaseRunStateV1.create(
        tmp_path / "external",
        label="release",
        commit="82062a2",
        budget_root=tmp_path / "budget",
    )

    with pytest.raises(ValueError, match="forbidden"):
        state.checkpoint("offline-gates", status="passed", details={"api_key": "forbidden"})


def test_release_state_reopens_and_skips_only_the_latest_pass(tmp_path, monkeypatch) -> None:
    from agens_novel.artifacts import sink

    monkeypatch.setattr(sink, "_restrict_windows_acl", lambda _root: None)
    state = ReleaseRunStateV1.create(
        tmp_path / "external",
        label="release",
        commit="82062a2",
        budget_root=tmp_path / "budget",
    )
    state.checkpoint("chrome-agens-v3-high", status="passed")

    reopened = ReleaseRunStateV1.open(state.path)

    assert reopened.run_id == state.run_id
    assert reopened.is_passed("chrome-agens-v3-high") is True
    reopened.checkpoint("chrome-agens-v3-high", status="failed")
    assert reopened.is_passed("chrome-agens-v3-high") is False
