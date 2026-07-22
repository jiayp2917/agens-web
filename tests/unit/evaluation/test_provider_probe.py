"""Mock-only tests for provider capability probing."""

from __future__ import annotations

import asyncio
import json

from agens_novel.artifacts import sink
from agens_novel.evaluation.model_config import EvaluationModelConfig
from agens_novel.evaluation.provider_probe import probe_provider


def _config(tmp_path, monkeypatch) -> EvaluationModelConfig:
    monkeypatch.setenv("AGENS_EVALUATION_MODE", "1")
    monkeypatch.setenv("AGENS_ARTIFACT_ROOT", str(tmp_path / "evidence"))
    monkeypatch.setenv("AGENS_EVALUATION_PROVIDER", "DeepSeek")
    monkeypatch.setenv("AGENS_EVALUATION_MODEL", "deepseek-v4-flash")
    monkeypatch.setenv("AGENS_EVALUATION_BASE_URL", "https://api.deepseek.example/v1")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-evaluation-key")
    monkeypatch.setattr(sink, "_restrict_windows_acl", lambda _root: None)
    return EvaluationModelConfig.from_environment()


def test_probe_prefers_json_object_and_checks_all_agent_contracts(tmp_path, monkeypatch) -> None:
    config = _config(tmp_path, monkeypatch)
    calls = []

    async def fake_request(messages, **kwargs):
        calls.append(kwargs)
        if "on_chunk" in kwargs:
            assert "stream" not in kwargs
            callback = kwargs["on_chunk"]
            callback("流式")
            return {"text": "流式回应", "elapsed_ms": 12, "usage": {"total_tokens": 3}}
        _reject_schema_probe(kwargs.get("response_format"))
        return {
            "text": _probe_response_text(messages[0]["content"]),
            "elapsed_ms": 8,
            "usage": {"total_tokens": 2},
        }

    report = asyncio.run(
        probe_provider(config, request=fake_request, stream_request=fake_request)
    )

    assert report["recommended_transport"] == "json_object"
    assert len(report["probes"]) == 7
    assert all(item["strict"] for item in report["probes"] if item["name"] != "json_schema")
    assert any("on_chunk" in call for call in calls)
    assert sink.sensitive_marker_counts(tmp_path / "evidence") == {"secret_like": 0, "url_like": 0}


def _reject_schema_probe(response_format) -> None:
    if response_format and response_format.get("type") == "json_schema":
        if "probe_json_schema" in str(response_format):
            raise ValueError("unsupported schema")


def _probe_response_text(content: str) -> str:
    tagged = {
        "world_data": "<world_data>{\"opening_narrative\":\"开局\",\"chronicle_0_16\":[\"幼年\"],\"initial_situation_16\":\"渡口\",\"choices\":[\"A 行\",\"B 行\",\"C 行\",\"D 行\"]}</world_data>",
        "narrator_data": "<narrator_data>{\"narrative\":\"叙事\",\"choices\":[\"A 行\",\"B 行\",\"C 行\",\"D 行\"]}</narrator_data>",
        "judge_data": "<judge_data>{\"approved\":true,\"issue_codes\":[],\"rewrite_required\":false}</judge_data>",
    }
    for marker, response in tagged.items():
        if marker in content:
            return response
    if "opening_narrative" in content:
        return json.dumps(
            {
                "opening_narrative": "开局",
                "chronicle_0_16": ["幼年"],
                "initial_situation_16": "渡口",
                "choices": ["A 行", "B 行", "C 行", "D 行"],
            }
        )
    if "narrative" in content and "choices" in content:
        return json.dumps({"narrative": "叙事", "choices": ["A 行", "B 行", "C 行", "D 行"]})
    if "approved" in content:
        return json.dumps({"approved": True, "issue_codes": [], "rewrite_required": False})
    return json.dumps({"ok": True, "text": "中文"})
