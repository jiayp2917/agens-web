"""Narrator JSON and legacy output parsing tests."""

from __future__ import annotations

import pytest

from agens_novel.agents.narrator import nodes
from agens_novel.agents.narrator.nodes import (
    _NARRATOR_RESPONSE_FORMAT,
    _contract_diagnostics,
    _parse_narrator_output,
)
from agens_novel.engine.model_result import ModelResultKind, classify_narrator_result


class TestNarratorParse:
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

    def test_contract_diagnostics_ignore_fake_tag_substrings_in_removed_json(self) -> None:
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
        assert status.kind == ModelResultKind.OK

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


@pytest.mark.asyncio
async def test_json_narrator_uses_the_provider_neutral_output_budget(monkeypatch) -> None:
    captured: dict[str, object] = {}

    async def fake_call(_messages, **kwargs):
        captured.update(kwargs)
        return {
            "text": '{"narrative":"山门雾起。","choices":["吐纳","请教","历练","随缘"]}',
            "usage": {},
        }

    monkeypatch.setattr(nodes, "call_llm", fake_call)

    _response, _text, transport, envelope_ok = await nodes._primary_narrator_call(
        {"response_mode": "json_object"},
        [],
        None,
    )

    assert captured["max_tokens"] == 8192
    assert transport.value == "json_object"
    assert envelope_ok is True


def test_narrator_output_budget_cannot_be_lowered_below_structured_minimum(monkeypatch) -> None:
    monkeypatch.setenv("AGNES_MAX_TOKENS", "4096")

    assert nodes._narrator_max_tokens() == 8192
