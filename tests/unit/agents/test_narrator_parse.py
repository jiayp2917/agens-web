"""Tests for narrator output parsing (<state_update> extraction)."""

from __future__ import annotations

import asyncio
import json

from agens_novel.agents.narrator.nodes import (
    _NARRATOR_RESPONSE_FORMAT,
    _contract_diagnostics,
    _parse_narrator_output,
    _unwrap_narrator_envelope,
    build_prompt,
)
from agens_novel.engine.model_result import ModelResultKind, classify_narrator_result
from agens_novel.llm.provider_adapter import ProviderTransport, narrator_transport


class TestNarratorParse:
    def test_narrator_transport_keeps_provider_wire_formats_separate(self, monkeypatch) -> None:
        monkeypatch.delenv("AGENS_DEEPSEEK_NARRATOR_TRANSPORT", raising=False)

        assert narrator_transport({"provider": "Agens", "model": "agnes-2.0-flash"}) == ProviderTransport.JSON_SCHEMA
        assert narrator_transport({"provider": "DeepSeek", "model": "deepseek-v4-flash"}) == ProviderTransport.LEGACY_TAGS

        monkeypatch.setenv("AGENS_DEEPSEEK_NARRATOR_TRANSPORT", "json_object")
        assert narrator_transport({"provider": "DeepSeek", "model": "deepseek-v4-flash"}) == ProviderTransport.JSON_OBJECT

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
        assert "choices 标签不得省略" in result["user_message"]
        assert "第一个字符不得是 <、{、[" in result["user_message"]
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
                "model": "agnes-2.0-flash",
            }
        )

        assert result["provider_json_schema"] is True
        assert "narrative 和 choices" in result["user_message"]
        assert "非空且互不重复" in result["user_message"]
        assert "不得含任何英文字母" in result["user_message"]
        assert "<state_update>{}</state_update>" not in result["user_message"]
        assert "<choices>[" not in result["user_message"]

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

    def test_basic_narrative_with_delta(self) -> None:
        text = (
            "你静坐吐纳，灵气缓缓涌入丹田。\n"
            "周围的空气微微震颤。\n"
            "<state_update>\n"
            '{"character": {"attributes": {"willpower": 1, "root_bone": 1}}}\n'
            "</state_update>"
        )
        narrative, delta, choices = _parse_narrator_output(text)
        assert "吐纳" in narrative
        assert delta == {"character": {"attributes": {"willpower": 1, "root_bone": 1}}}
        assert choices == []

    def test_choices_tag_json_array(self) -> None:
        text = (
            "山门雾气渐开。\n"
            "<state_update>{\"character\": {\"attributes\": {\"luck\": 1}}}</state_update>\n"
            "<choices>\n"
            "[\"留在山门吐纳\", \"询问接引弟子\", \"观察灵气流向\"]\n"
            "</choices>"
        )
        narrative, delta, choices = _parse_narrator_output(text)
        assert narrative == "山门雾气渐开。"
        assert delta["character"]["attributes"]["luck"] == 1
        assert choices == ["留在山门吐纳", "询问接引弟子", "观察灵气流向"]

    def test_choices_from_state_update_meta(self) -> None:
        text = (
            "山风吹过石阶。\n"
            "<state_update>"
            "{\"meta\": {\"choices\": [\"修炼\", \"交谈\", \"探索\"]}}"
            "</state_update>"
        )
        narrative, _delta, choices = _parse_narrator_output(text)
        assert narrative == "山风吹过石阶。"
        assert choices == ["修炼", "交谈", "探索"]

    def test_choices_less_than_four_not_padded_by_parser(self) -> None:
        text = (
            "山门风急。\n"
            "<state_update>{}</state_update>\n"
            "<choices>[\"请教陈师兄\", \"查看令牌\"]</choices>"
        )
        _narrative, _delta, choices = _parse_narrator_output(text)
        assert choices == ["请教陈师兄", "查看令牌"]

    def test_narrative_without_tag(self) -> None:
        text = "你走在山间小路上，远处传来鸟鸣。"
        narrative, delta, choices = _parse_narrator_output(text)
        assert narrative == text
        assert delta is None
        assert choices == []

    def test_bare_abc_lines_are_parsed_as_choices(self) -> None:
        text = (
            "山门前风声渐紧。\n"
            "<state_update>{\"character\": {}, \"world\": {}, \"meta\": {}}</state_update>\n"
            "A. 跟随弟子前往演武堂\n"
            "B. 向守门弟子道谢\n"
            "C. 留意石阶上的阵纹"
        )
        narrative, delta, choices = _parse_narrator_output(text)

        assert narrative == "山门前风声渐紧。"
        assert delta == {"character": {}, "world": {}, "meta": {}}
        assert choices == ["跟随弟子前往演武堂", "向守门弟子道谢", "留意石阶上的阵纹"]

    def test_bare_chinese_abcd_lines_are_parsed_and_removed_from_narrative(self) -> None:
        text = (
            "药谷雨声渐密，你在石亭中听见外门弟子议论新开的任务。\n"
            "<state_update>{\"character\": {}, \"world\": {}, \"meta\": {}}</state_update>\n"
            "选项A：留在石亭整理见闻\n"
            "选项B：去任务堂询问药谷差事\n"
            "选项C：冒雨探查药圃边缘\n"
            "选项D：随缘跟上一名陌生丹童"
        )
        narrative, delta, choices = _parse_narrator_output(text)

        assert narrative == "药谷雨声渐密，你在石亭中听见外门弟子议论新开的任务。"
        assert delta == {"character": {}, "world": {}, "meta": {}}
        assert choices == [
            "留在石亭整理见闻",
            "去任务堂询问药谷差事",
            "冒雨探查药圃边缘",
            "随缘跟上一名陌生丹童",
        ]

    def test_fenced_json_payload_is_parsed_without_visible_fence(self) -> None:
        text = (
            "你在藏经阁门前停步，听见执事提起一卷残缺竹简。\n"
            "```json\n"
            "{\"state_delta\":{\"character\":{},\"world\":{\"lore_add\":[\"藏经阁近日清点残卷\"]},\"meta\":{}},"
            "\"choices\":[\"登记借阅名册\",\"询问执事来历\",\"夜里潜去旧架\",\"随缘抽取一卷\"]}\n"
            "```"
        )
        narrative, delta, choices = _parse_narrator_output(text)

        assert narrative == "你在藏经阁门前停步，听见执事提起一卷残缺竹简。"
        assert "```" not in narrative
        assert delta["world"]["lore_add"] == ["藏经阁近日清点残卷"]
        assert choices == ["登记借阅名册", "询问执事来历", "夜里潜去旧架", "随缘抽取一卷"]

    def test_bare_json_payload_is_parsed_after_narrative(self) -> None:
        text = (
            "你沿溪行至山脚，远处灵雾里有钟声回应。\n"
            "{\"character\":{},\"world\":{\"current_scene\":\"山脚溪桥\"},\"meta\":{},"
            "\"choices\":[\"在溪桥吐纳\",\"拜访附近散修\",\"深入灵雾\",\"随钟声而行\"]}"
        )
        narrative, delta, choices = _parse_narrator_output(text)

        assert narrative == "你沿溪行至山脚，远处灵雾里有钟声回应。"
        assert delta["world"]["current_scene"] == "山脚溪桥"
        assert choices == ["在溪桥吐纳", "拜访附近散修", "深入灵雾", "随钟声而行"]

    def test_plain_json_like_prose_is_removed_from_visible_narrative(self) -> None:
        text = '你拾起一枚玉牌，上面刻着 {"rank":"outer","note":"药谷"}，像是旧年外门凭证。'
        narrative, delta, choices = _parse_narrator_output(text)

        assert "{" not in narrative
        assert "rank" not in narrative
        assert "旧年外门凭证" in narrative
        assert delta is None
        assert choices == []

    def test_contract_like_words_inside_plain_json_prose_are_removed_from_visible_text(self) -> None:
        text = (
            '榜文旁贴着一张旧签，写着 {"text":"外门旧录","choices":["勿动"]}；'
            '另一枚木牌只记 {"meta":{"rank":"outer"}}。'
        )
        narrative, delta, choices = _parse_narrator_output(text)

        assert "choices" not in narrative
        assert "meta" not in narrative
        assert "{" not in narrative
        assert delta is None
        assert choices == []

    def test_quoted_choice_fragments_are_removed_from_visible_narrative(self) -> None:
        text = (
            "他在药圃旁查完因果账。"
            "\"稳住气息继续查账\", \"拜访账册执事\", \"冒险入山验证\", \"随缘不问来处\""
        )
        narrative, delta, choices = _parse_narrator_output(text)

        assert narrative == "他在药圃旁查完因果账。"
        assert "拜访账册执事" not in narrative
        assert delta is None
        assert choices == []

    def test_bare_payload_search_skips_plain_json_before_contract_payload(self) -> None:
        text = (
            '你先看见旧牌 {"text":"外门旧录"}，随后执事递来正式记录。\n'
            '{"state_delta":{"character":{},"world":{"current_scene":"山门榜前"},"meta":{}},'
            '"choices":["整理旧录","询问执事","揭榜试炼","随缘抽签"]}'
        )
        narrative, delta, choices = _parse_narrator_output(text)

        assert "旧牌" in narrative
        assert "{" not in narrative
        assert delta["world"]["current_scene"] == "山门榜前"
        assert choices == ["整理旧录", "询问执事", "揭榜试炼", "随缘抽签"]

    def test_malformed_legacy_state_update_is_diagnostic_only_with_valid_choices(self) -> None:
        text = (
            "你在山门前停步。\n"
            "<state_update>{bad json}</state_update>\n"
            "<choices>[\"吐纳\", \"询问\", \"历练\", \"随缘\"]</choices>"
        )
        narrative, delta, choices = _parse_narrator_output(text)
        status = classify_narrator_result({
            "narrative": narrative,
            "state_delta": delta,
            "choices": choices,
        })

        assert narrative == "你在山门前停步。"
        assert delta is None
        assert choices == ["吐纳", "询问", "历练", "随缘"]
        assert status.kind == ModelResultKind.OK

    def test_contract_diagnostics_report_shape_without_text(self) -> None:
        text = (
            "他在山门旁看见旧榜。\n"
            "<state_update>{\"character\":{},\"world\":{},\"meta\":{}}</state_update>\n"
            "<choices>[\"闭关\", \"拜访\", \"历练\"]</choices>"
        )
        narrative, delta, choices = _parse_narrator_output(text)

        diagnostics = _contract_diagnostics(text, narrative, delta, choices)

        assert diagnostics == {
            "missing_narrative": False,
            "missing_state_update": False,
            "choices_count": 3,
            "choices_count_ok": False,
            "raw_has_state_update_tag": True,
            "raw_has_choices_tag": True,
            "structured_residue": False,
            "english_residue": False,
            "narrative_english_residue": False,
            "choice_english_indices": [],
        }

    def test_contract_diagnostics_reject_any_visible_english_word(self) -> None:
        text = (
            "他在山门前获得 foreign chronicle。\n"
            '<state_update>{"character":{},"world":{},"meta":{}}</state_update>\n'
            '<choices>["闭关", "Explore ruins", "历练", "随缘"]</choices>'
        )
        narrative, delta, choices = _parse_narrator_output(text)

        diagnostics = _contract_diagnostics(text, narrative, delta, choices)

        assert diagnostics["english_residue"] is True
        assert diagnostics["narrative_english_residue"] is True
        assert diagnostics["choice_english_indices"] == [1]

    def test_schema_disallows_ascii_letters_in_visible_fields(self) -> None:
        properties = _NARRATOR_RESPONSE_FORMAT["json_schema"]["schema"]["properties"]

        assert properties["narrative"]["pattern"] == "^[^A-Za-z]*$"
        assert properties["choices"]["items"]["pattern"] == "^[^A-Za-z]*$"

    def test_contract_diagnostics_do_not_accept_fake_tag_substrings(self) -> None:
        text = (
            "山门旧录只把伪标签当作普通字段。\n"
            '{"state_delta":{"character":{},"world":{},"meta":{}},'
            '"choices":["闭关","拜访","历练","随缘"],'
            '"note":"<state_update fake> <choices fake>"}'
        )
        narrative, delta, choices = _parse_narrator_output(text)

        diagnostics = _contract_diagnostics(text, narrative, delta, choices)
        status = classify_narrator_result(
            {
                "narrative": narrative,
                "state_delta": delta,
                "choices": choices,
                "contract_diagnostics": diagnostics,
            }
        )

        assert diagnostics["raw_has_state_update_tag"] is False
        assert diagnostics["raw_has_choices_tag"] is False
        assert status.kind == ModelResultKind.INCOMPLETE_OUTPUT

    def test_state_update_with_extra_trailing_brace_is_recovered(self) -> None:
        text = (
            "你在山门前静观灵机。\n"
            "<state_update>{\"character\":{\"attributes\":{\"spirit\":1}},\"world\":{},\"meta\":{}}}</state_update>\n"
            "<choices>[\"继续吐纳\", \"请教师兄\", \"下山历练\", \"随缘而行\"]</choices>"
        )

        narrative, delta, choices = _parse_narrator_output(text)

        assert narrative == "你在山门前静观灵机。"
        assert delta == {"character": {"attributes": {"spirit": 1}}, "world": {}, "meta": {}}
        assert choices == ["继续吐纳", "请教师兄", "下山历练", "随缘而行"]

    def test_json_only_payload_can_supply_narrative_field(self) -> None:
        text = (
            "{\"narrative\":\"你在山门榜前停步，看到新贴出的药谷告示。\","
            "\"state_update\":{\"character\":{},\"world\":{},\"meta\":{}},"
            "\"choices\":{\"A\":\"抄录告示\",\"B\":\"询问药谷弟子\",\"C\":\"直接接下差事\",\"D\":\"随缘抽签\"}}"
        )
        narrative, delta, choices = _parse_narrator_output(text)

        assert narrative == "你在山门榜前停步，看到新贴出的药谷告示。"
        assert delta == {"character": {}, "world": {}, "meta": {}}
        assert choices == ["抄录告示", "询问药谷弟子", "直接接下差事", "随缘抽签"]

    def test_repair_incomplete_output_adds_choices(self, monkeypatch) -> None:
        from agens_novel.agents.narrator import nodes

        calls = []

        async def fake_call_llm_stream(*_args, **_kwargs):
            calls.append(_kwargs)
            return {"text": "山门前风声渐紧。", "elapsed_ms": 10, "usage": {}}

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

        monkeypatch.setattr(nodes, "call_llm_stream", fake_call_llm_stream)
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

        async def unexpected_stream(*_args, **_kwargs):
            raise AssertionError("schema mode must use one non-streaming primary call")

        monkeypatch.setattr(nodes, "call_llm", fake_call_llm)
        monkeypatch.setattr(nodes, "call_llm_stream", unexpected_stream)
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


