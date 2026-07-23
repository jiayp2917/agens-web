"""Profile validation and deterministic session initialization for new games."""

from __future__ import annotations

from typing import Any

from ..game.constants import (
    ATTRIBUTE_KEYS,
    ATTRIBUTE_MAX,
    ATTRIBUTE_MIN,
    ATTRIBUTE_TOTAL,
    DIFFICULTY_OPTIONS,
    FAMILY_BACKGROUNDS,
    SPIRIT_ROOTS,
    TALENT_OPTIONS,
    compute_starting_lifespan,
)
from ..rule_rng import new_run_seed
from ..session.game_session import GameSession
from ..utils.strings import dedupe_strings
from .profile_opening import profile_default_world

PROFILE_ATTRIBUTE_TOTAL = ATTRIBUTE_TOTAL
PROFILE_MANUAL_ATTRIBUTE_MIN = 2
PROFILE_MANUAL_ATTRIBUTE_MAX = 8
PROFILE_RANDOM_ATTRIBUTE_MIN = ATTRIBUTE_MIN
PROFILE_RANDOM_ATTRIBUTE_MAX = ATTRIBUTE_MAX
PROFILE_REWARDED_ATTRIBUTE_MAX = ATTRIBUTE_MAX
_PROFILE_ATTRIBUTE_DEFAULT = PROFILE_ATTRIBUTE_TOTAL // len(ATTRIBUTE_KEYS)
_ALLOW_LEGACY_BONUS_ATTRIBUTES = "_allow_legacy_bonus_attributes"


def apply_profile_session(session: GameSession, profile: dict[str, Any]) -> None:
    """Initialize a deterministic session from the character form profile."""
    attrs = normalize_profile_attributes(
        profile.get("attributes", {}),
        random_mode=bool(profile.get("randomize_attributes")),
        allow_legacy_bonus=bool(profile.get(_ALLOW_LEGACY_BONUS_ATTRIBUTES)),
    )

    session.reset()
    session.game_started = True
    session.game_over = False
    session.turn_count = 0
    session.rule_rng_counter = 0
    session.run_seed = new_run_seed()
    session.char_name = str(profile.get("char_name") or "无名")
    session.realm = "练气"
    session.realm_stage = 1
    session.age = int(profile.get("age") or 16)
    session.talent = str(profile.get("talent") or TALENT_OPTIONS[0])
    session.spirit_root = str(profile.get("spirit_root") or SPIRIT_ROOTS[0]["name"])
    session.spirit_root_grade = str(profile.get("spirit_root_grade") or "")
    session.family_background = str(profile.get("family_background") or FAMILY_BACKGROUNDS[0])
    session.difficulty = str(profile.get("difficulty") or DIFFICULTY_OPTIONS[1])
    session.attributes = attrs
    session.lifespan = compute_starting_lifespan(
        session.realm,
        attributes=attrs,
        talent=session.talent,
        difficulty=session.difficulty,
        extra_lifespan=int(profile.get("extra_lifespan") or 0),
    )
    session.techniques = list(
        profile.get("techniques") or [{"name": "基础吐纳术", "level": 1, "type": "内功"}]
    )
    session.inventory = list(
        profile.get("inventory") or [{"name": "粗布道袍", "quantity": 1, "type": "防具"}]
    )
    legacy_talents = profile.get("legacy_talents")
    opening_titles = profile.get("opening_titles")
    session.legacy_talents = dedupe_strings(
        legacy_talents if isinstance(legacy_talents, list) else []
    )
    session.titles = dedupe_strings(opening_titles if isinstance(opening_titles, list) else [])
    default_scene, default_location, default_region, default_lore = profile_default_world(profile)
    session.current_scene = str(profile.get("current_scene") or default_scene)
    session.location = str(profile.get("location") or default_location)
    session.region = str(profile.get("region") or default_region)
    session.discovered_locations = [session.location]
    session.lore_facts = [default_lore]


def normalize_profile_attributes(
    incoming_attrs: Any,
    *,
    random_mode: bool = False,
    allow_legacy_bonus: bool = False,
) -> dict[str, int]:
    """Validate and normalize character-creation attributes.

    GAME_MODE_SPEC section 4.1 defines the public profile contract: manual
    creation uses six attributes, each 2-8, with a fixed total of 30. Random
    creation is normalized before this function is called and may use 0-10,
    still totaling 30. Account legacy bonuses are applied after the public
    input is validated, so service code may opt into a post-bonus total above
    30 while each attribute remains on the 0-10 gameplay scale.
    """
    if not incoming_attrs:
        return {key: _PROFILE_ATTRIBUTE_DEFAULT for key in ATTRIBUTE_KEYS}
    if not isinstance(incoming_attrs, dict):
        raise ValueError("attributes must be an object")

    missing = [key for key in ATTRIBUTE_KEYS if key not in incoming_attrs]
    unknown = [str(key) for key in incoming_attrs if key not in ATTRIBUTE_KEYS]
    if missing or unknown:
        raise ValueError("attributes must contain exactly the six v5 keys")

    attrs: dict[str, int] = {}
    for key in ATTRIBUTE_KEYS:
        value = incoming_attrs[key]
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError("attribute values must be integers")
        attrs[key] = value

    total = sum(attrs.values())
    if allow_legacy_bonus:
        _validate_legacy_attributes(attrs, total)
        return attrs
    if total != PROFILE_ATTRIBUTE_TOTAL:
        raise ValueError("manual attributes must sum to 30")
    if random_mode:
        _validate_attribute_range(
            attrs, PROFILE_RANDOM_ATTRIBUTE_MIN, PROFILE_RANDOM_ATTRIBUTE_MAX, "random"
        )
        return attrs
    _validate_attribute_range(
        attrs, PROFILE_MANUAL_ATTRIBUTE_MIN, PROFILE_MANUAL_ATTRIBUTE_MAX, "manual"
    )
    return attrs


def _validate_legacy_attributes(attrs: dict[str, int], total: int) -> None:
    if total < PROFILE_ATTRIBUTE_TOTAL:
        raise ValueError("attributes must not drop below the 30 point pool")
    _validate_attribute_range(
        attrs, PROFILE_RANDOM_ATTRIBUTE_MIN, PROFILE_REWARDED_ATTRIBUTE_MAX, "legacy-bonus"
    )


def _validate_attribute_range(
    attrs: dict[str, int], minimum: int, maximum: int, label: str
) -> None:
    if not all(minimum <= value <= maximum for value in attrs.values()):
        raise ValueError(f"{label} attributes must stay between {minimum} and {maximum}")
