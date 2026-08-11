"""Narrator provider transport and prompt contract tests."""

from __future__ import annotations

import asyncio
import json

from agens_novel.agents.narrator.nodes import (
    _unwrap_narrator_envelope,
    build_prompt,
)
from agens_novel.llm.provider_adapter import ProviderTransport, narrator_transport


class TestNarratorParse:
    def test_narrator_transport_uses_explicit_response_mode(self) -> None:
        assert narrator_transport({}) == ProviderTransport.JSON_OBJECT
        assert narrator_transport({"response_mode": "json_schema"}) == ProviderTransport.JSON_SCHEMA
        assert narrator_transport({"provider_transport": "json_object"}) == ProviderTransport.JSON_OBJECT
        assert narrator_transport({"response_mode": "legacy_tags"}) == ProviderTransport.JSON_OBJECT

    def test_unwrap_narrator_envelope_requires_exact_output_field(self) -> None:
        wrapped = json.dumps(
            {
                "narrative": "山门新榜已经贴出。",
                "choices": ["闭关", "拜访", "历练", "随缘"],
            },
            ensure_ascii=False,
        )

        output = _unwrap_narrator_envelope(wrapped)
        assert output is not None
        assert "<state_update>" not in output
        assert "<choices>" in output
        assert _unwrap_narrator_envelope('{"narrative":"ok","extra":1}') is None
        assert _unwrap_narrator_envelope("not json") is None

    def test_build_prompt_records_size_metrics_without_prompt_text(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(
            "agens_novel.paths.system_prompt_path",
            lambda _name: tmp_path / "narrator.md",
        )
        (tmp_path / "narrator.md").write_text("系统提示", encoding="utf-8")
        state = {
            "user_input": "闭关修炼",
            "game_state_json": "{\"turn_count\":1}",
            "chat_history": [
                {"role": "assistant", "content": "开场"},
                {"role": "user", "content": "A"},
            ],
        }

        result = build_prompt(state)

        metrics = result["prompt_metrics"]
        assert metrics["history_count"] == 2
        assert metrics["message_count"] == 4
        assert metrics["game_state_chars"] == len("{\"turn_count\":1}")
        assert metrics["user_input_chars"] == len("闭关修炼")
        assert metrics["prompt_chars"] > metrics["game_state_chars"]
        assert "闭关修炼" not in metrics.values()
        assert "<本回合输出契约>" in result["user_message"]
        assert "<state_update>{}</state_update>" not in result["user_message"]
        assert "choices 标签不得省略" not in result["user_message"]
        assert "任何字段都不得包含标签、Markdown 或额外包装" in result["user_message"]
        assert "不得含任何英文字母" in result["user_message"]

    def test_build_prompt_uses_schema_fields_without_tag_contract(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(
            "agens_novel.paths.system_prompt_path",
            lambda _name: tmp_path / "narrator_schema.md",
        )
        (tmp_path / "narrator_schema.md").write_text("schema prompt", encoding="utf-8")

        result = build_prompt(
            {
                "user_input": "拜访同门",
                "game_state_json": "{}",
                "chat_history": [],
                "response_mode": "json_schema",
            }
        )

        assert result["provider_json_schema"] is True
        assert "narrative 和 choices" in result["user_message"]
        assert "非空且互不重复" in result["user_message"]
        assert "不得含任何英文字母" in result["user_message"]
        assert "<state_update>{}</state_update>" not in result["user_message"]
        assert "<choices>[" not in result["user_message"]

    def test_build_prompt_excludes_verbose_display_only_world_profile(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(
            "agens_novel.paths.system_prompt_path",
            lambda _name: tmp_path / "narrator_schema.md",
        )
        (tmp_path / "narrator_schema.md").write_text("schema prompt", encoding="utf-8")
        state_json = json.dumps(
            {
                "turn_count": 12,
                "rule_state": {"run_seed": "fixed", "rng_counter": 11},
                "character": {"realm": "练气", "age": 28},
                "world": {
                    "current_scene": "潮音渡口",
                    "story_key": "ocean-v2",
                    "world_profile": {
                        "world_name": "沧澜群岛",
                        "chronicle_0_16": ["展示文本" * 500],
                    },
                },
            },
            ensure_ascii=False,
        )

        result = build_prompt(
            {
                "user_input": "继续修行",
                "game_state_json": state_json,
                "chat_history": [],
            }
        )

        assert "ocean-v2" in result["user_message"]
        assert "潮音渡口" in result["user_message"]
        assert "chronicle_0_16" not in result["user_message"]
        assert result["prompt_metrics"]["game_state_chars"] < len(state_json)

    def test_prompt_state_projection_preserves_rule_fields_and_rejects_invalid_json(self) -> None:
        from agens_novel.agents.narrator.prompting import _narrator_state_for_prompt

        raw = json.dumps(
            {
                "turn_count": 3,
                "rule_state": {"run_seed": "fixed"},
                "world": {"active_quests": [1, 2, 3, 4, 5, 6, 7]},
            }
        )

        projected = json.loads(_narrator_state_for_prompt(raw))

        assert projected["turn_count"] == 3
        assert projected["rule_state"] == {"run_seed": "fixed"}
        assert projected["world"]["active_quests"] == [2, 3, 4, 5, 6, 7]
        assert _narrator_state_for_prompt("not-json") == "not-json"

    def test_json_object_prompt_uses_the_structured_contract_and_safe_history(
        self, tmp_path, monkeypatch
    ) -> None:
        monkeypatch.setattr(
            "agens_novel.paths.system_prompt_path",
            lambda name: tmp_path / f"{name}.md",
        )
        (tmp_path / "narrator.md").write_text("legacy <state_update>", encoding="utf-8")
        (tmp_path / "narrator_schema.md").write_text("structured json only", encoding="utf-8")

        result = build_prompt(
            {
                "user_input": "继续修行",
                "game_state_json": "{}",
                "provider": "DeepSeek",
                "model": "deepseek-v4-flash",
                "provider_transport": "json_object",
                "chat_history": [
                    {
                        "role": "assistant",
                        "content": '<state_update>{}</state_update>\n<choices>["甲","乙","丙","丁"]</choices>',
                    }
                ],
            }
        )

        assert result["provider_json_object"] is True
        assert result["system_message"] == "structured json only"
        assert "<state_update>" not in result["user_message"]
        assert all("<state_update>" not in message["content"] for message in result["messages"])

    def test_json_object_rejects_a_legacy_tag_fixture_without_relaxing_strictness(
        self, monkeypatch
    ) -> None:
        from agens_novel.agents.narrator import nodes

        async def fake_call_llm(*_args, **_kwargs):
            return {
                "text": '编年史正文。<choices>["甲","乙","丙","丁"]</choices>',
                "usage": {},
                "elapsed_ms": 1,
            }

        monkeypatch.setattr(nodes, "call_llm", fake_call_llm)
        result = asyncio.run(
            nodes.call_agnes_llm(
                {
                    "api_key_set": True,
                    "messages": [{"role": "user", "content": "测试"}],
                    "provider": "DeepSeek",
                    "model": "deepseek-v4-flash",
                    "provider_transport": "json_object",
                }
            )
        )

        assert result["provider_json_envelope_ok"] is False
        assert result["provider_transport"] == "json_object"

    def test_schema_prompt_strips_legacy_tags_from_assistant_history(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(
            "agens_novel.paths.system_prompt_path",
            lambda _name: tmp_path / "narrator_schema.md",
        )
        (tmp_path / "narrator_schema.md").write_text("schema prompt", encoding="utf-8")
        result = build_prompt(
            {
                "user_input": "继续修行",
                "game_state_json": "{}",
                "model": "agnes-2.0-flash",
                "chat_history": [
                    {"role": "user", "content": "拜访同门"},
                    {
                        "role": "assistant",
                        "content": (
                            "山门名册已有变化。\n"
                            "<state_update>{}</state_update>\n"
                            '<choices>["闭关","寻访","历练","随缘"]</choices>'
                        ),
                    },
                ],
            }
        )

        assistant_history = [
            message["content"] for message in result["messages"] if message["role"] == "assistant"
        ]
        assert assistant_history == ["山门名册已有变化。"]
        assert all("<state_update>" not in content for content in assistant_history)

    def test_build_prompt_compacts_long_history_but_keeps_opening(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(
            "agens_novel.paths.system_prompt_path",
            lambda _name: tmp_path / "narrator.md",
        )
        (tmp_path / "narrator.md").write_text("系统提示", encoding="utf-8")
        history = [{"role": "assistant", "content": "开局设定：" + "青岚界" * 500}]
        history.extend({"role": "user", "content": f"行动{i}"} for i in range(30))
        state = {
            "user_input": "继续修行",
            "game_state_json": "{\"turn_count\":7}",
            "chat_history": history,
        }

        result = build_prompt(state)
        contents = [message["content"] for message in result["messages"]]

        assert result["prompt_metrics"]["history_count"] == len(history)
        assert any("开局设定" in content for content in contents)
        assert any("前情摘要" in content for content in contents)
        assert any("行动29" in content for content in contents)
        assert not any("行动0" == content for content in contents)
        assert len(result["messages"]) < len(history) + 2
