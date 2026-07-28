from __future__ import annotations

import json

import pytest

from agens_novel import paths
from agens_novel.evaluation.governance_state import GovernanceRunStateV1, GovernanceStateError


def _create_state(tmp_path, monkeypatch) -> GovernanceRunStateV1:
    from agens_novel.evaluation import governance_state

    monkeypatch.setattr(governance_state, "_restrict_windows_acl", lambda _root: None)
    return GovernanceRunStateV1.create(
        tmp_path / "external" / "runs",
        commit="567254c",
        database_label="agens_web_test_001",
        model_label="agens",
        scenario_label="v3_high_a",
        evidence_root=tmp_path / "external" / "evidence",
    )


def test_governance_state_creates_unique_external_root_and_safe_initial_record(tmp_path, monkeypatch) -> None:
    first = _create_state(tmp_path, monkeypatch)
    second = _create_state(tmp_path, monkeypatch)

    assert first.root != second.root
    assert first.root.parent == (tmp_path / "external" / "runs").resolve()
    assert first.path.is_file()
    assert first.read()["current"] == {
        "phase": "created",
        "checkpoint": "created",
        "recovery_point": None,
        "test_summary": {},
    }


def test_governance_state_retries_a_directory_collision(tmp_path, monkeypatch) -> None:
    from agens_novel.evaluation import governance_state

    monkeypatch.setattr(governance_state, "_restrict_windows_acl", lambda _root: None)
    parent = tmp_path / "external" / "runs"
    parent.mkdir(parents=True)
    (parent / "governance-collision").mkdir()
    run_ids = iter(("governance-collision", "governance-unique"))
    monkeypatch.setattr(governance_state, "_new_run_id", lambda: next(run_ids))

    state = GovernanceRunStateV1.create(
        parent,
        commit="567254c",
        database_label="agens_web_test_001",
        model_label="agens",
        scenario_label="v3_high_a",
        evidence_root=tmp_path / "external" / "evidence",
    )

    assert state.run_id == "governance-unique"


def test_governance_state_rejects_repository_paths_and_sensitive_values(tmp_path, monkeypatch) -> None:
    from agens_novel.evaluation import governance_state

    monkeypatch.setattr(governance_state, "_restrict_windows_acl", lambda _root: None)
    external = tmp_path / "external"
    with pytest.raises(GovernanceStateError, match="outside"):
        GovernanceRunStateV1.create(
            paths.PROJECT_ROOT,
            commit="567254c",
            database_label="db",
            model_label="agens",
            scenario_label="v3",
            evidence_root=external,
        )

    state = _create_state(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="forbidden"):
        state.checkpoint("offline", "passed", test_summary={"api_key": "redacted"})
    with pytest.raises(ValueError, match="sensitive"):
        state.checkpoint("offline", "passed", test_summary={"diagnostic": "https://example.test"})


def test_governance_state_reopens_and_continues_from_latest_checkpoint(tmp_path, monkeypatch) -> None:
    state = _create_state(tmp_path, monkeypatch)
    state.checkpoint(
        "offline_gates",
        "passed",
        recovery_point="before_model_smoke",
        test_summary={"passed": 42, "failed": 0, "duration_ms": 123},
    )

    reopened = GovernanceRunStateV1.open(state.path)

    assert reopened.run_id == state.run_id
    assert reopened.latest_checkpoint() == {
        "phase": "offline_gates",
        "checkpoint": "passed",
        "recovery_point": "before_model_smoke",
        "test_summary": {"passed": 42, "failed": 0, "duration_ms": 123},
    }
    reopened.checkpoint("model_smoke", "started")
    assert reopened.read()["checkpoints"][-1]["phase"] == "model_smoke"


def test_governance_state_rejects_tampered_sensitive_checkpoint_content(tmp_path, monkeypatch) -> None:
    state = _create_state(tmp_path, monkeypatch)
    payload = state.read()
    payload["checkpoints"][0]["test_summary"] = {"note": "Bearer secret-value"}
    state.path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="sensitive"):
        state.read()
