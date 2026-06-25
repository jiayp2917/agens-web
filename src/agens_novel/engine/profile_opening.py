"""Profile-driven opening helpers."""

from __future__ import annotations

from typing import Any

from ..session.game_session import GameSession


def profile_default_world(profile: dict[str, Any]) -> tuple[str, str, str, str]:
    """Build deterministic fallback world fields from the character profile."""
    family = str(profile.get("family_background") or "凡俗")
    talent = str(profile.get("talent") or "平平无奇")
    location = "青玄宗山门"
    region = "东荒云界"
    lore = f"青玄宗立于东荒云脉之上，近年广收门人，亦关注出身{family}、身怀{talent}的少年。"
    return location, location, region, lore


def profile_opening(session: GameSession) -> str:
    """Opening text for deterministic character creation fallback."""
    return (
        f"玄历元年，晨雾漫过{session.location}，{session.char_name or '无名'}踏上山门石阶。"
        f"{session.family_background or '凡俗出身'}的旧事仍在身后，"
        f"{session.spirit_root or '未明灵根'}却已在丹田深处泛起微光。"
        "石阶尽头，外门钟声宣告这一局修行岁月正式展开。"
    )


def profile_concept(profile: dict[str, Any]) -> str:
    """Build a compact World Builder concept from the web creation form."""
    return (
        f"角色名:{profile.get('char_name') or '无名'};"
        f"天赋:{profile.get('talent') or '平平无奇'};"
        f"灵根:{profile.get('spirit_root') or '未明'};"
        f"家世:{profile.get('family_background') or '凡俗'};"
        f"难度:{profile.get('difficulty') or '普通'}。"
        "请生成宗门、地缘、开局矛盾、当前NPC和首次A/B/C行动；D固定为气运/天命路径。"
    )
