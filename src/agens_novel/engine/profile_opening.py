"""Profile-driven opening helpers."""

from __future__ import annotations

from typing import Any

from ..game.constants import ATTRIBUTE_KEYS, ATTRIBUTE_LABELS, normalize_attribute_value
from ..session.game_session import GameSession
from .world_catalog import world_pack_for_key


def profile_attributes(profile: dict[str, Any]) -> dict[str, int]:
    """Return normalized 0-10 character attributes for opening generation."""
    raw_attrs = profile.get("attributes")
    attrs: dict[str, int] = {}
    if isinstance(raw_attrs, dict):
        for key in ATTRIBUTE_KEYS:
            attrs[key] = normalize_attribute_value(raw_attrs.get(key, 5))
    else:
        attrs = {key: 5 for key in ATTRIBUTE_KEYS}
    return attrs


def fate_profile(profile: dict[str, Any]) -> list[dict[str, Any]]:
    """Return structured fate dimensions derived from public creation inputs."""
    attrs = profile_attributes(profile)
    talent = str(profile.get("talent") or "")
    root = str(profile.get("spirit_root") or "")
    family = str(profile.get("family_background") or "")
    difficulty = str(profile.get("difficulty") or "普通")
    random_mode = bool(profile.get("randomize_attributes"))
    scores: dict[str, int] = {
        "苦修": 0,
        "宗门": 0,
        "散修": 0,
        "天命": 0,
        "灾厄": 0,
        "贵胄": 0,
        "神魂异兆": 0,
        "边地劫数": 0,
    }

    _score_attribute_fates(scores, attrs, talent, root)
    _score_background_fates(scores, family)
    _score_difficulty_fates(scores, difficulty, random_mode)

    if max(scores.values()) <= 0:
        scores["散修"] = 1

    profiles: list[dict[str, Any]] = []
    for fate_id, score in sorted(scores.items(), key=lambda item: (-item[1], item[0])):
        if score <= 0:
            continue
        spec = _FATE_DIMENSIONS[fate_id]
        profiles.append({
            "id": fate_id,
            "label": spec["label"],
            "score": score,
            "related_attributes": spec["related_attributes"],
            "preferred_worlds": spec["preferred_worlds"],
            "event_weight_modifiers": spec["event_weight_modifiers"],
            "narrative_keywords": spec["narrative_keywords"],
        })
    return profiles[:4]


def _score_attribute_fates(
    scores: dict[str, int], attrs: dict[str, int], talent: str, root: str
) -> None:
    if attrs["root_bone"] >= 7 or attrs["physique"] >= 7 or "雷" in root:
        scores["苦修"] += 3
    if attrs["comprehension"] >= 7 or "剑心" in talent or "道胎" in talent:
        scores["苦修"] += 2
        scores["天命"] += 1
    if attrs["luck"] >= 7 or "天命" in talent:
        scores["天命"] += 4
    if attrs["luck"] <= 3:
        scores["灾厄"] += 3
        scores["边地劫数"] += 2
    if attrs["willpower"] >= 7:
        scores["苦修"] += 1
        scores["边地劫数"] += 1
    if attrs["soul"] >= 7:
        scores["神魂异兆"] += 4
        scores["天命"] += 1


def _score_background_fates(scores: dict[str, int], family: str) -> None:
    if any(marker in family for marker in ("隐世", "仙族", "世家")):
        scores["贵胄"] += 4
        scores["宗门"] += 2
    if "宗门" in family:
        scores["宗门"] += 4
    if "农家" in family or "寒门" in family:
        scores["散修"] += 3


def _score_difficulty_fates(scores: dict[str, int], difficulty: str, random_mode: bool) -> None:
    if difficulty == "困难":
        scores["灾厄"] += 3
        scores["边地劫数"] += 3
    elif difficulty == "简单":
        scores["宗门"] += 1
    if random_mode:
        scores["天命"] += 1
        scores["灾厄"] += 1


def fate_tendency(profile: dict[str, Any]) -> list[str]:
    """Derive broad fate tags from public character-creation inputs."""
    return [item["label"] for item in fate_profile(profile)] or ["散修"]


def profile_summary(profile: dict[str, Any]) -> dict[str, Any]:
    """Build the safe public profile facts used by opening generators."""
    attrs = profile_attributes(profile)
    profile_fates = fate_profile(profile)
    return {
        "char_name": str(profile.get("char_name") or "无名"),
        "talent": str(profile.get("talent") or "平平无奇"),
        "spirit_root": str(profile.get("spirit_root") or "未明"),
        "family_background": str(profile.get("family_background") or "凡俗"),
        "difficulty": str(profile.get("difficulty") or "普通"),
        "randomize_attributes": bool(profile.get("randomize_attributes")),
        "attributes": attrs,
        "fate_profile": profile_fates,
        "fate_tendency": [item["label"] for item in profile_fates] or ["散修"],
    }


