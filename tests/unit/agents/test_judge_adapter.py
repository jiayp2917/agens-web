"""Provider transport and authority tests for Judge decisions."""

from __future__ import annotations

import asyncio

from agens_novel.agents.judge import nodes


def _state(model: str) -> dict[str, object]:
    return {
        "model": model,
        "user_input": "A",
        "narrative": "其人在外门静修。",
        "state_delta": {},
        "game_state_json": "{}",
    }


def test_judge_deepseek_json_object_uses_adapter(monkeypatch) -> None:
    monkeypatch.setenv("AGENS_DEEPSEEK_JUDGE_TRANSPORT", "json_object")
    prompt = nodes.build_prompt(_state("deepseek-v4-flash"))
    calls = []

    async def fake_call(_state, **kwargs):
        calls.append(kwargs)
        return {"output_text": "{}", "llm_error": "", "elapsed_ms": 1, "usage": {}}

    monkeypatch.setattr(nodes, "call_agnes_llm_common", fake_call)
    asyncio.run(nodes.call_agnes_llm({**prompt, "api_key_set": True}))

    assert prompt["provider_transport"] == "json_object"
    assert calls[0]["response_format"] == {"type": "json_object"}


def test_judge_legacy_correction_is_not_returned_as_authority() -> None:
    result = nodes.save_artifact(
        {
            "output_text": (
                '{"approved": false, "corrected_delta": '
                '{"character": {"realm": "筑基"}}, "judgment_note": "冲突"}'
            ),
            "llm_error": "",
            "model": "test-model",
        }
    )

    assert result["approved"] is False
    assert result["corrected_delta"] == {}
    assert result["rewrite_required"] is True
