"""Tests for the read-only skill compatibility gate."""

from __future__ import annotations

from pathlib import Path

from scripts.verify_skill_copies import find_skill_copy_drift


def test_repository_skill_copies_are_in_sync() -> None:
    repository_root = Path(__file__).resolve().parents[3]
    assert find_skill_copy_drift(repository_root) == []


def test_skill_copy_drift_reports_hashes_without_rewriting_files(tmp_path) -> None:
    source = tmp_path / ".codex" / "skills" / "example" / "SKILL.md"
    copy = tmp_path / ".claude" / "skills" / "example" / "SKILL.md"
    source.parent.mkdir(parents=True)
    copy.parent.mkdir(parents=True)
    source.write_text("source", encoding="utf-8")
    copy.write_text("copy", encoding="utf-8")

    drifts = find_skill_copy_drift(tmp_path, skill_names=("example",))

    assert drifts == [
        {
            "skill": "example",
            "source_sha256": "41cf6794ba4200b839c53531555f0f3998df4cbb01a4d5cb0b94e3ca5e23947d",
            "copy_sha256": "6f5a6034e770acbfb3f797e6a7eb7948d470d45f9928f92b7d72dc7c45e6d0cd",
        }
    ]
    assert source.read_text(encoding="utf-8") == "source"
    assert copy.read_text(encoding="utf-8") == "copy"