def profile_default_world(profile: dict[str, Any]) -> tuple[str, str, str, str]:
    """Build deterministic fallback world fields from the character profile."""
    summary = profile_summary(profile)
    family = summary["family_background"]
    talent = summary["talent"]
    difficulty = summary["difficulty"]
    attrs = summary["attributes"]
    fate = "、".join(summary["fate_tendency"])
    world_key = _world_key(summary)
    pack = world_pack_for_key(world_key)
    region = str(pack["world_name"])
    location = str(pack["location"])
    pressure = {
        "简单": "各地灵脉尚稳，宗门愿给新弟子试错余地",
        "普通": "边境暗流渐起，宗门筛选弟子比往年更严",
        "困难": "灵脉衰落与妖潮传闻并行，少年入道即要面对取舍",
    }.get(difficulty, "边境暗流渐起，宗门筛选弟子比往年更严")
    lore = (
        f"{region}近年局势为{pressure}。{family}出身、身怀{talent}的少年被卷入"
        f"{fate}的命数；六维中{_attribute_focus(attrs)}最能影响他的开局。"
    )
    return location, location, region, lore


def profile_opening(session: GameSession) -> str:
    """Opening text for deterministic character creation fallback."""
    chronicle = []
    if isinstance(session.world_profile, dict):
        raw_chronicle = session.world_profile.get("chronicle_0_16")
        if isinstance(raw_chronicle, list):
            chronicle = [str(item) for item in raw_chronicle if str(item).strip()]
    if chronicle:
        return "\n".join(chronicle[:5]) + f"\n\n十六岁这年，{session.current_scene or session.location}。"
    return (
        f"十六岁这年，{session.char_name or '无名'}来到{session.location or '山门'}。"
        f"其出身{session.family_background or '凡俗'}，灵根为{session.spirit_root or '未明'}，"
        f"外界局势已在{session.region or '本界'}积成暗流。"
    )


def _world_key(summary: dict[str, Any]) -> str:
    attrs = summary["attributes"]
    if summary["difficulty"] == "困难" or attrs["willpower"] >= 7 or attrs["luck"] <= 3:
        return "frontier"
    if "隐世" in summary["family_background"] or "宗门" in summary["family_background"]:
        return "clan"
    if attrs["luck"] >= 7 or attrs["soul"] >= 7:
        return "ocean"
    return "forest"


def _attribute_focus(attrs: dict[str, int]) -> str:
    ordered = sorted(attrs.items(), key=lambda item: item[1], reverse=True)
    top_key, top_value = ordered[0]
    low_key, low_value = ordered[-1]
    top_label = ATTRIBUTE_LABELS.get(top_key, top_key)
    low_label = ATTRIBUTE_LABELS.get(low_key, low_key)
    if top_value - low_value >= 3:
        return f"{top_label}偏强、{low_label}偏弱"
    return f"{top_label}稍占上风"


def _dedupe(values: list[str]) -> list[str]:
    out: list[str] = []
    for value in values:
        text = value.strip()
        if text and text not in out:
            out.append(text)
    return out


_FATE_DIMENSIONS: dict[str, dict[str, Any]] = {
    "苦修": {
        "label": "苦修",
        "related_attributes": ["root_bone", "physique", "comprehension", "willpower"],
        "preferred_worlds": ["frontier", "forest"],
        "event_weight_modifiers": {"稳妥": 2, "风险": 1},
        "narrative_keywords": ["根基", "苦修", "耐性"],
    },
    "宗门": {
        "label": "宗门",
        "related_attributes": ["comprehension", "willpower"],
        "preferred_worlds": ["clan", "forest"],
        "event_weight_modifiers": {"稳妥": 1, "机遇": 2},
        "narrative_keywords": ["师门", "名册", "规矩"],
    },
    "散修": {
        "label": "散修",
        "related_attributes": ["luck", "willpower"],
        "preferred_worlds": ["frontier", "ocean", "forest"],
        "event_weight_modifiers": {"机遇": 1, "风险": 1},
        "narrative_keywords": ["坊市", "路引", "自寻门路"],
    },
    "天命": {
        "label": "天命",
        "related_attributes": ["luck", "comprehension", "soul"],
        "preferred_worlds": ["ocean", "clan"],
        "event_weight_modifiers": {"气运": 3, "机遇": 1},
        "narrative_keywords": ["签文", "星象", "潮汐"],
    },
    "灾厄": {
        "label": "灾厄",
        "related_attributes": ["luck", "willpower", "physique"],
        "preferred_worlds": ["frontier"],
        "event_weight_modifiers": {"风险": 2, "气运": 1},
        "narrative_keywords": ["劫数", "反噬", "失踪"],
    },
    "贵胄": {
        "label": "贵胄",
        "related_attributes": ["comprehension", "soul"],
        "preferred_worlds": ["clan"],
        "event_weight_modifiers": {"机遇": 2, "稳妥": 1},
        "narrative_keywords": ["旧契", "族名", "评席"],
    },
    "神魂异兆": {
        "label": "神魂异兆",
        "related_attributes": ["soul", "comprehension"],
        "preferred_worlds": ["ocean", "clan"],
        "event_weight_modifiers": {"气运": 2, "机遇": 1},
        "narrative_keywords": ["梦兆", "魂灯", "幻境"],
    },
    "边地劫数": {
        "label": "边地劫数",
        "related_attributes": ["willpower", "physique", "luck"],
        "preferred_worlds": ["frontier"],
        "event_weight_modifiers": {"风险": 3},
        "narrative_keywords": ["边营", "妖潮", "断路"],
    },
}
