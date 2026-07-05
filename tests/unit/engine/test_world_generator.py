"""Tests for profile-aware world/opening generation helpers."""

from __future__ import annotations

from agens_novel.engine.world_generator import (
    build_world_fallback,
    build_world_prompt,
    is_complete_opening_payload,
    parse_world_response,
)


def _profile(**overrides):
    base = {
        "char_name": "许满",
        "talent": "平平无奇",
        "spirit_root": "木灵根",
        "family_background": "寒门",
        "difficulty": "普通",
        "randomize_attributes": False,
        "attributes": {
            "root_bone": 5,
            "comprehension": 5,
            "luck": 5,
            "willpower": 5,
            "physique": 5,
            "soul": 5,
        },
    }
    base.update(overrides)
    return base


def test_world_prompt_includes_attributes_and_fate() -> None:
    prompt = build_world_prompt(_profile(
        talent="天命道胎",
        spirit_root="雷灵根",
        difficulty="困难",
        attributes={
            "root_bone": 8,
            "comprehension": 7,
            "luck": 8,
            "willpower": 4,
            "physique": 2,
            "soul": 1,
        },
    ))

    assert "六维属性" in prompt
    assert "根骨=8" in prompt
    assert "命数倾向" in prompt
    assert "天命奇遇" in prompt
    assert "0-16岁短编年史" in prompt


def test_fallback_varies_by_profile_and_contains_opening_payload() -> None:
    calm = build_world_fallback(_profile())
    hard = build_world_fallback(_profile(
        difficulty="困难",
        attributes={
            "root_bone": 2,
            "comprehension": 4,
            "luck": 2,
            "willpower": 8,
            "physique": 8,
            "soul": 6,
        },
    ))

    assert calm["world_name"] != hard["world_name"]
    assert calm["initial_situation_16"] != hard["initial_situation_16"]
    assert len(calm["chronicle_0_16"]) >= 3
    assert len(calm["choices"]) == 4
    assert "青玄宗" not in calm["opening_narrative"]
    assert calm["world"]["lore_facts"]


def test_parse_world_response_accepts_new_fields_and_strips_internal_keys() -> None:
    parsed = parse_world_response({
        "generated_data": {
            "world_profile": {
                "world_name": "归墟潮界",
                "regions": "潮生海市",
                "sects": [{"name": "潮音阁"}],
                "current_conflicts": "灵潮提前",
                "fate_hooks": "天命奇遇",
            },
            "opening": {
                "chronicle_0_16": "十六岁前，许满多听潮声。",
                "initial_situation_16": "十六岁这年，许满抵达潮音渡口。",
                "choices": ["稳住渡口差事", "打听灵潮", "夜探沉星礁", "随潮而行"],
            },
            "world": {"location": "潮音渡口"},
            "llm_error": "must-not-leak",
            "state_delta": {"character": {"inventory_add": ["bad"]}},
        }
    })

    assert parsed["world_name"] == "归墟潮界"
    assert parsed["regions"] == ["潮生海市"]
    assert parsed["current_conflicts"] == ["灵潮提前"]
    assert parsed["chronicle_0_16"] == ["十六岁前，许满多听潮声。"]
    assert parsed["initial_situation_16"] == "十六岁这年，许满抵达潮音渡口。"
    assert parsed["choices"] == ["稳住渡口差事", "打听灵潮", "夜探沉星礁", "随潮而行"]
    assert "llm_error" not in parsed
    assert "state_delta" not in parsed


def test_complete_opening_payload_requires_model_owned_fields() -> None:
    complete = parse_world_response({
        "generated_data": {
            "world_name": "归墟潮界",
            "regions": [{"name": "潮生海市"}],
            "sects": [{"name": "潮音阁"}],
            "current_conflicts": ["灵潮提前"],
            "fate_hooks": ["天命奇遇"],
            "chronicle_0_16": ["十六岁前，许满多听潮声。"],
            "initial_situation_16": "十六岁这年，许满抵达潮音渡口。",
            "world": {
                "current_scene": "潮音渡口正在登记听潮弟子",
                "lore_facts": ["归墟潮界灵潮提前。"],
            },
            "choices": ["稳住渡口差事", "打听灵潮", "夜探沉星礁", "随潮而行"],
        }
    })
    incomplete = parse_world_response({
        "generated_data": {
            "opening_narrative": "只有一段开场文字。",
            "choices": ["稳住渡口差事"],
        }
    })

    assert is_complete_opening_payload(complete) is True
    assert is_complete_opening_payload(incomplete) is False


def test_complete_opening_payload_rejects_choices_completed_by_fallback() -> None:
    parsed = parse_world_response({
        "generated_data": {
            "world_name": "归墟潮界",
            "regions": [{"name": "潮生海市"}],
            "sects": [{"name": "潮音阁"}],
            "current_conflicts": ["灵潮提前"],
            "fate_hooks": ["天命奇遇"],
            "chronicle_0_16": ["十六岁前，许满多听潮声。"],
            "initial_situation_16": "十六岁这年，许满抵达潮音渡口。",
            "world": {
                "current_scene": "潮音渡口正在登记听潮弟子",
                "lore_facts": ["归墟潮界灵潮提前。"],
            },
            "choices": ["稳住渡口差事", "打听灵潮"],
        }
    })

    assert parsed["choices"] == ["稳住渡口差事", "打听灵潮"]
    assert is_complete_opening_payload(parsed) is False


def test_complete_opening_payload_rejects_missing_model_world_name() -> None:
    parsed = parse_world_response({
        "generated_data": {
            "regions": [{"name": "潮生海市"}],
            "sects": [{"name": "潮音阁"}],
            "current_conflicts": ["灵潮提前"],
            "fate_hooks": ["天命奇遇"],
            "chronicle_0_16": ["十六岁前，许满多听潮声。"],
            "initial_situation": "许满抵达潮音渡口。",
            "initial_situation_16": "十六岁这年，许满抵达潮音渡口。",
            "world": {
                "current_scene": "潮音渡口正在登记听潮弟子",
                "lore_facts": ["归墟潮界灵潮提前。"],
            },
            "choices": ["稳住渡口差事", "打听灵潮", "夜探沉星礁", "随潮而行"],
        }
    })

    assert "world_name" not in parsed
    assert is_complete_opening_payload(parsed) is False
