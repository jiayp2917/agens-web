"""Realm system — breakthrough logic and spirit root modifiers.

Provides ``RealmConfig`` dataclass and ``RealmSystem`` with methods for
checking breakthrough eligibility, calculating success rates, and executing
breakthrough attempts.
"""

from __future__ import annotations

import random
import logging
from dataclasses import dataclass, field
from typing import Any

from .constants import REALM_ORDER, REALM_CONFIGS, SPIRIT_ROOT_MAP

log = logging.getLogger(__name__)


@dataclass
class RealmConfig:
    """Configuration for a single cultivation realm."""

    name: str = ""
    stages: int = 1
    experience_required: int = 100
    insight_required: int = 0
    breakthrough_base_rate: float = 0.80
    hp_base: int = 100
    mp_base: int = 50
    spirit_root_bonus: dict[str, float] = field(default_factory=dict)
    breakthrough_requirements: list[dict[str, str]] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RealmConfig:
        """Create a RealmConfig from a raw dict (e.g. from REALM_CONFIGS)."""
        return cls(
            name=data.get("name", ""),
            stages=data.get("stages", 1),
            experience_required=data.get("experience_required", 100),
            insight_required=data.get("insight_required", 0),
            breakthrough_base_rate=data.get("breakthrough_base_rate", 0.80),
            hp_base=data.get("hp_base", 100),
            mp_base=data.get("mp_base", 50),
            spirit_root_bonus=data.get("spirit_root_bonus", {}),
            breakthrough_requirements=list(data.get("breakthrough_requirements", [])),
        )


