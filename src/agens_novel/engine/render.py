"""Pure-text rendering functions for game state.

These produce plain strings (with Unicode progress bars) suitable for any
display. No dependency on any UI library.

Used by the web adapter and tests.
"""

from __future__ import annotations

from ..session.game_session import GameSession

# Chinese stage suffixes for realm display.
_STAGE_CN = ["", "一层", "二层", "三层", "四层", "五层", "六层", "七层", "八层", "九层"]


def _stage_suffix(stage: int) -> str:
    if 1 <= stage <= 9:
        return _STAGE_CN[stage]
    return f" {stage}层"


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
    realm_str = f"{session.realm}{_stage_suffix(session.realm_stage)}"
    age = getattr(session, "age", 16)
    lifespan = getattr(session, "lifespan", 100)
    remaining = max(0, lifespan - age)
    prep_met, prep_total = _breakthrough_requirement_count(session)
    prep_str = f" | 准备:{prep_met}/{prep_total}" if prep_total else ""
    loc = session.location or "未知"
    return f"[{realm_str} | {age}岁 | 寿元:{remaining}/{lifespan}年{prep_str} | 地点:{loc} | 第{session.turn_count}回合]"


def format_status_card(session: GameSession) -> str:
    """Multi-line character card — game mode (no HP/MP)."""
    realm_str = f"{session.realm}{_stage_suffix(session.realm_stage)}"
    prep_met, prep_total = _breakthrough_requirement_count(session)
    age = getattr(session, "age", 16)
    lifespan = getattr(session, "lifespan", 100)
    remaining = max(0, lifespan - age)

    lines = [
        f"  姓名:   {session.char_name or '未命名'}",
        f"  年龄:   {age} / 寿元 {remaining}/{lifespan} 年",
        f"  境界:   {realm_str}",
        f"  灵根:   {_spirit_root_str(session)}",
        f"  天赋:   {getattr(session, 'talent', '') or '未显'}",
        f"  家世:   {getattr(session, 'family_background', '') or '凡俗'}",
        f"  准备:   {prep_met}/{prep_total}（破境资源/机缘）" if prep_total else "  准备:   无额外要求",
        f"  地点:   {session.location or '未知'}" + (f" - {session.region}" if session.region else ""),
        f"  回合:   {session.turn_count}",
    ]
    if session.status_effects:
        effects = ", ".join(session.status_effects) if isinstance(session.status_effects, list) else str(session.status_effects)
        lines.append(f"  状态:   {effects}")
    attrs = getattr(session, "attributes", {})
    if attrs:
        from ..game.constants import ATTRIBUTE_LABELS
        attr_text = " / ".join(f"{ATTRIBUTE_LABELS.get(k, k)}:{v}" for k, v in attrs.items())
        lines.append(f"  属性:   {attr_text}")
    return "\n".join(lines)


def format_inventory(session: GameSession) -> str:
    """Inventory list as plain text."""
    if not session.inventory:
        return "  (背包为空)"
    lines = []
    for item in session.inventory:
        if isinstance(item, dict):
            name = item.get("name", "?")
            qty = item.get("quantity", 1)
            typ = item.get("type", "")
            rarity = item.get("rarity", "")
            equipped = " [已装备]" if item.get("equipped") else ""
            rarity_str = f" [{rarity}]" if rarity else ""
            type_str = f" [{typ}]" if typ else ""
            lines.append(f"  · {name} x{qty}{type_str}{rarity_str}{equipped}")
        else:
            lines.append(f"  · {item}")
    return "\n".join(lines)


def format_skills(session: GameSession) -> str:
    """Techniques/skills list as plain text."""
    if not session.techniques:
        return "  (尚未习得功法)"
    lines = []
    for tech in session.techniques:
        if isinstance(tech, dict):
            name = tech.get("name", "?")
            level = tech.get("level", 1)
            typ = tech.get("type", "")
            element = tech.get("element", "")
            parts = [f"  · {name} Lv.{level}"]
            if typ:
                parts.append(f"[{typ}]")
            if element:
                parts.append(f"({element})")
            lines.append(" ".join(parts))
        else:
            lines.append(f"  · {tech}")
    return "\n".join(lines)


def format_map(session: GameSession) -> str:
    """Discovered locations."""
    if not session.discovered_locations:
        return "  (尚未探索任何地点)"
    lines = []
    for loc in session.discovered_locations:
        marker = " <-- 当前" if loc == session.location else ""
        lines.append(f"  · {loc}{marker}")
    return "\n".join(lines)


def format_quests(session: GameSession) -> str:
    """Active quests."""
    if not session.active_quests:
        return "  (当前没有任务)"
    lines = []
    for q in session.active_quests:
        status = q.get("status", "?")
        name = q.get("name", "?")
        desc = q.get("description", "")
        qtype = q.get("type", "")
        icon = "●" if status == "active" else "○"
        type_str = f"[{qtype}] " if qtype else ""
        lines.append(f"  {icon} {type_str}{name}: {desc}")
    return "\n".join(lines)


def format_log(session: GameSession, count: int = 5) -> str:
    """Recent turn narratives."""
    history = session.turn_history
    if not history:
        return "  (暂无回合记录)"
    parts = []
    for entry in history[-count:]:
        turn = entry.get("turn", "?")
        narrative = entry.get("narrative", "（无叙事）")
        if len(narrative) > 150:
            narrative = narrative[:147] + "..."
        parts.append(f"── 第 {turn} 回合 ──\n{narrative}")
    return "\n\n".join(parts)


def format_realm(session: GameSession) -> str:
    """Format realm/breakthrough info."""
    from ..game.constants import REALM_ORDER

    realm_str = f"{session.realm}{_stage_suffix(session.realm_stage)}"

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


def format_equipment(session: GameSession) -> str:
    """Format equipment slot info."""
    slots = session.equipment_slots or {}
    if not slots:
        return "  (无装备)"

    slot_names = {"weapon": "武器", "armor": "防具", "accessory": "饰品"}
    lines = []
    for slot_key in ("weapon", "armor", "accessory"):
        slot_name = slot_names.get(slot_key, slot_key)
        item = slots.get(slot_key)
        if item and isinstance(item, dict):
            name = item.get("name", "未知")
            rarity = item.get("rarity", "")
            rarity_str = f" [{rarity}]" if rarity else ""
            lines.append(f"  {slot_name}: {name}{rarity_str}")
        else:
            lines.append(f"  {slot_name}: (空)")

    return "\n".join(lines) if lines else "  (无装备)"
