"""Profile-driven opening helpers."""

from __future__ import annotations

from typing import Any

from ..game.constants import DEFAULT_ATTRIBUTES
from ..session.game_session import GameSession


def luck_from_attributes(attributes: dict[str, int]) -> str:
    """Map numeric creation luck to a compact display label."""
    value = attributes.get("luck", DEFAULT_ATTRIBUTES["luck"])
    if value >= 90:
        return "天眷"
    if value >= 70:
        return "中上"
    if value >= 45:
        return "平稳"
    if value >= 25:
        return "起伏"
    return "低迷"


def profile_seed_name(profile: dict[str, Any]) -> str:
    """Return the player-provided game name, or the default sect seed."""
    return str(profile.get("game_name") or "").strip()


def profile_default_world(profile: dict[str, Any]) -> tuple[str, str, str, str]:
    """Build deterministic fallback world fields from the profile's game name."""
    game_name = profile_seed_name(profile)
    if not game_name:
        return "青玄宗山门", "青玄宗山门", "东荒", "青玄宗立于东荒云脉之上，山门深处常有灵雾不散。"

    sect = _sect_name_from_game_name(game_name)
    location = f"{sect}山门"
    region = f"{game_name[:8]}界"
    lore = f"{sect}因《{game_name}》而立名，山门规矩、灵脉走向与此名暗合。"
    return location, location, region, lore


def profile_opening(session: GameSession, *, special: bool = False, game_name: str = "") -> str:
    """Opening text for deterministic character creation fallback."""
    if special:
        return (
            "云海倒悬，九峰钟声同时响起。你睁眼时，掌门与诸峰长老已经等在殿外，"
            "无人敢高声言语。一枚无主仙令悬在你掌心，像是早已等了很多年。"
        )
    seed = f"《{game_name}》的因果" if game_name else "山门旧事"
    return (
        f"晨雾漫过{session.location}，{session.char_name or '无名'}踏上山门石阶。"
        f"{session.family_background or '凡俗出身'}的旧事仍在身后，"
        f"{session.spirit_root or '未明灵根'}却已在丹田深处泛起微光。"
        f"{seed}在石阶尽头缓缓展开。"
    )


def profile_concept(profile: dict[str, Any], *, special: bool = False) -> str:
    """Build a compact World Builder concept from the web creation form."""
    if special:
        return "生成隐藏开局的第一幕，保持界面不明示隐藏机制。"
    game_name = profile_seed_name(profile)
    game_part = f"游戏名称/世界种子:{game_name};" if game_name else "游戏名称为空，使用默认宗门开局;"
    return (
        game_part +
        f"角色名:{profile.get('char_name') or '无名'};"
        f"天赋:{profile.get('talent') or '平平无奇'};"
        f"灵根:{profile.get('spirit_root') or '未明'};"
        f"家世:{profile.get('family_background') or '凡俗'};"
        f"难度:{profile.get('difficulty') or '普通'}。"
        "请根据游戏名称生成宗门、地缘、开局矛盾、当前NPC和首次A/B/C行动；"
        "若游戏名称为空才使用默认青玄宗山门。"
    )


def _sect_name_from_game_name(game_name: str) -> str:
    compact = "".join(game_name.split())
    if not compact:
        return "青玄宗"
    suffix = "宗" if not compact.endswith(("宗", "门", "派", "宫", "阁", "山")) else ""
    return f"{compact[:6]}{suffix}"
