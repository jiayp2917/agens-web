"""Narrator strict-output repair and retry contract tests."""

from __future__ import annotations

import asyncio
import json

from agens_novel.agents.narrator.nodes import (
    _parse_narrator_output,
)


class TestNarratorParse:
    def test_repair_incomplete_output_adds_choices(self, monkeypatch) -> None:
        from agens_novel.agents.narrator import nodes

        calls = []

        async def fake_call_llm(*_args, **_kwargs):
            calls.append(_kwargs)
            if len(calls) == 1:
                return {"text": "山门前风声渐紧。", "elapsed_ms": 10, "usage": {}}
            return {
                "text": (
                    "山门前风声渐紧。\n"
                    "<state_update>{\"character\": {}, \"world\": {}, \"meta\": {}}</state_update>\n"
                    "<choices>[\"前往演武堂\", \"向弟子道谢\", \"观察阵纹\", \"随缘看一眼山门\"]</choices>"
                ),
                "elapsed_ms": 12,
                "usage": {},
            }

        monkeypatch.setattr(nodes, "call_llm", fake_call_llm)
        result = asyncio.run(nodes.call_agnes_llm({
            "api_key_set": True,
            "messages": [{"role": "user", "content": "test"}],
            "model": "deepseek-chat",
            "base_url": "https://api.deepseek.com/v1",
            "repair_incomplete_output": True,
            "output_text": "",
        }))

        narrative, delta, choices = _parse_narrator_output(result["output_text"])
        assert len(calls) == 2
        assert result["repaired_output"] is True
        assert calls[0]["temperature"] == 0.0
        assert narrative == "山门前风声渐紧。"
        assert delta == {"character": {}, "world": {}, "meta": {}}
        assert choices == ["前往演武堂", "向弟子道谢", "观察阵纹", "随缘看一眼山门"]

    def test_agens_schema_call_unwraps_primary_contract_without_repair(self, monkeypatch) -> None:
        from agens_novel.agents.narrator import nodes

        calls = []

        async def fake_call_llm(*_args, **kwargs):
            calls.append(kwargs)
            output = (
                "山门执事重排外门名册，验真者依新规稳住根基。\n"
                '<state_update>{"character":{},"world":{},"meta":{}}</state_update>\n'
                '<choices>["闭关温养","拜访同门","探查山径","随缘听风"]</choices>'
            )
            return {
                "text": json.dumps(
                    {
                        "narrative": output.split("\n", 1)[0],
                        "choices": ["闭关温养", "拜访同门", "探查山径", "随缘听风"],
                    },
                    ensure_ascii=False,
                ),
                "elapsed_ms": 12,
                "usage": {},
            }

        monkeypatch.setattr(nodes, "call_llm", fake_call_llm)
        # The narrator no longer has a streaming path at all; guard against its return.
        assert not hasattr(nodes, "call_llm_stream")
        result = asyncio.run(
            nodes.call_agnes_llm(
                {
                    "api_key_set": True,
                    "messages": [{"role": "user", "content": "test"}],
                    "model": "agnes-2.0-flash",
                    "base_url": "https://example.com/v1",
                    "provider_json_schema": True,
                    "repair_incomplete_output": False,
                }
            )
        )

        narrative, delta, choices = _parse_narrator_output(result["output_text"])
        assert len(calls) == 1
        assert calls[0]["response_format"]["type"] == "json_schema"
        assert result["provider_json_schema"] is True
        assert result["provider_json_envelope_ok"] is True
        assert result["repaired_output"] is False
        assert narrative.startswith("山门执事")
        assert delta is None
        assert len(choices) == 4

    def test_system_prompt_requires_unambiguous_narrative_and_choices_contract(self) -> None:
        from agens_novel import paths

        prompt = paths.system_prompt_path("narrator").read_text(encoding="utf-8")

        assert "<state_update>{}</state_update>" not in prompt
        assert '<choices>["行动一", "行动二", "行动三", "行动四"]</choices>' in prompt
        assert "不要输出 `[\"...\"]`" not in prompt

    def test_json_only_state_delta_triggers_repair_for_narrative_and_choices(self, monkeypatch) -> None:
        from agens_novel.agents.narrator import nodes

        calls = []

        async def fake_call_llm(*_args, **_kwargs):
            calls.append(_kwargs)
            if len(calls) == 1:
                return {
                    "text": (
                        "{\"character\":{\"inventory_add\":[{\"name\":\"庚金矿碎\",\"quantity\":1}]},"
                        "\"world\":{\"current_scene\":\"洞穴外\"}}"
                    ),
                    "elapsed_ms": 10,
                    "usage": {},
                }
            return {
                "text": (
                    "你在洞穴外细查石缝，拾得一片庚金矿碎。\n"
                    "<state_update>{\"character\":{\"inventory_add\":[{\"name\":\"庚金矿碎\",\"quantity\":1}]},"
                    "\"world\":{\"current_scene\":\"洞穴外\"},\"meta\":{}}</state_update>\n"
                    "<choices>[\"收好矿碎返回营地\", \"继续搜寻洞穴边缘\", \"冒险进入洞穴\", \"随缘辨认矿气\"]</choices>"
                ),
                "elapsed_ms": 12,
                "usage": {},
            }

        monkeypatch.setattr(nodes, "call_llm", fake_call_llm)
        result = asyncio.run(nodes.call_agnes_llm({
            "api_key_set": True,
            "messages": [{"role": "user", "content": "test"}],
            "model": "deepseek-chat",
            "base_url": "https://api.deepseek.com/v1",
            "repair_incomplete_output": True,
        }))

        narrative, delta, choices = _parse_narrator_output(result["output_text"])
        assert len(calls) == 2
        assert result["repaired_output"] is True
        assert "庚金矿碎" in narrative
        assert delta["character"]["inventory_add"][0]["name"] == "庚金矿碎"
        assert choices == ["收好矿碎返回营地", "继续搜寻洞穴边缘", "冒险进入洞穴", "随缘辨认矿气"]

    def test_empty_output_does_not_trigger_repair(self, monkeypatch) -> None:
        from agens_novel.agents.narrator import nodes

        calls = []

        async def fake_call_llm(*_args, **_kwargs):
            calls.append(_kwargs)
            return {"text": "", "elapsed_ms": 10, "usage": {}}

        monkeypatch.setattr(nodes, "call_llm", fake_call_llm)
        result = asyncio.run(nodes.call_agnes_llm({
            "api_key_set": True,
            "messages": [{"role": "user", "content": "test"}],
            "model": "deepseek-chat",
            "base_url": "https://api.deepseek.com/v1",
            "repair_incomplete_output": True,
        }))

        assert len(calls) == 1
        assert result["output_text"] == ""
        assert result["repaired_output"] is False

    def test_repair_without_narrative_is_not_accepted(self, monkeypatch) -> None:
        from agens_novel.agents.narrator import nodes

        calls = []

        async def fake_call_llm(*_args, **_kwargs):
            calls.append(_kwargs)
            if len(calls) == 1:
                return {
                    "text": (
                        "{\"character\":{\"inventory_add\":[{\"name\":\"清灵丹\",\"quantity\":1}]},"
                        "\"world\":{},\"meta\":{}}"
                    ),
                    "elapsed_ms": 10,
                    "usage": {},
                }
            return {
                "text": (
                    "<state_update>{\"character\":{\"inventory_add\":[{\"name\":\"清灵丹\",\"quantity\":1}]},"
                    "\"world\":{},\"meta\":{}}</state_update>\n"
                    "<choices>[\"查看丹药\", \"请教师兄\", \"继续吐纳\", \"随缘而行\"]</choices>"
                ),
                "elapsed_ms": 12,
                "usage": {},
            }

        monkeypatch.setattr(nodes, "call_llm", fake_call_llm)
        result = asyncio.run(nodes.call_agnes_llm({
            "api_key_set": True,
            "messages": [{"role": "user", "content": "test"}],
            "model": "deepseek-chat",
            "base_url": "https://api.deepseek.com/v1",
            "repair_incomplete_output": True,
        }))

        assert len(calls) == 2
        assert result["repaired_output"] is False
        assert "inventory_add" in result["output_text"]
        narrative, _delta, _choices = _parse_narrator_output(result["output_text"])
        assert narrative == ""

    def test_empty_delta_tag(self) -> None:
        text = "一些文字<state_update>\n{}\n</state_update>"
        narrative, delta, choices = _parse_narrator_output(text)
        assert narrative == "一些文字"
        assert delta == {}

    def test_malformed_json_in_tag(self) -> None:
        text = "叙事文本<state_update>\n{bad json}\n</state_update>"
        narrative, delta, choices = _parse_narrator_output(text)
        assert narrative == "叙事文本"
        assert delta is None

    def test_complex_delta(self) -> None:
        import json
        data = {
            "character": {"status_effects_add": ["轻伤"], "attributes": {"physique": 1}},
            "world": {"location": "秘境入口", "current_scene": "发现一座古老的石门"},
            "meta": {"game_over": False},
        }
        text = f"你遭遇了一只妖兽！\n<state_update>\n{json.dumps(data, ensure_ascii=False)}\n</state_update>"
        narrative, delta, choices = _parse_narrator_output(text)
        assert "妖兽" in narrative
        assert delta["character"]["status_effects_add"] == ["轻伤"]
        assert delta["world"]["location"] == "秘境入口"

    def test_multiline_narrative(self) -> None:
        text = (
            "第一段叙事。\n\n"
            "第二段叙事。\n\n"
            "第三段。\n"
            "<state_update>\n"
            '{"character": {"attributes": {"luck": 1}}}\n'
            "</state_update>"
        )
        narrative, delta, choices = _parse_narrator_output(text)
        assert "第一段" in narrative
        assert "第三段" in narrative
        assert delta["character"]["attributes"]["luck"] == 1