class TestNarrativeViewStreamFilter:
    """Test that <state_update> is correctly filtered from narrator output.

    NarrativeView strips the <state_update>...</state_update> block before
    displaying; these tests verify the parser does the stripping.
    """

    def test_state_tag_regex(self):
        """Verify the _parse_narrator_output correctly strips state_update."""
        from agens_novel.agents.narrator.nodes import _parse_narrator_output

        text = "你静坐吐纳，灵气入体。\n\n<state_update>\n{\"character\": {\"attributes\": {\"luck\": 1}}}\n</state_update>"
        narrative, delta, choices = _parse_narrator_output(text)

        assert narrative == "你静坐吐纳，灵气入体。"
        assert delta == {"character": {"attributes": {"luck": 1}}}
        assert "<state_update>" not in narrative

    def test_state_tag_at_beginning(self):
        """If the entire output is a state_update, narrative should be empty."""
        from agens_novel.agents.narrator.nodes import _parse_narrator_output

        text = "<state_update>\n{\"meta\": {\"game_over\": true}}\n</state_update>"
        narrative, delta, choices = _parse_narrator_output(text)

        assert narrative == ""
        assert delta.get("meta", {}).get("game_over") is True

    def test_no_state_tag(self):
        """If there's no state_update tag, full text is narrative."""
        from agens_novel.agents.narrator.nodes import _parse_narrator_output

        text = "一段普通的叙事文本，没有 JSON。"
        narrative, delta, choices = _parse_narrator_output(text)

        assert narrative == text
        assert delta is None

    def test_malformed_json_in_tag(self):
        """Malformed structure tags should stay incomplete, not silently succeed."""
        from agens_novel.agents.narrator.nodes import _parse_narrator_output

        text = "叙事内容\n\n<state_update>\n{invalid json}\n</state_update>"
        narrative, delta, choices = _parse_narrator_output(text)

        assert narrative == "叙事内容"
        assert delta is None


