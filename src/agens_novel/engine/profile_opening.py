"""Profile-driven opening helpers."""

from __future__ import annotations

from typing import Any

from ..game.constants import ATTRIBUTE_KEYS, ATTRIBUTE_LABELS, normalize_attribute_value
from ..session.game_session import GameSession


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


def fate_tendency(profile: dict[str, Any]) -> list[str]:
    """Derive broad fate tags from public character-creation inputs."""
    attrs = profile_attributes(profile)
    talent = str(profile.get("talent") or "")
    root = str(profile.get("spirit_root") or "")
    family = str(profile.get("family_background") or "")
    difficulty = str(profile.get("difficulty") or "普通")
    tags: list[str] = []

    if attrs["comprehension"] >= 7 or "剑心" in talent or "道胎" in talent:
        tags.append("早慧悟道")
    if attrs["luck"] >= 7 or "天命" in talent:
        tags.append("天命奇遇")
    if attrs["root_bone"] >= 7 or attrs["physique"] >= 7 or "雷" in root:
        tags.append("苦修武修")
    if attrs["willpower"] >= 7 or difficulty == "困难":
        tags.append("逆境磨砺")
    if attrs["soul"] >= 7:
        tags.append("神魂异兆")
    if "隐世" in family or "仙族" in family or "宗门" in family:
        tags.append("贵胄世家")
    elif "农家" in family or "寒门" in family:
        tags.append("寒门散修")
    if difficulty == "困难" or attrs["luck"] <= 3:
        tags.append("灾厄边地")
    if bool(profile.get("randomize_attributes")):
        tags.append("命数起伏")

    if not tags:
        tags.append("平稳入道")
    return _dedupe(tags)[:4]


def profile_summary(profile: dict[str, Any]) -> dict[str, Any]:
    """Build the safe public profile facts used by opening generators."""
    attrs = profile_attributes(profile)
    return {
        "char_name": str(profile.get("char_name") or "无名"),
        "talent": str(profile.get("talent") or "平平无奇"),
        "spirit_root": str(profile.get("spirit_root") or "未明"),
        "family_background": str(profile.get("family_background") or "凡俗"),
        "difficulty": str(profile.get("difficulty") or "普通"),
        "randomize_attributes": bool(profile.get("randomize_attributes")),
        "attributes": attrs,
        "fate_tendency": fate_tendency(profile),
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
    region = _WORLD_VARIANTS[world_key]["world_name"]
    location = _WORLD_VARIANTS[world_key]["location"]
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


_WORLD_VARIANTS = {
    "frontier": {
        "world_name": "西陲裂土",
        "location": "荒岭接引营",
        "sect": "砺锋院",
    },
    "clan": {
        "world_name": "玄都盟境",
        "location": "玄都盟外院",
        "sect": "玄都盟",
    },
    "ocean": {
        "world_name": "沧澜群岛",
        "location": "潮音渡口",
        "sect": "潮音阁",
    },
    "forest": {
        "world_name": "青岚药境",
        "location": "青岚药圃",
        "sect": "青岚谷",
    },
}


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
