"""Tests for world builder output parsing."""

from __future__ import annotations

import asyncio
import json

from agens_novel.agents.world_builder import nodes
from agens_novel.agents.world_builder.nodes import _parse_schema_world_output, _parse_world_output


def test_world_builder_schema_prompt_is_used_for_explicit_schema_mode() -> None:
    result = nodes.build_prompt(
        {
            "response_mode": "json_schema",
            "generation_type": "profile_opening",
            "user_input": "角色名：许满；难度：普通；六维属性：根骨=5。",
        }
    )

    assert result["provider_json_schema"] is True
    assert "<world_data>" not in result["system_message"]
    assert "直接返回一个 JSON 对象" in result["system_message"]


def test_world_builder_schema_call_passes_provider_format(monkeypatch) -> None:
    calls = []

    async def fake_call(state, **kwargs):
        calls.append(kwargs)
        return {"output_text": "{}", "llm_error": "", "elapsed_ms": 1, "usage": {}}

    monkeypatch.setattr(nodes, "call_agnes_llm_common", fake_call)
    result = asyncio.run(
        nodes.call_agnes_llm(
            {
                "api_key_set": True,
                "provider_json_schema": True,
                "messages": [{"role": "user", "content": "开局"}],
            }
        )
    )

    assert calls[0]["response_format"]["type"] == "json_schema"
    assert result["output_text"] == "{}"


def test_profile_opening_schema_call_uses_opening_response_format(monkeypatch) -> None:
    calls = []

    async def fake_call(state, **kwargs):
        calls.append(kwargs)
        return {"output_text": "{}", "llm_error": "", "elapsed_ms": 1, "usage": {}}

    monkeypatch.setattr(nodes, "call_agnes_llm_common", fake_call)
    asyncio.run(
        nodes.call_agnes_llm(
            {
                "api_key_set": True,
                "provider_transport": "json_schema",
                "generation_type": "profile_opening",
                "messages": [{"role": "user", "content": "开局"}],
            }
        )
    )

    assert calls[0]["response_format"]["json_schema"]["name"] == "profile_opening"


def test_world_builder_deepseek_json_object_uses_adapter(monkeypatch) -> None:
    monkeypatch.setenv("AGENS_DEEPSEEK_WORLD_OPENING_TRANSPORT", "json_object")
    prompt = nodes.build_prompt(
        {
            "model": "deepseek-v4-flash",
            "generation_type": "profile_opening",
            "user_input": "角色名：许满。",
        }
    )
    calls = []

    async def fake_call(_state, **kwargs):
        calls.append(kwargs)
        return {"output_text": "{}", "llm_error": "", "elapsed_ms": 1, "usage": {}}

    monkeypatch.setattr(nodes, "call_agnes_llm_common", fake_call)
    asyncio.run(nodes.call_agnes_llm({**prompt, "api_key_set": True}))

    assert prompt["provider_transport"] == "json_object"
    assert calls[0]["response_format"] == {"type": "json_object"}


def test_world_builder_defaults_to_json_object_without_provider_branching() -> None:
    result = nodes.build_prompt(
        {
            "model": "any-openai-compatible-model",
            "generation_type": "profile_opening",
            "user_input": "角色名：许满。",
        }
    )

    assert result["provider_transport"] == "json_object"
    assert "必须直接返回一个 JSON 对象" in result["system_message"]


def test_profile_opening_schema_accepts_only_the_opening_envelope() -> None:
    payload = {
        "chronicle_0_16": ["幼年听潮。", "少时识得灵机。", "十六岁抵达渡口。"],
        "initial_situation_16": "十六岁的渡口试炼即将开始。",
        "opening_narrative": "潮声渐紧，许满在十六岁来到渡口，旧日因果也随之浮现。",
        "choices": ["留在渡口核对试炼名册", "拜访舟客打听旧事", "夜探暗礁承担风险", "循着天命潮声而行"],
        "world": {"must_not": "be_applied"},
    }

    parsed, _description, opening = _parse_schema_world_output(
        json.dumps(payload, ensure_ascii=False),
        profile_opening=True,
    )

    assert parsed == {
        "chronicle_0_16": payload["chronicle_0_16"],
        "initial_situation_16": payload["initial_situation_16"],
        "opening_narrative": payload["opening_narrative"],
        "choices": payload["choices"],
    }
    assert opening == payload["opening_narrative"]


