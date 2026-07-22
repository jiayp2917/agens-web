"""Tests for profile-aware world/opening generation helpers."""

from __future__ import annotations

from agens_novel.engine.profile_opening import fate_profile, profile_summary, world_key_for_summary
from agens_novel.engine.start_flow import merge_opening_payload
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
    prompt = build_world_prompt(
        _profile(
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
        )
    )

    assert "六维属性" in prompt
    assert "根骨=8" in prompt
    assert "命数倾向" in prompt
    assert "命数画像" in prompt
    assert "天命" in prompt
    assert "0-16岁短编年史" in prompt


def test_world_builder_prompt_does_not_offer_generic_choice_placeholders() -> None:
    from agens_novel import paths

    prompt = paths.system_prompt_path("world_builder").read_text(encoding="utf-8")

    assert '"稳妥路径的具体行动"' not in prompt
    assert '"机遇路径的具体行动"' not in prompt
    assert "必须引用本次生成的具体地点" in prompt


def test_structured_catalog_semantics_drive_fate_without_name_substrings() -> None:
    profile = _profile(
        talent="星痕感应",
        spirit_root="潮汐灵根",
        family_background="旧族旁门",
        profile_semantics={
            "talent": {
                "description": "能察觉常人忽略的天象变化。",
                "tags": ["机缘", "神魂"],
                "attribute_mods": {"soul": 1},
            },
            "spirit_root": {
                "cultivation_tendency": "观潮炼神",
                "event_tags": ["神魂", "变化"],
            },
            "family_background": {
                "description": "出身没落旧族。",
                "story_tags": ["世家", "传承"],
                "initial_risks": ["旧契追索"],
            },
        },
    )

    fates = {item["id"] for item in fate_profile(profile)}
    summary = profile_summary(profile)
    prompt = build_world_prompt(profile)
    opening = build_world_fallback(profile)

    assert {"天命", "神魂异兆", "贵胄"}.issubset(fates)
    assert world_key_for_summary(summary) in {"ocean", "clan"}
    assert "能察觉常人忽略的天象变化" in prompt
    assert "旧契追索" in opening["opening_narrative"]


def test_fallback_varies_by_profile_and_contains_opening_payload() -> None:
    calm = build_world_fallback(_profile())
    hard = build_world_fallback(
        _profile(
            difficulty="困难",
            attributes={
                "root_bone": 2,
                "comprehension": 4,
                "luck": 2,
                "willpower": 8,
                "physique": 8,
                "soul": 6,
            },
        )
    )

    assert calm["world_name"] != hard["world_name"]
    assert calm["initial_situation_16"] != hard["initial_situation_16"]
    assert len(calm["chronicle_0_16"]) >= 3
    assert len(calm["choices"]) == 4
    assert calm["world_key"] == "forest"
    assert calm["event_weights"]
    assert calm["fate_profile"]
    assert calm["story_key"] == "herb-boundary-blight"
    assert calm["story_version"] == 2
    assert calm["story_state"]["stage_goal"]
    assert calm["story_opening"] in calm["opening_narrative"]
    assert calm["world"]["active_quests"][0]["name"] == calm["story_title"]
    assert hard["story_key"] == "border-vein-crisis"
    assert "long_conflict" in calm
    assert "青玄宗" not in calm["opening_narrative"]
    assert calm["world"]["lore_facts"]


def test_fallback_chronicle_uses_grammatical_family_and_talent_templates() -> None:
    opening = build_world_fallback(
        _profile(
            family_background="魔道遗孤",
            talent="平平无奇",
            spirit_root="火灵根",
        )
    )

    chronicle = opening["chronicle_0_16"]
    initial = opening["initial_situation_16"]
    assert "身世被记作「魔道遗孤」" in chronicle[0]
    assert "生于魔道遗孤" not in chronicle[0]
    assert "平平无奇也在" not in chronicle[1]
    assert "。；" not in chronicle[1]
    assert "正受" not in initial
    assert "牵动，其" not in initial


def test_parse_world_response_accepts_new_fields_and_strips_internal_keys() -> None:
    parsed = parse_world_response(
        {
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
        }
    )

    assert parsed["world_name"] == "归墟潮界"
    assert parsed["regions"] == ["潮生海市"]
    assert parsed["current_conflicts"] == ["灵潮提前"]
    assert parsed["chronicle_0_16"] == ["十六岁前，许满多听潮声。"]
    assert parsed["initial_situation_16"] == "十六岁这年，许满抵达潮音渡口。"
    assert parsed["choices"] == ["稳住渡口差事", "打听灵潮", "夜探沉星礁", "随潮而行"]
    assert "llm_error" not in parsed
    assert "state_delta" not in parsed


def test_complete_opening_payload_requires_model_owned_fields() -> None:
    complete = parse_world_response({"generated_data": build_world_fallback(_profile())})
    incomplete = parse_world_response(
        {
            "generated_data": {
                "opening_narrative": "只有一段开场文字。",
                "choices": ["稳住渡口差事"],
            }
        }
    )

    assert is_complete_opening_payload(complete) is True
    assert is_complete_opening_payload(incomplete) is False


def test_complete_opening_payload_rejects_visible_english_in_opening() -> None:
    parsed = parse_world_response(
        {
            "generated_data": {
                "world_name": "归墟潮界",
                "regions": [{"name": "潮生海市"}],
                "sects": [{"name": "潮音阁"}],
                "current_conflicts": ["灵潮提前"],
                "fate_hooks": ["天命奇遇"],
                "chronicle_0_16": ["十六岁前，许满多听潮声。"],
                "initial_situation_16": "十六岁这年，许满抵达潮音渡口。",
                "opening_narrative": "他在 Harvest 与劳作之间长大。",
                "world": {
                    "current_scene": "潮音渡口正在登记听潮弟子",
                    "lore_facts": ["归墟潮界灵潮提前。"],
                },
                "choices": ["稳住渡口差事", "打听灵潮", "夜探沉星礁", "随潮而行"],
            }
        }
    )

    assert is_complete_opening_payload(parsed) is False


def test_complete_opening_payload_rejects_choices_completed_by_fallback() -> None:
    parsed = parse_world_response(
        {
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
        }
    )

    assert parsed["choices"] == ["稳住渡口差事", "打听灵潮"]
    assert is_complete_opening_payload(parsed) is False


def test_complete_opening_payload_rejects_letter_only_choices() -> None:
    parsed = parse_world_response(
        {
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
                "choices": ["A", "B", "C", "D"],
            }
        }
    )

    assert is_complete_opening_payload(parsed) is False


def test_complete_opening_payload_rejects_missing_model_world_name() -> None:
    parsed = parse_world_response(
        {
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
        }
    )

    assert "world_name" not in parsed
    assert is_complete_opening_payload(parsed) is False


def test_model_opening_cannot_replace_rule_owned_story_binding() -> None:
    fallback = build_world_fallback(_profile())

    merged = merge_opening_payload(
        fallback,
        {
            "world_name": "模型新世界",
            "story_key": "model-story",
            "story_version": 99,
            "story_state": {"phase_key": "model-reset"},
        },
    )

    assert merged["world_name"] == "模型新世界"
    assert merged["story_key"] == fallback["story_key"]
    assert merged["story_version"] == fallback["story_version"]
    assert merged["story_state"] == fallback["story_state"]
