"""Rich formatting helpers for the game UI."""

from __future__ import annotations

from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .game_session import GameSession, REALM_ORDER


def render_status_bar(session: GameSession) -> str:
    """One-line compact status for display after each turn."""
    realm_str = f"{session.realm}{_stage_suffix(session.realm_stage)}"
    hp = f"HP:{session.hp}/{session.hp_max}"
    mp = f"MP:{session.mp}/{session.mp_max}"
    loc = session.location or "未知"
    return f"[{realm_str} | {hp} | {mp} | 地点:{loc} | 第{session.turn_count}回合]"


def render_status_panel(session: GameSession) -> Panel:
    """Full character card as a Rich Panel."""
    realm_str = f"{session.realm}{_stage_suffix(session.realm_stage)}"
    hp_bar = _bar(session.hp, session.hp_max)
    mp_bar = _bar(session.mp, session.mp_max)
    xp_bar = _bar(session.experience, session.experience_to_next)

    lines = [
        f"  姓名:   {session.char_name or '未命名'}",
        f"  境界:   {realm_str}",
        f"  HP:     {hp_bar} {session.hp}/{session.hp_max}",
        f"  MP:     {mp_bar} {session.mp}/{session.mp_max}",
        f"  灵根:   {_spirit_root_str(session)}",
        f"  经验:   {xp_bar} {session.experience}/{session.experience_to_next}",
        f"  寿命:   {session.lifespan} 年",
        f"  灵石:   {session.gold}",
        f"  地点:   {session.location or '未知'}" + (f" - {session.region}" if session.region else ""),
        f"  回合:   {session.turn_count}",
    ]
    if session.status_effects:
        lines.append(f"  状态:   {', '.join(session.status_effects)}")

    return Panel("\n".join(lines), title="角色状态", border_style="cyan")


def render_inventory_table(session: GameSession) -> Panel:
    """Inventory as a Rich table inside a Panel."""
    if not session.inventory:
        return Panel("  (背包为空)", title="背包", border_style="yellow")

    table = Table(show_header=True, header_style="bold")
    table.add_column("物品", style="cyan")
    table.add_column("数量", justify="right")
    table.add_column("类型", style="dim")
    for item in session.inventory:
        if isinstance(item, dict):
            table.add_row(
                item.get("name", "?"),
                str(item.get("quantity", 1)),
                item.get("type", ""),
            )
        else:
            table.add_row(str(item), "1", "")
    return Panel(table, title="背包", border_style="yellow")


def render_skills_table(session: GameSession) -> Panel:
    """Techniques as a Rich table inside a Panel."""
    if not session.techniques:
        return Panel("  (尚未习得功法)", title="功法", border_style="blue")

    table = Table(show_header=True, header_style="bold")
    table.add_column("功法", style="cyan")
    table.add_column("等级", justify="right")
    table.add_column("类型", style="dim")
    for tech in session.techniques:
        if isinstance(tech, dict):
            table.add_row(
                tech.get("name", "?"),
                str(tech.get("level", 1)),
                tech.get("type", ""),
            )
        else:
            table.add_row(str(tech), "1", "")
    return Panel(table, title="功法", border_style="blue")


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _stage_suffix(stage: int) -> str:
    """Convert a numeric stage to Chinese suffix for 练气 realm."""
    cn = ["", "一层", "二层", "三层", "四层", "五层", "六层", "七层", "八层", "九层"]
    if 1 <= stage <= 9:
        return cn[stage]
    return f" {stage}层"


def _bar(current: int, maximum: int, width: int = 10) -> str:
    """Render a simple text progress bar."""
    if maximum <= 0:
        return "░" * width
    filled = int(width * current / maximum)
    filled = max(0, min(filled, width))
    return "█" * filled + "░" * (width - filled)


def _spirit_root_str(session: GameSession) -> str:
    parts = []
    if session.spirit_root:
        parts.append(session.spirit_root)
    if session.spirit_root_grade:
        parts.append(f"({session.spirit_root_grade}级)")
    return " ".join(parts) if parts else "未觉醒"
