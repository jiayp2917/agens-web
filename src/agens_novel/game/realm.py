"""Realm system — breakthrough logic and spirit root modifiers.

Provides ``RealmConfig`` dataclass and ``RealmSystem`` with methods for
checking breakthrough eligibility, calculating success rates, and executing
breakthrough attempts.
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass, field
from typing import Any

from .constants import (
    ATTRIBUTE_DEFAULT,
    REALM_CONFIGS,
    REALM_ORDER,
    SPIRIT_ROOT_MAP,
    compute_breakthrough_lifespan,
    format_realm_name,
    normalize_attribute_value,
)

log = logging.getLogger(__name__)

_QI_REFINING_BASE_AGE = 16
_QI_REFINING_YEARS_PER_STAGE = 2
_QI_REFINING_TURNS_PER_STAGE = 3
BREAKTHROUGH_BLOCKING_EFFECTS = ("根基重创", "修为未复", "走火入魔")


def breakthrough_blocking_effects(effects: Any) -> list[str]:
    """Return active breakthrough blockers from string or structured effects."""
    if not isinstance(effects, list):
        return []
    blockers: list[str] = []
    for effect in effects:
        if isinstance(effect, str):
            name = effect.strip()
        elif isinstance(effect, dict):
            name = str(effect.get("name") or effect.get("effect") or effect.get("status") or "").strip()
        else:
            name = ""
        if name in BREAKTHROUGH_BLOCKING_EFFECTS and name not in blockers:
            blockers.append(name)
    return blockers


@dataclass
class RealmConfig:
    """Configuration for a single cultivation realm."""

    name: str = ""
    stages: int = 1
    lifespan: int = 100
    breakthrough_base_rate: float = 0.80
    spirit_root_bonus: dict[str, float] = field(default_factory=dict)
    breakthrough_requirements: list[dict[str, str]] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RealmConfig:
        """Create a RealmConfig from a raw dict (e.g. from REALM_CONFIGS)."""
        return cls(
            name=data.get("name", ""),
            stages=data.get("stages", 1),
            lifespan=data.get("lifespan", 100),
            breakthrough_base_rate=data.get("breakthrough_base_rate", 0.80),
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
        game_over = getattr(session, "game_over", False)

        if game_over:
            return False, "游戏已结束，无法突破。"
        effects = getattr(session, "status_effects", [])
        if breakthrough_blocking_effects(effects):
            return False, "根基尚未恢复，需先疗伤稳固后方可突破。"

        cfg = self.get_realm_config(realm)
        if cfg is None:
            return False, f"未知境界: {realm}"

        # Must be at the final stage of the current realm.
        if realm_stage < cfg.stages:
            return False, f"当前境界{format_realm_name(realm, realm_stage)}，需达到{format_realm_name(realm, cfg.stages)}方可突破。"

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

        attrs = getattr(session, "attributes", {})
        if isinstance(attrs, dict):
            comprehension = normalize_attribute_value(attrs.get("comprehension", ATTRIBUTE_DEFAULT))
            root_bone = normalize_attribute_value(attrs.get("root_bone", ATTRIBUTE_DEFAULT))
            luck = normalize_attribute_value(attrs.get("luck", ATTRIBUTE_DEFAULT))
            base_rate += (comprehension - ATTRIBUTE_DEFAULT) * 0.015
            base_rate += (root_bone - ATTRIBUTE_DEFAULT) * 0.015
            base_rate += (luck - ATTRIBUTE_DEFAULT) * 0.01

        if realm == "练气":
            age = int(getattr(session, "age", _QI_REFINING_BASE_AGE) or _QI_REFINING_BASE_AGE)
            if age >= 70:
                base_rate -= 0.35
            elif age >= 50:
                base_rate -= 0.15

        # Clamp to [0.0, 1.0].
        return max(0.05, min(0.95, base_rate))

    # ─────────────────────────────────────────────────────────────────────
    # Breakthrough execution
    # ─────────────────────────────────────────────────────────────────────

    def attempt_breakthrough(self, session: Any) -> dict[str, Any]:
        """Execute a breakthrough attempt.

        Returns a delta dict to be applied via ``apply_delta``.  On success
        the realm advances; on failure a status effect records the backlash.
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
                    "lifespan": compute_breakthrough_lifespan(
                        next_realm,
                        int(getattr(session, "lifespan", 1) or 1),
                        attributes=getattr(session, "attributes", {}),
                        talent=str(getattr(session, "talent", "") or ""),
                        difficulty=str(getattr(session, "difficulty", "") or ""),
                    ),
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
            character_delta: dict[str, Any] = {}
            status_effect = self._failure_status_effect(session)
            if status_effect in {"根基重创", "修为未复"}:
                character_delta["lifespan"] = self._failure_lifespan_delta(session)
            if status_effect == "根基重创":
                character_delta["status_effects_add"] = ["根基重创", "修为未复"]
            return {
                "character": character_delta,
                "meta": {
                    "breakthrough_result": "failure",
                    "status_effect_add": status_effect,
                },
            }

    # ─────────────────────────────────────────────────────────────────────
    # Small-layer (stage) advancement within a realm
    # ─────────────────────────────────────────────────────────────────────

    def try_advance_stage(self, session: Any) -> dict[str, Any] | None:
        """Check if the player can advance to the next small layer.

        Called after settled chronicle turns. Stage progress is event-like:
        low-risk choices advance slowly, risky or fortunate turns can advance
        faster, but no XP resource is tracked.

        Returns a delta dict for ``apply_delta``, or ``None`` if no advancement
        is possible right now.
        """
        realm = getattr(session, "realm", "练气")
        stage = getattr(session, "realm_stage", 1)

        cfg = self.get_realm_config(realm)
        if cfg is None:
            return None

        if stage >= cfg.stages:
            return None  # at max layer — need breakthrough, not stage advance
        effects = getattr(session, "status_effects", [])
        if breakthrough_blocking_effects(effects):
            return None

        min_stage = self._minimum_stage_for_chronicle_pace(session, cfg)
        if min_stage > stage:
            return self._stage_delta(min_stage, cfg.stages, paced=True)

        attrs = getattr(session, "attributes", {}) if hasattr(session, "attributes") else {}
        comprehension = (
            normalize_attribute_value(attrs.get("comprehension", ATTRIBUTE_DEFAULT))
            if isinstance(attrs, dict) else ATTRIBUTE_DEFAULT
        )
        root_bone = (
            normalize_attribute_value(attrs.get("root_bone", ATTRIBUTE_DEFAULT))
            if isinstance(attrs, dict) else ATTRIBUTE_DEFAULT
        )
        rate = (
            0.22
            + max(0, comprehension - ATTRIBUTE_DEFAULT) * 0.03
            + max(0, root_bone - ATTRIBUTE_DEFAULT) * 0.03
        )
        if random.random() > min(0.55, rate):
            return None

        # Advance to next layer within the same realm.
        next_stage = stage + 1

        return self._stage_delta(next_stage, cfg.stages, paced=False)

    def _failure_status_effect(self, session: Any) -> str:
        if getattr(session, "realm", "练气") == "练气":
            age = int(getattr(session, "age", _QI_REFINING_BASE_AGE) or _QI_REFINING_BASE_AGE)
            if age >= 70:
                return "根基重创"
            if age >= 50:
                return "修为未复"
        return "走火入魔"

    def _failure_lifespan_delta(self, session: Any) -> str:
        age = int(getattr(session, "age", _QI_REFINING_BASE_AGE) or _QI_REFINING_BASE_AGE)
        if age >= 70:
            return "-20"
        if age >= 50:
            return "-10"
        return "-5"

    def _minimum_stage_for_chronicle_pace(self, session: Any, cfg: RealmConfig) -> int:
        """Keep early Qi Refining from lagging behind a multi-year chronicle."""
        if getattr(session, "realm", "练气") != "练气":
            return int(getattr(session, "realm_stage", 1) or 1)
        age = int(getattr(session, "age", _QI_REFINING_BASE_AGE) or _QI_REFINING_BASE_AGE)
        turn_count = int(getattr(session, "turn_count", 0) or 0)
        years_elapsed = max(0, age - _QI_REFINING_BASE_AGE)
        stage_from_years = 1 + years_elapsed // _QI_REFINING_YEARS_PER_STAGE
        stage_from_turns = 1 + turn_count // _QI_REFINING_TURNS_PER_STAGE
        return max(1, min(cfg.stages, stage_from_years, stage_from_turns))

    @staticmethod
    def _stage_delta(next_stage: int, max_stage: int, *, paced: bool) -> dict[str, Any]:
        delta: dict[str, Any] = {
            "character": {
                "realm_stage": next_stage,
            },
            "meta": {
                "stage_advanced": True,
                "new_stage": next_stage,
                "max_stage": max_stage,
            },
        }
        if paced:
            delta["meta"]["stage_advance_reason"] = "chronicle_pace"
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
