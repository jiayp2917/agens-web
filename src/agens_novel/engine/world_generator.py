"""World profile generation for character-creation phase.

Generates a structured world profile from the character's profile selections
and catalog references. The model returns JSON; on failure a local template
fallback keeps the game running.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from ..game.constants import ATTRIBUTE_KEYS, ATTRIBUTE_LABELS, compute_starting_lifespan
from .choices import clean_visible_text, has_visible_english, normalize_choices
from .profile_opening import profile_summary, world_key_for_summary
from .story_catalog import opening_story_binding, story_arc_for_binding
from .world_catalog import world_pack_for_key

log = logging.getLogger(__name__)

_OPENING_VISIBLE_FIELDS = (
    "world_name",
    "initial_situation",
    "initial_situation_16",
    "opening_narrative",
    "current_conflicts",
    "fate_hooks",
    "chronicle_0_16",
    "regions",
    "sects",
    "choices",
)
_WORLD_VISIBLE_FIELDS = (
    "current_scene",
    "location",
    "region",
    "lore_facts",
    "discovered_locations",
)


def build_world_prompt(profile: dict[str, Any]) -> str:
    """Build a World Builder prompt from a character creation profile."""
    summary = profile_summary(profile)
    attrs = summary["attributes"]
    fate_profile = summary["fate_profile"]
    attr_text = "，".join(
        f"{ATTRIBUTE_LABELS.get(key, key)}={attrs[key]}" for key in ATTRIBUTE_KEYS
    )
    fate = "、".join(summary["fate_tendency"])
    fate_detail = "；".join(
        f"{item['label']}({item['score']})" for item in fate_profile if isinstance(item, dict)
    )
    random_mode = "随机" if summary["randomize_attributes"] else "手选"
    semantic_text = _semantic_prompt(summary.get("profile_semantics"))
    legacy_talents = (
        [str(item).strip() for item in profile.get("legacy_talents", []) if str(item).strip()]
        if isinstance(profile.get("legacy_talents"), list)
        else []
    )
    opening_titles = (
        [str(item).strip() for item in profile.get("opening_titles", []) if str(item).strip()]
        if isinstance(profile.get("opening_titles"), list)
        else []
    )

    parts = [
        f"角色名：{summary['char_name']}",
        f"天赋：{summary['talent']}",
        f"灵根：{summary['spirit_root']}",
        f"家世：{summary['family_background']}",
        f"难度：{summary['difficulty']}",
        f"属性模式：{random_mode}",
        f"六维属性：{attr_text}",
        f"命数倾向：{fate}",
        f"命数画像：{fate_detail}",
    ]
    if semantic_text:
        parts.append(f"命数语义：{semantic_text}")
    if legacy_talents:
        parts.append(f"遗泽天赋：{'、'.join(legacy_talents)}")
    if opening_titles:
        parts.append(f"开局称号：{'、'.join(opening_titles)}")
    return (
        "；".join(parts) + "。请根据以上信息生成该角色的本局修仙世界观、外界情报、0-16岁短编年史、"
        "16岁初始局势和首次四个选择。叙事使用第三方编年史视角，A/B/C/D语义固定为稳妥、机遇、风险、气运。"
    )


def build_world_fallback(profile: dict[str, Any]) -> dict[str, Any]:
    """Generate a default world profile without calling the model."""
    summary = profile_summary(profile)
    attrs = summary["attributes"]
    char_name = summary["char_name"]
    family_background = summary["family_background"]
    talent = summary["talent"]
    spirit_root = summary["spirit_root"]
    difficulty = summary["difficulty"]
    fate_tags = summary["fate_tendency"]
    fate_profile = summary["fate_profile"]
    variant = _select_variant(summary)
    story = opening_story_binding(variant["world_key"], fate_tags)
    story_arc = story_arc_for_binding(story["story_key"], story["story_version"])
    world_name = variant["world_name"]
    sect_name = variant["sect"]
    location = variant["location"]
    region_name = variant["region"]
    conflict = _difficulty_conflict(difficulty, variant)
    chronicle = _fallback_chronicle(summary, variant)
    initial_situation = (
        f"十六岁这年，{char_name}抵达{location}。{world_name}正受{conflict}牵动，"
        f"其{family_background}出身、{spirit_root}与{talent}共同把他推向{_fate_text(fate_tags)}的开局。"
    )
    choices = [
        f"在{location}按规矩登记，先稳住住处与修行名册",
        f"打听{sect_name}近日外放的机缘与讲法消息",
        f"前往{region_name}边缘查探{variant['risk_hook']}",
        f"【气运】顺着{_fate_text(fate_tags)}的预兆，暂不争抢明面机会",
    ]
    lore_facts = [
        f"{world_name}当前冲突：{conflict}。",
        f"{char_name}的命数倾向：{'、'.join(fate_tags)}。",
        str(story["story_opening"]),
        *chronicle,
    ]

    return {
        "character": {
            "name": char_name,
            "realm": "练气",
            "realm_stage": 1,
            "spirit_root": spirit_root,
            "spirit_root_grade": str(profile.get("spirit_root_grade") or ""),
            "age": int(profile.get("age") or 16),
            "talent": talent,
            "family_background": family_background,
            "difficulty": difficulty,
            "attributes": attrs,
            "breakthrough_flags": list(profile.get("breakthrough_flags") or []),
            "techniques": list(
                profile.get("techniques") or [{"name": "基础吐纳术", "level": 1, "type": "内功"}]
            ),
            "inventory": list(
                profile.get("inventory") or [{"name": "粗布道袍", "quantity": 1, "type": "防具"}]
            ),
            "status_effects": list(profile.get("status_effects") or []),
            "lifespan": int(
                profile.get("lifespan")
                or compute_starting_lifespan(
                    "练气",
                    attributes=attrs,
                    talent=talent,
                    difficulty=difficulty,
                )
            ),
            "equipment_slots": profile.get("equipment_slots"),
        },
        "world_name": world_name,
        "regions": [
            {"name": region_name, "description": variant["region_desc"]},
            {"name": variant["outer_region"], "description": variant["outer_desc"]},
        ],
        "sects": [
            {"name": sect_name, "alignment": "正道", "description": variant["sect_desc"]},
            {"name": variant["rival"], "alignment": "敌对", "description": variant["rival_desc"]},
            {
                "name": variant["neutral"],
                "alignment": "中立",
                "description": variant["neutral_desc"],
            },
        ],
        "cultivation_system": f"{world_name}沿用九境修行，但早期更看重六维短板：{_attribute_readout(attrs)}。",
        "current_conflicts": [
            conflict,
            variant["secondary_conflict"],
            variant["long_conflict"],
        ],
        "initial_situation": initial_situation,
        "initial_situation_16": initial_situation,
        "chronicle_0_16": chronicle,
        "fate_hooks": fate_tags,
        "fate_profile": fate_profile,
        "world_key": variant["world_key"],
        "opening_hook": variant["opening_hook"],
        "long_conflict": variant["long_conflict"],
        "event_weights": variant["event_weights"],
        "matched_fates": variant["matched_fates"],
        **story,
        "opening_narrative": (
            "\n".join(chronicle) + "\n\n" + str(story["story_opening"]) + "\n\n" + initial_situation
        ),
        "choices": choices,
        "world": {
            "current_scene": initial_situation,
            "location": location,
            "region": world_name,
            "npcs_present": [
                {"name": variant["mentor"], "relation": "接引", "realm": "练气", "affinity": 0}
            ],
            "active_quests": [
                {
                    "name": story_arc.title if story_arc else variant["quest"],
                    "description": story["story_state"]["stage_goal"],
                    "status": "active",
                    "type": "主线",
                }
            ],
            "discovered_locations": [location],
            "lore_facts": lore_facts,
            "day_count": 1,
        },
        "world_rules": {
            "special_rule": f"本局角色运势受难度「{difficulty}」与命数倾向「{'、'.join(fate_tags)}」影响。"
        },
    }


def parse_world_response(result: dict[str, Any]) -> dict[str, Any]:
    """Extract world profile from a model response dict.

    The model response may nest the actual world data inside 'generated_data'
    or 'world_profile'. This function finds and validates the structured
    world profile.
    """
    data = _world_payload(result)
    if not data:
        log.warning("World builder returned no usable data")
        return {}
    data = _flatten_world_payload(data)
    _clean_opening_visible_fields(data)
    required = ["world_name", "regions", "sects", "initial_situation"]
    missing = [k for k in required if k not in data]
    if missing:
        log.warning("World builder response missing keys: %s", missing)
    _normalize_world_lists(data)
    if not data.get("initial_situation_16"):
        data["initial_situation_16"] = data.get("initial_situation", "")
    _complete_world_state(data)
    choices = normalize_choices(data.get("choices"))
    if choices:
        data["choices"] = choices
    if "world_rules" not in data or not isinstance(data["world_rules"], dict):
        data["world_rules"] = {}
    for key in ("llm_error", "_error", "llm_calls", "state_delta", "raw_prompt", "api_key"):
        data.pop(key, None)
    return data


def _world_payload(result: dict[str, Any]) -> dict[str, Any]:
    generated = result.get("generated_data")
    if isinstance(generated, dict) and generated:
        return dict(generated)
    profile = result.get("world_profile")
    return dict(profile) if isinstance(profile, dict) and profile else {}


def _flatten_world_payload(data: dict[str, Any]) -> dict[str, Any]:
    flattened = dict(data)
    nested_profile = flattened.pop("world_profile", None)
    if isinstance(nested_profile, dict):
        for key, value in nested_profile.items():
            flattened.setdefault(key, value)
    opening = flattened.pop("opening", None)
    if isinstance(opening, dict):
        flattened.setdefault(
            "opening_narrative", opening.get("opening_narrative") or opening.get("narrative")
        )
        flattened.setdefault("chronicle_0_16", opening.get("chronicle_0_16"))
        flattened.setdefault(
            "initial_situation_16",
            opening.get("initial_situation_16") or opening.get("initial_situation"),
        )
        flattened.setdefault("choices", opening.get("choices"))
    return flattened


def _normalize_world_lists(data: dict[str, Any]) -> None:
    fields = (
        "regions",
        "sects",
        "current_conflicts",
        "fate_hooks",
        "chronicle_0_16",
        "matched_fates",
    )
    for field in fields:
        if field in data and not isinstance(data[field], list):
            data[field] = [data[field]] if data[field] else []
    if "fate_profile" in data and not isinstance(data["fate_profile"], list):
        data["fate_profile"] = []


def _complete_world_state(data: dict[str, Any]) -> None:
    world_value = data.get("world")
    world = dict(world_value) if isinstance(world_value, dict) else {}
    if data.get("world_name"):
        world.setdefault("region", data["world_name"])
    situation = data.get("initial_situation_16") or data.get("initial_situation")
    if situation:
        world.setdefault("current_scene", situation)
    lore_value = world.get("lore_facts")
    lore_facts = list(lore_value) if isinstance(lore_value, list) else []
    chronicle_value = data.get("chronicle_0_16")
    chronicle = chronicle_value if isinstance(chronicle_value, list) else []
    for fact in [data.get("initial_situation"), *chronicle]:
        if isinstance(fact, str) and fact.strip() and fact not in lore_facts:
            lore_facts.append(fact.strip())
    world["lore_facts"] = lore_facts
    data["world"] = world


def is_complete_opening_payload(data: dict[str, Any]) -> bool:
    """Return True only when model data itself can satisfy live opening acceptance."""
    if not isinstance(data, dict) or not data:
        return False
    character_value = data.get("character")
    character: dict[str, Any] = character_value if isinstance(character_value, dict) else {}
    required_character_strings = (
        "name",
        "realm",
        "spirit_root",
        "talent",
        "family_background",
        "difficulty",
    )
    if any(not str(character.get(key) or "").strip() for key in required_character_strings):
        return False
    if not _valid_character_contract(character):
        return False
    world_name = str(data.get("world_name") or "").strip()
    regions = data.get("regions")
    sects = data.get("sects")
    chronicle = data.get("chronicle_0_16")
    initial = str(data.get("initial_situation_16") or data.get("initial_situation") or "").strip()
    opening = str(data.get("opening_narrative") or "").strip()
    conflicts = data.get("current_conflicts")
    hooks = data.get("fate_hooks")
    choices = normalize_choices(data.get("choices"))
    world_value = data.get("world")
    world: dict[str, Any] = world_value if isinstance(world_value, dict) else {}
    scene = str(world.get("current_scene") or "").strip()
    location = str(world.get("location") or "").strip()
    region = str(world.get("region") or "").strip()
    lore = world.get("lore_facts")
    discovered = world.get("discovered_locations")
    return (
        bool(world_name)
        and _valid_named_records(regions, ("name", "description"))
        and _valid_named_records(sects, ("name", "alignment", "description"))
        and isinstance(chronicle, list)
        and 3 <= len([item for item in chronicle if str(item).strip()]) <= 5
        and bool(initial)
        and bool(opening)
        and isinstance(conflicts, list)
        and len([item for item in conflicts if str(item).strip()]) >= 1
        and isinstance(hooks, list)
        and len([item for item in hooks if str(item).strip()]) >= 1
        and bool(scene)
        and bool(location)
        and bool(region)
        and isinstance(world.get("npcs_present"), list)
        and isinstance(world.get("active_quests"), list)
        and isinstance(discovered, list)
        and len([item for item in discovered if str(item).strip()]) >= 1
        and isinstance(lore, list)
        and len([item for item in lore if str(item).strip()]) >= 1
        and isinstance(world.get("day_count"), int)
        and not isinstance(world.get("day_count"), bool)
        and int(world["day_count"]) >= 1
        and _opening_choices_are_meaningful(choices)
        and not any(has_visible_english(text) for text in _opening_visible_texts(data))
    )


def _valid_character_contract(character: dict[str, Any]) -> bool:
    integer_fields = ("realm_stage", "age", "lifespan")
    if any(
        not isinstance(character.get(key), int)
        or isinstance(character.get(key), bool)
        or int(character[key]) < 1
        for key in integer_fields
    ):
        return False
    attributes = character.get("attributes")
    if not isinstance(attributes, dict) or set(attributes) != set(ATTRIBUTE_KEYS):
        return False
    if any(
        not isinstance(attributes.get(key), int)
        or isinstance(attributes.get(key), bool)
        or not 0 <= int(attributes[key]) <= 10
        for key in ATTRIBUTE_KEYS
    ):
        return False
    for key in ("breakthrough_flags", "techniques", "inventory", "status_effects"):
        if not isinstance(character.get(key), list):
            return False
    return "spirit_root_grade" in character and "equipment_slots" in character


def _valid_named_records(value: Any, required_fields: tuple[str, ...]) -> bool:
    if not isinstance(value, list) or not value:
        return False
    return all(
        isinstance(item, dict)
        and all(str(item.get(field) or "").strip() for field in required_fields)
        for item in value
    )


def _opening_choices_are_meaningful(choices: list[str]) -> bool:
    if len(choices) != 4:
        return False
    placeholders = {
        "具体行动",
        "稳妥路径的具体行动",
        "机遇路径的具体行动",
        "风险路径的具体行动",
        "气运路径的具体行动",
    }
    for choice in choices:
        text = clean_visible_text(choice, allow_structured=False)
        if len(text) < 4 or text in placeholders or re.fullmatch(r"[A-Da-d1-4]", text):
            return False
    return True


def _clean_opening_visible_fields(data: dict[str, Any]) -> None:
    for key in _OPENING_VISIBLE_FIELDS:
        if key in data:
            data[key] = _clean_visible_value(data[key])
    world = data.get("world")
    if not isinstance(world, dict):
        return
    for key in (
        "current_scene",
        "location",
        "region",
        "lore_facts",
        "discovered_locations",
        "npcs_present",
        "active_quests",
    ):
        if key in world:
            world[key] = _clean_visible_value(world[key])


def _clean_visible_value(value: Any) -> Any:
    if isinstance(value, str):
        return clean_visible_text(value, allow_structured=False)
    if isinstance(value, list):
        return [_clean_visible_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _clean_visible_value(item) for key, item in value.items()}
    return value


def _opening_visible_texts(data: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for key in _OPENING_VISIBLE_FIELDS:
        values.extend(_visible_strings(data.get(key)))
    values.extend(_world_visible_texts(data.get("world")))
    return values


def _world_visible_texts(value: Any) -> list[str]:
    if not isinstance(value, dict):
        return []
    values: list[str] = []
    for key in _WORLD_VISIBLE_FIELDS:
        values.extend(_visible_strings(value.get(key)))
    values.extend(_record_visible_texts(value.get("npcs_present"), ("name", "relation", "realm")))
    values.extend(
        _record_visible_texts(value.get("active_quests"), ("name", "description", "type"))
    )
    return values


def _record_visible_texts(value: Any, fields: tuple[str, ...]) -> list[str]:
    if not isinstance(value, list):
        return []
    values: list[str] = []
    for item in value:
        if isinstance(item, dict):
            for key in fields:
                values.extend(_visible_strings(item.get(key)))
    return values


def _visible_strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        out: list[str] = []
        for item in value:
            out.extend(_visible_strings(item))
        return out
    if isinstance(value, dict):
        out = []
        for item in value.values():
            out.extend(_visible_strings(item))
        return out
    return []


def _select_variant(summary: dict[str, Any]) -> dict[str, Any]:
    key = world_key_for_summary(summary)
    pack = dict(world_pack_for_key(key))
    pack["world_key"] = key
    return pack


def _difficulty_conflict(difficulty: str, variant: dict[str, str]) -> str:
    if difficulty == "简单":
        return f"{variant['sect']}开放新一轮试炼，外界虽有暗流但仍留有缓冲。"
    if difficulty == "困难":
        return f"{variant['sect']}周边灵脉吃紧，{variant['rival']}已把手伸向新弟子试炼。"
    return f"{variant['sect']}与{variant['rival']}围绕{variant['outer_region']}的灵机互相试探。"


def _fallback_chronicle(summary: dict[str, Any], variant: dict[str, str]) -> list[str]:
    name = summary["char_name"]
    attrs = summary["attributes"]
    fate = _fate_text(summary["fate_tendency"])
    family = summary["family_background"]
    talent = summary["talent"]
    root = summary["spirit_root"]
    semantics = summary.get("profile_semantics")
    semantic_context = _chronicle_semantics(semantics)
    return [
        f"零至六岁，{name}生于{family}。{semantic_context['family'] or '家中只留下朴素而克制的早年记载。'}",
        f"七至十二岁，{root}初显，{talent}也在一次小小变故中露出端倪。{semantic_context['talent_root']}",
        f"十三至十五岁，{variant['world_name']}的局势传到家门，{_attribute_readout(attrs)}逐渐决定他的修行短板。",
        f"十六岁，{fate}的线索把{name}带到{variant['location']}，本局修行由此展开。",
    ]


def _attribute_readout(attrs: dict[str, int]) -> str:
    ordered = sorted(attrs.items(), key=lambda item: item[1], reverse=True)
    top_key, top_value = ordered[0]
    low_key, low_value = ordered[-1]
    top = ATTRIBUTE_LABELS.get(top_key, top_key)
    low = ATTRIBUTE_LABELS.get(low_key, low_key)
    if top_value - low_value >= 3:
        return f"{top}偏强、{low}偏弱"
    return f"{top}略显突出、六维整体均衡"


def _fate_text(tags: list[str]) -> str:
    return "、".join(tags[:2]) if tags else "平稳入道"


def _semantic_prompt(value: Any) -> str:
    if not isinstance(value, dict):
        return ""
    parts: list[str] = []
    for key, label in (
        ("talent", "天赋"),
        ("spirit_root", "灵根"),
        ("family_background", "家世"),
        ("difficulty", "难度"),
    ):
        item = value.get(key)
        if not isinstance(item, dict):
            continue
        description = _short_text(item.get("description"), 56)
        markers = _semantic_keywords(item)
        detail = description or "、".join(markers[:4])
        if detail:
            parts.append(f"{label}：{detail}")
    return "；".join(parts)


def _chronicle_semantics(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {"family": "", "talent_root": ""}
    family = value.get("family_background")
    talent = value.get("talent")
    root = value.get("spirit_root")
    family_text = ""
    if isinstance(family, dict):
        description = _short_text(family.get("description"), 48)
        risks = family.get("initial_risks")
        risk_text = "、".join(str(item) for item in risks[:2]) if isinstance(risks, list) else ""
        family_text = description
        if risk_text:
            family_text = f"{family_text} 早年牵连包括{risk_text}。".strip()
    talent_root_parts: list[str] = []
    if isinstance(talent, dict):
        talent_root_parts.append(_short_text(talent.get("description"), 42))
    if isinstance(root, dict):
        tendency = _short_text(root.get("cultivation_tendency"), 24)
        if tendency:
            talent_root_parts.append(f"灵根更亲近{tendency}")
    return {
        "family": family_text,
        "talent_root": "；".join(part for part in talent_root_parts if part),
    }


def _semantic_keywords(item: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for field in ("tags", "story_tags", "event_tags", "initial_risks"):
        raw = item.get(field)
        if isinstance(raw, list):
            values.extend(str(value).strip() for value in raw if str(value).strip())
    return list(dict.fromkeys(values))


def _short_text(value: Any, limit: int) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip("，。； ") + "。"
