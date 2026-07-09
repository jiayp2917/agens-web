"""Tests for world builder output parsing."""

from __future__ import annotations

import json

from agens_novel.agents.world_builder.nodes import _parse_world_output


def test_parse_world_output_preserves_abcd_opening_choices() -> None:
    payload = {
        "character": {"name": "许满", "realm": "练气"},
        "world": {"location": "青玄宗山门"},
        "opening_narrative": "晨雾漫过山门。",
        "choices": [
            {"id": "A", "text": "留在山门吐纳"},
            {"id": "B", "action": "询问接引弟子"},
            "观察灵气流向",
            "随缘听天命",
        ],
    }
    text = f"前言\n<world_data>\n{json.dumps(payload, ensure_ascii=False)}\n</world_data>"

    data, world_description, opening = _parse_world_output(text)

    assert world_description == "前言"
    assert opening == "晨雾漫过山门。"
    assert data["choices"] == ["留在山门吐纳", "询问接引弟子", "观察灵气流向", "随缘听天命"]


def test_parse_world_output_does_not_pad_short_choices() -> None:
    payload = {
        "character": {"name": "许满", "realm": "练气"},
        "world": {"location": "青玄宗山门"},
        "opening_narrative": "晨雾漫过山门。",
        "choices": ["请教陈师兄"],
    }
    text = f"前言\n<world_data>\n{json.dumps(payload, ensure_ascii=False)}\n</world_data>"

    data, _world_description, _opening = _parse_world_output(text)

    assert data["choices"] == ["请教陈师兄"]


def test_parse_world_output_accepts_dynamic_opening_fields_and_strips_internal_data() -> None:
    payload = {
        "world_name": "归墟潮界",
        "regions": [{"name": "潮生海市"}],
        "sects": [{"name": "潮音阁"}],
        "current_conflicts": ["灵潮提前"],
        "fate_hooks": ["天命奇遇"],
        "chronicle_0_16": ["零至六岁，许满常听潮声。"],
        "initial_situation_16": "十六岁这年，许满抵达潮音渡口。",
        "opening_narrative": "归墟潮界灵潮提前，许满在十六岁抵达潮音渡口。",
        "choices": ["A：稳住渡口差事", "B：打听灵潮", "C：夜探沉星礁", "D：随潮而行"],
        "raw_prompt": "must-not-leak",
        "api_key": "sk-must-not-leak",
        "state_delta": {"character": {"inventory_add": ["bad"]}},
    }
    text = f"前言\n<world_data>\n```json\n{json.dumps(payload, ensure_ascii=False)}\n```\n</world_data>"

    data, _world_description, opening = _parse_world_output(text)

    assert opening == payload["opening_narrative"]
    assert data["world_name"] == "归墟潮界"
    assert data["chronicle_0_16"] == ["零至六岁，许满常听潮声。"]
    assert len(data["choices"]) == 4
    assert all(not choice.startswith(("A", "B", "C", "D")) for choice in data["choices"])
    assert "raw_prompt" not in data
    assert "api_key" not in data
    assert "state_delta" not in data


def test_parse_world_output_accepts_plain_json_fence_without_world_data_tag() -> None:
    payload = {
        "world_name": "Test Realm",
        "regions": [{"name": "Outer Gate"}],
        "sects": [{"name": "Cloud Sect"}],
        "current_conflicts": ["border unrest"],
        "fate_hooks": ["wanderer"],
        "chronicle_0_16": ["0-16: grew up near the pass"],
        "initial_situation_16": "At sixteen, the path opens.",
        "opening_narrative": "The chronicle starts at the pass.",
        "choices": ["A: stay", "B: ask", "C: risk", "D: wait"],
    }
    text = f"Opening prose.\n```json\n{json.dumps(payload, ensure_ascii=False)}\n```"

    data, world_description, opening = _parse_world_output(text)

    assert world_description == "Opening prose."
    assert opening == "The chronicle starts at the pass."
    assert data["world_name"] == "Test Realm"
    assert data["chronicle_0_16"] == ["0-16: grew up near the pass"]
    assert len(data["choices"]) == 4