class RealmSystem:
    """Manages realm progression, breakthrough checks, and spirit root effects.

    Usage::

        rs = RealmSystem()
        if rs.can_attempt_breakthrough(session):
            result = rs.attempt_breakthrough(session)
    """

    def __init__(self) -> None:
        # Build RealmConfig objects from the constants table.
        self.REALMS: dict[str, RealmConfig] = {
            name: RealmConfig.from_dict(cfg) for name, cfg in REALM_CONFIGS.items()
        }
        self.REALM_ORDER: list[str] = list(REALM_ORDER)

    # ─────────────────────────────────────────────────────────────────────
    # Lookup helpers
    # ─────────────────────────────────────────────────────────────────────

    def get_realm_config(self, realm: str) -> RealmConfig | None:
        """Return the RealmConfig for a given realm name, or None."""
        return self.REALMS.get(realm)

    def get_next_realm(self, realm: str) -> str | None:
        """Return the realm after the given one, or None if at the end."""
        try:
            idx = self.REALM_ORDER.index(realm)
        except ValueError:
            return None
        next_idx = idx + 1
        if next_idx >= len(self.REALM_ORDER):
            return None
        return self.REALM_ORDER[next_idx]

    # ─────────────────────────────────────────────────────────────────────
    # Breakthrough eligibility
    # ─────────────────────────────────────────────────────────────────────

    def can_attempt_breakthrough(self, session: Any) -> tuple[bool, str]:
        """Check whether a GameSession can attempt a realm breakthrough.

        Returns:
            (can_attempt, reason) — reason is empty string on success.
        """
        realm = getattr(session, "realm", "练气")
        realm_stage = getattr(session, "realm_stage", 1)
        experience = getattr(session, "experience", 0)
        experience_to_next = getattr(session, "experience_to_next", 100)
        insight = getattr(session, "insight", 0)
        game_over = getattr(session, "game_over", False)

        if game_over:
            return False, "游戏已结束，无法突破。"

        cfg = self.get_realm_config(realm)
        if cfg is None:
            return False, f"未知境界: {realm}"

        # Must be at the final stage of the current realm.
        if realm_stage < cfg.stages:
            return False, f"当前境界{realm}第{realm_stage}层，需达到第{cfg.stages}层方可突破。"

        # Must have sufficient experience.
        if experience < experience_to_next:
            return False, f"经验不足({experience}/{experience_to_next})，无法突破。"

        # Must have sufficient insight (感悟/心境) — pure cultivation alone cannot
        # break through.  See the "感悟" gate design in the project notes.
        if insight < cfg.insight_required:
            return False, (
                f"道心未明，感悟不足（{insight}/{cfg.insight_required}）。"
                "闭门造车难成大道——需外出历练、参悟机缘，方可破境。"
            )

        missing = self._missing_breakthrough_requirements(session, cfg)
        if missing:
            return False, "破境准备不足：" + "；".join(missing) + "。"

        # Check if there is a next realm.
        next_realm = self.get_next_realm(realm)
        if next_realm is None:
            return False, "已达最高境界（飞升）。"

        return True, ""

    def _missing_breakthrough_requirements(self, session: Any, cfg: RealmConfig) -> list[str]:
        """Return labels for lightweight breakthrough gates that are not met."""
        flags = _session_flags(session)
        inventory_text = _inventory_text(getattr(session, "inventory", []))
        missing: list[str] = []
        for requirement in cfg.breakthrough_requirements:
            key = requirement.get("key", "")
            label = requirement.get("label", key)
            if not key:
                continue
            if key in flags:
                continue
            aliases = _REQUIREMENT_ALIASES.get(key, ())
            if any(alias in inventory_text for alias in aliases):
                continue
            missing.append(label)
        return missing

    # ─────────────────────────────────────────────────────────────────────
    # Breakthrough rate calculation
    # ─────────────────────────────────────────────────────────────────────

    def calculate_breakthrough_rate(self, session: Any) -> float:
        """Calculate the breakthrough success rate for a session.

        Returns a float between 0.0 and 1.0.
        """
        realm = getattr(session, "realm", "练气")
        cfg = self.get_realm_config(realm)
        if cfg is None:
            return 0.0

        base_rate = cfg.breakthrough_base_rate

        # Spirit root bonus.
        spirit_root = getattr(session, "spirit_root", "")
        spirit_root_grade = getattr(session, "spirit_root_grade", "")
        if spirit_root and spirit_root_grade:
            modifier = self.get_spirit_root_modifier(spirit_root)
            grade_bonus = modifier.get("breakthrough_bonus", 0.0)
            base_rate += grade_bonus

        # Clamp to [0.0, 1.0].
        return max(0.0, min(1.0, base_rate))

    # ─────────────────────────────────────────────────────────────────────
    # Breakthrough execution
    # ─────────────────────────────────────────────────────────────────────

    def attempt_breakthrough(self, session: Any) -> dict[str, Any]:
        """Execute a breakthrough attempt.

        Returns a delta dict to be applied via ``apply_delta``.  On success
        the realm advances; on failure HP drops and a debuff is added.
        """
        can, reason = self.can_attempt_breakthrough(session)
        if not can:
            return {"meta": {"breakthrough_result": "ineligible", "reason": reason}}

        rate = self.calculate_breakthrough_rate(session)
        success = random.random() < rate

        realm = getattr(session, "realm", "练气")
        next_realm = self.get_next_realm(realm)
        next_cfg = self.get_realm_config(next_realm) if next_realm else None

        if success and next_realm and next_cfg:
            log.info("Breakthrough success: %s -> %s", realm, next_realm)
            delta: dict[str, Any] = {
                "character": {
                    "realm": next_realm,
                    "realm_stage": 1,
                    "hp_max": next_cfg.hp_base,
                    "hp": next_cfg.hp_base,
                    "mp_max": next_cfg.mp_base,
                    "mp": next_cfg.mp_base,
                    "experience": "-50",  # consume some experience
                    "experience_to_next": next_cfg.experience_required,
                    "insight": 0,  # reset insight — new realm, new bottleneck
                },
                "meta": {
                    "breakthrough_result": "success",
                    "new_realm": next_realm,
                },
            }
            # Finale flag: ascension to "飞升" triggers the ending.
            if next_realm == "飞升":
                delta["meta"]["finale"] = True
                delta["meta"]["game_over"] = True
                delta["meta"]["game_over_reason"] = "飞升成仙，超脱凡尘，修真之路圆满。"
            return delta
        else:
            log.info("Breakthrough failed: %s (rate=%.2f)", realm, rate)
            current_hp = getattr(session, "hp", 100)
            hp_loss = max(1, int(current_hp * 0.15))
            return {
                "character": {
                    "hp": f"-{hp_loss}",
                    "experience": "-20",
                },
                "meta": {
                    "breakthrough_result": "failure",
                    "status_effect_add": "走火入魔",
                },
            }

    # ─────────────────────────────────────────────────────────────────────
    # Small-layer (stage) advancement within a realm
    # ─────────────────────────────────────────────────────────────────────

    def try_advance_stage(self, session: Any) -> dict[str, Any] | None:
        """Check if the player can advance to the next small layer.

        Called after every action that may grant experience.  When the player
        has enough accumulated XP to fill the current layer and is not yet at
        the realm's maximum stage, they auto-advance one layer.

        Returns a delta dict for ``apply_delta``, or ``None`` if no advancement
        is possible right now.
        """
        realm = getattr(session, "realm", "练气")
        stage = getattr(session, "realm_stage", 1)
        xp = getattr(session, "experience", 0)
        xp_needed = getattr(session, "experience_to_next", 100)

        cfg = self.get_realm_config(realm)
        if cfg is None:
            return None

        if xp < xp_needed:
            return None

        if stage >= cfg.stages:
            return None  # at max layer — need breakthrough, not stage advance

        # Advance to next layer within the same realm.
        next_stage = stage + 1
        hp_gain = max(1, cfg.hp_base // 8)
        mp_gain = max(1, cfg.mp_base // 8)

        delta: dict[str, Any] = {
            "character": {
                "realm_stage": next_stage,
                "experience": f"-{xp_needed}",
                # Keep experience_to_next stable so breakthrough threshold
                # matches the realm config and doesn't drift upward.
                "hp_max": f"+{hp_gain}",
                "hp": f"+{hp_gain}",
                "mp_max": f"+{mp_gain}",
                "mp": f"+{mp_gain}",
            },
            "meta": {
                "stage_advanced": True,
                "new_stage": next_stage,
                "max_stage": cfg.stages,
            },
        }
        return delta

    # ─────────────────────────────────────────────────────────────────────
    # Spirit root modifier
    # ─────────────────────────────────────────────────────────────────────

    def get_spirit_root_modifier(self, spirit_root: str) -> dict[str, Any]:
        """Return the modifier dict for a given spirit root name.

        Returns a dict with keys ``cultivation_bonus`` and ``breakthrough_bonus``.
        Defaults to (1.0, 0.0) if spirit root is unknown.
        """
        sr_data = SPIRIT_ROOT_MAP.get(spirit_root)
        if sr_data is None:
            return {"cultivation_bonus": 1.0, "breakthrough_bonus": 0.0}
        return {
            "cultivation_bonus": sr_data.get("cultivation_bonus", 1.0),
            "breakthrough_bonus": sr_data.get("breakthrough_bonus", 0.0),
        }


_REQUIREMENT_ALIASES: dict[str, tuple[str, ...]] = {
    "foundation_aid": ("筑基丹", "筑基机缘", "筑基护持", "筑基法门"),
    "golden_core_aid": ("结金丹", "凝丹机缘", "金丹法门"),
    "nascent_soul_aid": ("化婴丹", "元婴护法", "生死顿悟"),
    "spirit_transformation_aid": ("化神契机", "神魂试炼", "心魔明悟"),
    "unity_law_aid": ("合体道基", "天地法则", "法则感悟"),
    "mahayana_vow_aid": ("大乘道果", "宏愿因果", "宗门气运"),
    "tribulation_preparation": ("避劫阵", "渡劫场", "雷劫情报", "渡劫准备"),
    "tribulation_elixir": ("渡劫丹", "续命丹", "九转还魂丹"),
    "ascension_protection": ("护身法宝", "雷劫阵", "替劫符", "护道阵"),
}


def _session_flags(session: Any) -> set[str]:
    raw = getattr(session, "breakthrough_flags", [])
    if not isinstance(raw, list):
        return set()
    return {item.strip() for item in raw if isinstance(item, str) and item.strip()}


def _inventory_text(inventory: Any) -> str:
    if not isinstance(inventory, list):
        return ""
    chunks: list[str] = []
    for item in inventory:
        if isinstance(item, str):
            chunks.append(item)
        elif isinstance(item, dict):
            for key in ("name", "type", "rarity", "description"):
                value = item.get(key)
                if isinstance(value, str):
                    chunks.append(value)
    return " ".join(chunks)
