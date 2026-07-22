"""Regression coverage for prompt-free evaluation evidence."""

from __future__ import annotations

from agens_novel.agents.judge.nodes import save_artifact as save_judge_artifact
from agens_novel.agents.narrator.nodes import save_artifact as save_narrator_artifact
from agens_novel.agents.world_builder.nodes import save_artifact as save_world_artifact
from agens_novel.artifacts import sink


def test_agent_artifacts_never_persist_inputs(tmp_path, monkeypatch) -> None:
    evidence_root = tmp_path / "evidence"
    monkeypatch.setenv("AGENS_EVALUATION_MODE", "1")
    monkeypatch.setenv("AGENS_ARTIFACT_ROOT", str(evidence_root))
    monkeypatch.setattr(sink, "_restrict_windows_acl", lambda _root: None)

    save_narrator_artifact(
        {
            "run_id": "narrator-run",
            "model": "test-model",
            "output_text": '潮雾散去。<choices>["守渡口", "问舟客", "闯暗礁", "借潮行"]</choices>',
            "user_input": "this prompt text must not persist",
        }
    )
    save_world_artifact(
        {
            "run_id": "world-run",
            "model": "test-model",
            "output_text": "",
            "llm_error": "simulated failure",
            "user_input": "this prompt text must not persist",
        }
    )
    save_judge_artifact(
        {
            "run_id": "judge-run",
            "model": "test-model",
            "output_text": '{"approved":true}',
            "user_input": "this prompt text must not persist",
        }
    )

    assert not list(evidence_root.rglob("input.json"))
    assert all(
        "this prompt text must not persist" not in path.read_text(encoding="utf-8")
        for path in evidence_root.rglob("*")
        if path.is_file()
    )
