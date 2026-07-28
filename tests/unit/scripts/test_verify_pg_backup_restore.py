"""Pure checks for the backup and restore fixture payloads."""

from __future__ import annotations

from scripts.verify_pg_backup_restore import _restore_snapshots


def test_backup_restore_fixture_covers_supported_save_versions() -> None:
    snapshots = _restore_snapshots()

    assert set(snapshots) == {"v1", "v2", "v3"}
    assert snapshots["v1"]["world"]["story_version"] == 1
    assert snapshots["v2"]["world"]["story_version"] == 2
    assert snapshots["v3"]["world"]["story_version"] == 3


def test_backup_restore_fixture_preserves_post_arc_model_failure_context() -> None:
    v3 = _restore_snapshots()["v3"]

    assert v3["world"]["story_state"]["status"] == "post_arc"
    assert v3["pending_model_failure"]["status"] == "pending"
