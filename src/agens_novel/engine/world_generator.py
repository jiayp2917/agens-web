"""World profile generation for character-creation phase.

Generates a structured world profile from the character's profile selections
and catalog references. The model returns JSON; on failure a local template
fallback keeps the game running.
"""

from __future__ import annotations

import logging
from typing import Any

from ..game.constants import ATTRIBUTE_KEYS, ATTRIBUTE_LABELS
from .choices import normalize_choices
from .profile_opening import profile_summary
from .world_catalog import world_pack_for_key

log = logging.getLogger(__name__)

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
        f"{item['label']}({item['score']})"
        for item in fate_profile
        if isinstance(item, dict)
    )
    random_mode = "随机" if summary["randomize_attributes"] else "手选"

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
    return (
        "；".join(parts)
        + "。请根据以上信息生成该角色的本局修仙世界观、外界情报、0-16岁短编年史、"
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
        *chronicle,
    ]

    return {
        "world_name": world_name,
        "regions": [
            {"name": region_name, "description": variant["region_desc"]},
            {"name": variant["outer_region"], "description": variant["outer_desc"]},
        ],
        "sects": [
            {"name": sect_name, "alignment": "正道", "description": variant["sect_desc"]},
            {"name": variant["rival"], "alignment": "敌对", "description": variant["rival_desc"]},
            {"name": variant["neutral"], "alignment": "中立", "description": variant["neutral_desc"]},
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
        "opening_narrative": "\n".join(chronicle) + "\n\n" + initial_situation,
        "choices": choices,
        "world": {
            "current_scene": initial_situation,
            "location": location,
            "region": world_name,
            "npcs_present": [{"name": variant["mentor"], "relation": "接引", "realm": "练气", "affinity": 0}],
            "active_quests": [{"name": variant["quest"], "description": conflict, "status": "active", "type": "主线"}],
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
    # Try common nesting patterns
    generated = result.get("generated_data")
    if isinstance(generated, dict) and generated:
        data = generated
    elif isinstance(result.get("world_profile"), dict) and result["world_profile"]:
        data = result["world_profile"]
    else:
        log.warning("World builder returned no usable data")
        return {}

    data = dict(data)
    if isinstance(data.get("world_profile"), dict):
        nested_profile = data.pop("world_profile")
        for key, value in nested_profile.items():
            data.setdefault(key, value)
    if isinstance(data.get("opening"), dict):
        opening = data.pop("opening")
        data.setdefault("opening_narrative", opening.get("opening_narrative") or opening.get("narrative"))
        data.setdefault("chronicle_0_16", opening.get("chronicle_0_16"))
        data.setdefault("initial_situation_16", opening.get("initial_situation_16") or opening.get("initial_situation"))
        data.setdefault("choices", opening.get("choices"))

    # Validate required keys
    required = ["world_name", "regions", "sects", "initial_situation"]
    missing = [k for k in required if k not in data]
    if missing:
        log.warning("World builder response missing keys: %s", missing)

    # Ensure lists for list fields
    for field in ("regions", "sects", "current_conflicts", "fate_hooks", "chronicle_0_16", "matched_fates"):
        if field in data and not isinstance(data[field], list):
            data[field] = [data[field]] if data[field] else []
    if "fate_profile" in data and not isinstance(data["fate_profile"], list):
        data["fate_profile"] = []

    if not data.get("initial_situation_16"):
        data["initial_situation_16"] = data.get("initial_situation", "")

    if not isinstance(data.get("world"), dict):
        data["world"] = {}
    world = dict(data["world"])
    if data.get("world_name"):
        world.setdefault("region", data["world_name"])
    if data.get("initial_situation_16") or data.get("initial_situation"):
        world.setdefault("current_scene", data.get("initial_situation_16") or data.get("initial_situation"))
    lore_facts = world.get("lore_facts")
    if not isinstance(lore_facts, list):
        lore_facts = []
    for fact in [data.get("initial_situation"), *(data.get("chronicle_0_16") or [])]:
        if isinstance(fact, str) and fact.strip() and fact not in lore_facts:
            lore_facts.append(fact.strip())
    world["lore_facts"] = lore_facts
    data["world"] = world

    choices = normalize_choices(data.get("choices"))
    if choices:
        data["choices"] = choices

    # Ensure dict for world_rules
    if "world_rules" not in data or not isinstance(data["world_rules"], dict):
        data["world_rules"] = {}

    # Strip any model error/internal fields that must not reach the frontend
    for key in ("llm_error", "_error", "llm_calls", "state_delta", "raw_prompt", "api_key"):
        data.pop(key, None)

    return data


def is_complete_opening_payload(data: dict[str, Any]) -> bool:
    """Return True only when model data itself can satisfy live opening acceptance."""
    if not isinstance(data, dict) or not data:
        return False
    world_name = str(data.get("world_name") or "").strip()
    chronicle = data.get("chronicle_0_16")
    initial = str(data.get("initial_situation_16") or data.get("initial_situation") or "").strip()
    conflicts = data.get("current_conflicts")
    hooks = data.get("fate_hooks")
    choices = normalize_choices(data.get("choices"))
    world = data.get("world") if isinstance(data.get("world"), dict) else {}
    scene = str(world.get("current_scene") or "").strip()
    lore = world.get("lore_facts")
    return (
        bool(world_name)
        and isinstance(chronicle, list)
        and len([item for item in chronicle if str(item).strip()]) >= 1
        and bool(initial)
        and isinstance(conflicts, list)
        and len([item for item in conflicts if str(item).strip()]) >= 1
        and isinstance(hooks, list)
        and len([item for item in hooks if str(item).strip()]) >= 1
        and bool(scene)
        and isinstance(lore, list)
        and len([item for item in lore if str(item).strip()]) >= 1
        and len(choices) == 4
    )


def _select_variant(summary: dict[str, Any]) -> dict[str, Any]:
    attrs = summary["attributes"]
    if summary["difficulty"] == "困难" or attrs["willpower"] >= 7 or attrs["luck"] <= 3:
        key = "frontier"
    elif "隐世" in summary["family_background"] or "宗门" in summary["family_background"]:
        key = "clan"
    elif attrs["luck"] >= 7 or attrs["soul"] >= 7:
        key = "ocean"
    else:
        key = "forest"
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
    return [
        f"零至六岁，{name}生于{family}，族里只记得他少哭寡言，常望着远处灵光出神。",
        f"七至十二岁，{root}初显，{talent}也在一次小小变故中露出端倪。",
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
