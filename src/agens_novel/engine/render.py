"""Pure-text rendering functions for game state.

These produce plain strings (with Unicode progress bars) suitable for any
display — Android/mobile UI.  No dependency on Kivy or any UI library.

Used by Android popups and tests without depending on a terminal UI.
"""

from __future__ import annotations

from ..session.game_session import GameSession

# Chinese stage suffixes for realm display.
_STAGE_CN = ["", "一层", "二层", "三层", "四层", "五层", "六层", "七层", "八层", "九层"]


def _stage_suffix(stage: int) -> str:
    if 1 <= stage <= 9:
        return _STAGE_CN[stage]
    return f" {stage}层"


def _bar(current: int, maximum: int, width: int = 10) -> str:
    if maximum <= 0:
        return "░" * width
    filled = max(0, min(int(width * current / maximum), width))
    return "█" * filled + "░" * (width - filled)


def _spirit_root_str(session: GameSession) -> str:
    parts = []
    if session.spirit_root:
        parts.append(session.spirit_root)
    if session.spirit_root_grade:
        parts.append(f"({session.spirit_root_grade}级)")
    return " ".join(parts) if parts else "未觉醒"


def _insight_required(session: GameSession) -> int:
    """Insight needed to break out of the current realm (0 if unknown/terminal)."""
    from ..game.constants import REALM_CONFIGS
    cfg = REALM_CONFIGS.get(getattr(session, "realm", ""))
    if not isinstance(cfg, dict):
        return 0
    try:
        return int(cfg.get("insight_required", 0))
    except (TypeError, ValueError):
        return 0


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
    """One-line compact status."""
    realm_str = f"{session.realm}{_stage_suffix(session.realm_stage)}"
    hp = f"HP:{session.hp}/{session.hp_max}"
    mp = f"MP:{session.mp}/{session.mp_max}"
    insight = getattr(session, "insight", 0)
    insight_req = _insight_required(session)
    insight_str = f"感悟:{insight}/{insight_req}" if insight_req else f"感悟:{insight}"
    prep_met, prep_total = _breakthrough_requirement_count(session)
    prep_str = f" | 准备:{prep_met}/{prep_total}" if prep_total else ""
    loc = session.location or "未知"
    combat_marker = " ⚔" if session.combat else ""
    return f"[{realm_str} | {hp} | {mp} | {insight_str}{prep_str} | 地点:{loc} | 第{session.turn_count}回合{combat_marker}]"


def format_status_card(session: GameSession) -> str:
    """Multi-line character card."""
    realm_str = f"{session.realm}{_stage_suffix(session.realm_stage)}"
    hp_bar = _bar(session.hp, session.hp_max)
    mp_bar = _bar(session.mp, session.mp_max)
    xp_bar = _bar(session.experience, session.experience_to_next)
    insight = getattr(session, "insight", 0)
    insight_req = _insight_required(session)
    insight_bar = _bar(insight, insight_req) if insight_req else ""
    prep_met, prep_total = _breakthrough_requirement_count(session)

    lines = [
        f"  姓名:   {session.char_name or '未命名'}",
        f"  年龄:   {getattr(session, 'age', 16)}",
        f"  境界:   {realm_str}",
        f"  HP:     {hp_bar} {session.hp}/{session.hp_max}",
        f"  MP:     {mp_bar} {session.mp}/{session.mp_max}",
        f"  灵根:   {_spirit_root_str(session)}",
        f"  天赋:   {getattr(session, 'talent', '') or '未显'}",
        f"  家世:   {getattr(session, 'family_background', '') or '凡俗'}",
        f"  气运:   {getattr(session, 'luck', '') or '平稳'}",
        f"  经验:   {xp_bar} {session.experience}/{session.experience_to_next}",
        f"  感悟:   {insight_bar} {insight}/{insight_req}" if insight_req else f"  感悟:   {insight}",
        f"  准备:   {prep_met}/{prep_total}（破境资源/机缘）" if prep_total else "  准备:   无额外要求",
        f"  寿命:   {session.lifespan} 年",
        f"  灵石:   {session.gold}",
        f"  地点:   {session.location or '未知'}" + (f" - {session.region}" if session.region else ""),
        f"  回合:   {session.turn_count}",
    ]
    if session.status_effects:
        effects = ", ".join(session.status_effects) if isinstance(session.status_effects, list) else str(session.status_effects)
        lines.append(f"  状态:   {effects}")
    if session.combat:
        lines.append("  ⚔ 战斗中")
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
            mp_cost = tech.get("mp_cost", "")
            element = tech.get("element", "")
            parts = [f"  · {name} Lv.{level}"]
            if typ:
                parts.append(f"[{typ}]")
            if mp_cost:
                parts.append(f"MP:{mp_cost}")
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


def format_combat(session: GameSession) -> str:
    """Format combat state as readable text."""
    combat = session.combat
    if not combat:
        return "  (未在战斗中)"

    phase = combat.get("phase", "idle")
    player = combat.get("player", {})
    enemy = combat.get("enemy", {})
    turn = combat.get("turn_count", 0)

    lines = [
        f"  ⚔ 战斗 - 第 {turn} 回合 ({phase})",
        f"  ┌ {player.get('name', '你')}",
        f"  │ HP: {_bar(player.get('hp', 0), player.get('hp_max', 1))} {player.get('hp', 0)}/{player.get('hp_max', 0)}",
        f"  │ MP: {_bar(player.get('mp', 0), player.get('mp_max', 1))} {player.get('mp', 0)}/{player.get('mp_max', 0)}",
        f"  └ 境界: {player.get('realm', '?')}",
        "  VS",
        f"  ┌ {enemy.get('name', '敌人')}",
        f"  │ HP: {_bar(enemy.get('hp', 0), enemy.get('hp_max', 1))} {enemy.get('hp', 0)}/{enemy.get('hp_max', 0)}",
        f"  │ MP: {_bar(enemy.get('mp', 0), enemy.get('mp_max', 1))} {enemy.get('mp', 0)}/{enemy.get('mp_max', 0)}",
        f"  └ 境界: {enemy.get('realm', '?')}",
    ]

    narrative = combat.get("narrative", "")
    if narrative:
        lines.append(f"  > {narrative}")

    actions = combat.get("available_actions", [])
    if actions:
        action_names = {
            "attack": "普攻", "technique": "功法", "item": "丹药",
            "defend": "防御", "flee": "逃跑",
        }
        labels = [action_names.get(a, a) for a in actions]
        lines.append(f"  可用操作: {' / '.join(labels)}")

    return "\n".join(lines)


def format_realm(session: GameSession) -> str:
    """Format realm/breakthrough info."""
    from ..game.constants import REALM_ORDER

    realm_str = f"{session.realm}{_stage_suffix(session.realm_stage)}"
    xp_bar = _bar(session.experience, session.experience_to_next)
    insight = getattr(session, "insight", 0)
    insight_req = _insight_required(session)
    insight_bar = _bar(insight, insight_req) if insight_req else ""

    lines = [
        f"  境界: {realm_str}",
        f"  经验: {xp_bar} {session.experience}/{session.experience_to_next}",
    ]
    if insight_req:
        lines.append(f"  感悟: {insight_bar} {insight}/{insight_req}（突破所需）")
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
