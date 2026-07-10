"""Pure-text rendering functions for game state.

These produce plain strings (with Unicode progress bars) suitable for any
display. No dependency on any UI library.

Used by the web adapter and tests.
"""

from __future__ import annotations

from ..game.constants import format_realm_name
from ..session.game_session import GameSession


def public_realm_label(session: GameSession) -> str:
    return format_realm_name(session.realm or "练气", int(session.realm_stage or 1))


def _spirit_root_str(session: GameSession) -> str:
    parts = []
    if session.spirit_root:
        parts.append(session.spirit_root)
    if session.spirit_root_grade:
        parts.append(f"({session.spirit_root_grade}级)")
    return " ".join(parts) if parts else "未觉醒"


def _breakthrough_requirement_count(session: GameSession) -> tuple[int, int]:
    """Return (met, total) lightweight breakthrough preparation requirements."""
    from ..game.realm import RealmSystem
    rs = RealmSystem()
    cfg = rs.get_realm_config(getattr(session, "realm", ""))
    if cfg is None:
        return 0, 0
    total = len(cfg.breakthrough_requirements)
    missing = len(rs._missing_breakthrough_requirements(session, cfg))
    return max(0, total - missing), total


def format_status_bar(session: GameSession) -> str:
    """One-line compact status — game mode (age/realm/lifespan/meters)."""
    realm_str = public_realm_label(session)
    age = getattr(session, "age", 16)
    lifespan = getattr(session, "lifespan", 100)
    remaining = max(0, lifespan - age)
    prep_met, prep_total = _breakthrough_requirement_count(session)
    prep_str = f" | 准备:{prep_met}/{prep_total}" if prep_total else ""
    loc = session.location or "未知"
    return f"[{realm_str} | {age}岁 | 寿元:{remaining}/{lifespan}年{prep_str} | 地点:{loc} | 第{session.turn_count}回合]"


def format_realm(session: GameSession) -> str:
    """Format realm/breakthrough info."""
    from ..game.constants import REALM_ORDER

    realm_str = public_realm_label(session)

    lines = [
        f"  境界: {realm_str}",
    ]
    prep_met, prep_total = _breakthrough_requirement_count(session)
    if prep_total:
        lines.append(f"  破境准备: {prep_met}/{prep_total}")
    lines.append(f"  灵根: {_spirit_root_str(session)}")

    # Show next realm info if applicable.
    try:
        idx = REALM_ORDER.index(session.realm)
        if idx < len(REALM_ORDER) - 1:
            next_realm = REALM_ORDER[idx + 1]
            lines.append(f"  下一境界: {next_realm}")
            if idx >= 5:
                lines.append("  (此境界尚未开放)")
    except ValueError:
        pass

    return "\n".join(lines)