class TestNarratorHistoryCompaction:
    """The narrator prompt must compress chat_history before it reaches the storage cap."""

    def test_short_history_returned_verbatim(self) -> None:
        from agens_novel.agents.narrator.nodes import _compact_history_for_prompt

        history = [
            {"role": "assistant", "content": "开场"},
            {"role": "user", "content": "A"},
        ]
        assert _compact_history_for_prompt(history) is history

    def test_long_history_compresses_to_opening_stub_and_recent_window(self) -> None:
        from agens_novel.agents.narrator.nodes import (
            _RECENT_HISTORY_MESSAGES,
            _compact_history_for_prompt,
        )

        opening = {"role": "assistant", "content": "开局世界设定" * 200}  # >1200 chars
        history: list[dict] = [opening]
        for i in range(12):
            history.append({"role": "user", "content": f"行动{i}"})
            history.append({"role": "assistant", "content": f"叙事{i}"})

        compacted = _compact_history_for_prompt(history)

        # Opening (truncated) + summary stub + recent window.
        assert len(compacted) == 1 + 1 + _RECENT_HISTORY_MESSAGES
        # Opening entry preserved at the front and truncated to the 1200-char cap.
        assert compacted[0]["role"] == "assistant"
        assert compacted[0]["content"].startswith("开局世界设定")
        assert len(compacted[0]["content"]) <= 1200
        # Summary stub signals the omitted middle.
        assert "省略" in compacted[1]["content"]
        # Recent window is the verbatim tail.
        assert compacted[-_RECENT_HISTORY_MESSAGES:] == history[-_RECENT_HISTORY_MESSAGES:]
        # No uncompressed middle entries leak through.
        middle_dropped = {"role": "user", "content": "行动0"}
        assert middle_dropped not in compacted
