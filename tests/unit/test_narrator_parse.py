"""Tests for narrator output parsing (<state_update> extraction)."""

from __future__ import annotations

from agens_novel.agents.narrator.nodes import _parse_narrator_output


class TestNarratorParse:
    def test_basic_narrative_with_delta(self) -> None:
        text = (
            "你静坐吐纳，灵气缓缓涌入丹田。\n"
            "周围的空气微微震颤。\n"
            "<state_update>\n"
            '{"character": {"mp": "-10", "experience": "+15"}}\n'
            "</state_update>"
        )
        narrative, delta, choices = _parse_narrator_output(text)
        assert "吐纳" in narrative
        assert delta == {"character": {"mp": "-10", "experience": "+15"}}
        assert choices == []

    def test_choices_tag_json_array(self) -> None:
        text = (
            "山门雾气渐开。\n"
            "<state_update>{\"character\": {\"experience\": \"+5\"}}</state_update>\n"
            "<choices>\n"
            "[\"留在山门吐纳\", \"询问接引弟子\", \"观察灵气流向\"]\n"
            "</choices>"
        )
        narrative, delta, choices = _parse_narrator_output(text)
        assert narrative == "山门雾气渐开。"
        assert delta["character"]["experience"] == "+5"
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

    def test_choices_less_than_three_not_padded_by_parser(self) -> None:
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
        assert delta == {}

    def test_empty_delta_tag(self) -> None:
        text = "一些文字<state_update>\n{}\n</state_update>"
        narrative, delta, choices = _parse_narrator_output(text)
        assert narrative == "一些文字"
        assert delta == {}

    def test_malformed_json_in_tag(self) -> None:
        text = "叙事文本<state_update>\n{bad json}\n</state_update>"
        narrative, delta, choices = _parse_narrator_output(text)
        assert narrative == "叙事文本"
        assert delta == {}  # Graceful fallback

    def test_complex_delta(self) -> None:
        import json
        data = {
            "character": {"hp": "-20", "mp": "-30", "experience": "+25"},
            "world": {"location": "秘境入口", "current_scene": "发现一座古老的石门"},
            "meta": {"game_over": False},
        }
        text = f"你遭遇了一只妖兽！\n<state_update>\n{json.dumps(data, ensure_ascii=False)}\n</state_update>"
        narrative, delta, choices = _parse_narrator_output(text)
        assert "妖兽" in narrative
        assert delta["character"]["hp"] == "-20"
        assert delta["world"]["location"] == "秘境入口"

    def test_multiline_narrative(self) -> None:
        text = (
            "第一段叙事。\n\n"
            "第二段叙事。\n\n"
            "第三段。\n"
            "<state_update>\n"
            '{"character": {"experience": "+5"}}\n'
            "</state_update>"
        )
        narrative, delta, choices = _parse_narrator_output(text)
        assert "第一段" in narrative
        assert "第三段" in narrative
        assert delta["character"]["experience"] == "+5"