def test_profile_opening_schema_rejects_non_json_provider_response() -> None:
    """A structured transport response is not accepted unless it is JSON."""
    parsed, description, opening = _parse_schema_world_output(
        "provider returned prose instead of a JSON object",
        profile_opening=True,
    )

    assert parsed == {}
    assert description == ""
    assert opening == ""


def test_world_builder_schema_output_is_parsed_without_tags() -> None:
    payload = {
        "character": {
            "name": "许满",
            "realm": "练气",
            "realm_stage": 1,
            "spirit_root": "木灵根",
            "spirit_root_grade": "凡",
            "age": 16,
            "talent": "平平无奇",
            "family_background": "寒门",
            "difficulty": "普通",
            "attributes": {
                "root_bone": 5,
                "comprehension": 5,
                "luck": 5,
                "willpower": 5,
                "physique": 5,
                "soul": 5,
            },
            "breakthrough_flags": [],
            "techniques": [],
            "inventory": [],
            "status_effects": [],
            "lifespan": 100,
            "equipment_slots": None,
        },
        "world_name": "归墟潮界",
        "regions": [{"name": "潮生海市", "description": "潮图缺失"}],
        "sects": [{"name": "潮音阁", "alignment": "正道", "description": "守潮"}],
        "current_conflicts": ["灵潮提前"],
        "fate_hooks": ["天命奇遇"],
        "chronicle_0_16": [
            "零至六岁，常听潮声。",
            "七至十二岁，学会辨潮。",
            "十三至十五岁，离开故乡。",
        ],
        "initial_situation": "十六岁抵达潮音渡口。",
        "initial_situation_16": "十六岁抵达潮音渡口。",
        "opening_narrative": "归墟潮界灵潮提前，许满在十六岁抵达潮音渡口。",
        "choices": ["留在渡口", "打听灵潮", "夜探沉星礁", "随潮而行"],
        "world": {
            "current_scene": "渡口正在登记",
            "location": "潮音渡口",
            "region": "归墟潮界",
            "npcs_present": [],
            "active_quests": [],
            "discovered_locations": ["潮音渡口"],
            "lore_facts": ["灵潮提前"],
            "day_count": 1,
        },
    }

    parsed, description, opening = nodes._parse_schema_world_output(
        json.dumps(payload, ensure_ascii=False)
    )

    assert description == ""
    assert opening == payload["opening_narrative"]
    assert parsed["world_name"] == "归墟潮界"
    assert parsed["choices"] == payload["choices"]


def test_world_builder_schema_output_rejects_missing_character() -> None:
    payload = {
        "world_name": "归墟潮界",
        "regions": [{"name": "潮生海市", "description": "潮图缺失"}],
        "sects": [{"name": "潮音阁", "alignment": "正道", "description": "守潮"}],
        "current_conflicts": ["灵潮提前"],
        "fate_hooks": ["天命奇遇"],
        "chronicle_0_16": [
            "零至六岁，常听潮声。",
            "七至十二岁，学会辨潮。",
            "十三至十五岁，离开故乡。",
        ],
        "initial_situation": "十六岁抵达潮音渡口。",
        "initial_situation_16": "十六岁抵达潮音渡口。",
        "opening_narrative": "归墟潮界灵潮提前，许满在十六岁抵达潮音渡口。",
        "choices": ["留在渡口", "打听灵潮", "夜探沉星礁", "随潮而行"],
        "world": {
            "current_scene": "渡口正在登记",
            "location": "潮音渡口",
            "region": "归墟潮界",
            "npcs_present": [],
            "active_quests": [],
            "discovered_locations": ["潮音渡口"],
            "lore_facts": ["灵潮提前"],
            "day_count": 1,
        },
    }

    parsed, description, opening = nodes._parse_schema_world_output(
        json.dumps(payload, ensure_ascii=False)
    )

    assert parsed == {}
    assert description == ""
    assert opening == ""


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
