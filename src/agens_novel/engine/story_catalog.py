"""Versioned long-form story arc queries and rule-owned progression."""

from __future__ import annotations

import hashlib
import os
from dataclasses import replace
from typing import Any

from ..rule_rng import rule_rng_for_session
from .story_catalog_data import (
    DEFAULT_STORY_CONTENT_VERSION,
    STORY_ARCS,
    StoryArc,
    StoryEvent,
    StoryPhase,
)
from .story_catalog_data import (
    STORY_RESOLUTION_TURN as STORY_RESOLUTION_TURN,
)
from .story_catalog_data import (
    STORY_V2_RESOLUTION_TURN as STORY_V2_RESOLUTION_TURN,
)
from .story_catalog_data import (
    STORY_V3_RESOLUTION_TURN as STORY_V3_RESOLUTION_TURN,
)
from .world_catalog import world_key_for_name

_ARCS_BY_BINDING = {(arc.key, arc.version): arc for arc in STORY_ARCS}


def story_arc_for_world(
    world_key: str,
    fate_tags: list[str] | tuple[str, ...],
    *,
    content_version: int | None = None,
) -> StoryArc:
    """Select the latest compatible arc without depending on model output."""
    tags = {str(tag).strip() for tag in fate_tags if str(tag).strip()}
    selected_version = story_content_version() if content_version is None else content_version
    candidates = [
        arc for arc in STORY_ARCS if world_key in arc.worlds and arc.version == selected_version
    ]
    if not candidates:
        candidates = [
            arc for arc in STORY_ARCS if "forest" in arc.worlds and arc.version == selected_version
        ]
    return max(candidates, key=lambda arc: (len(tags.intersection(arc.fate_tags)), arc.version))


def story_arc_for_binding(story_key: str, story_version: int) -> StoryArc | None:
    """Resolve an exact version; never silently upgrade an existing save."""
    return _ARCS_BY_BINDING.get((story_key, story_version))


def opening_story_binding(
    world_key: str,
    fate_tags: list[str] | tuple[str, ...],
    *,
    content_version: int | None = None,
    run_seed: str = "",
    character_name: str = "",
) -> dict[str, Any]:
    arc = story_arc_for_world(world_key, fate_tags, content_version=content_version)
    first = arc.phases[0]
    state: dict[str, Any] = {
        "status": "active",
        "phase_key": first.key,
        "phase_title": first.title,
        "stage_goal": first.goal,
        "progress_turns": 0,
        "route_counts": {category: 0 for category in ("稳妥", "机遇", "风险", "气运")},
        "pressure": 0,
        "unresolved_threads": [arc.unresolved_thread, first.thread],
        "faction_attitudes": {
            arc.ally_faction: 0,
            arc.rival_faction: 0,
            arc.neutral_faction: 0,
        },
        "key_promises": [],
        "recent_beats": [],
        "ending": "",
    }
    if arc.version == 3:
        state.update(
            {
                "commitments": _v3_commitments(arc, run_seed, character_name),
                "run_seed": run_seed,
                "recent_motifs": [],
                "consequence_log": [],
                "clue_count": 0,
                "event_weight_modifiers": {"稳妥": 0, "机遇": 0, "风险": 0, "气运": 0},
                "arc_resolution": "",
                "post_arc_turns": 0,
            }
        )
    return {
        "story_key": arc.key,
        "story_version": arc.version,
        "story_title": arc.title,
        "story_opening": arc.opening,
        "story_state": state,
    }


def ensure_story_binding(session: Any, *, content_version: int | None = None) -> None:
    """Bind an unversioned session once; preserve every existing exact binding."""
    if str(getattr(session, "story_key", "") or ""):
        return
    profile = getattr(session, "world_profile", None)
    world_profile = profile if isinstance(profile, dict) else {}
    world_key = str(world_profile.get("world_key") or "").strip()
    if not world_key:
        world_key = world_key_for_name(
            str(world_profile.get("world_name") or getattr(session, "region", ""))
        )
    fate_tags = _fate_tags(world_profile)
    binding = opening_story_binding(
        world_key,
        fate_tags,
        content_version=content_version,
        run_seed=str(getattr(session, "run_seed", "") or ""),
        character_name=str(getattr(session, "char_name", "") or ""),
    )
    session.story_key = binding["story_key"]
    session.story_version = binding["story_version"]
    session.story_state = binding["story_state"]


def story_turn_delta(
    session: Any,
    category: str,
    event: dict[str, Any],
    new_age: int,
    game_over_reason: str = "",
) -> dict[str, Any]:
    """Return the next rule-owned story state without mutating the session."""
    binding = _session_story_binding(session)
    if binding is None:
        return {}
    arc, state = binding
    if state.get("status") == "post_arc":
        return _post_arc_turn_delta(arc, state, category, event, new_age)
    if state.get("status") != "active":
        return {}
    turn = max(1, int(getattr(session, "turn_count", 1) or 1))
    phase = _phase_for_turn(arc, turn)
    route_counts = _route_counts(state)
    route_counts[category] = route_counts.get(category, 0) + 1
    due = turn % 4 == 0
    pressure_change = _pressure_change(category) if due else 0
    if arc.version == 3 and category == "风险":
        # Risk still changes faction standing and creates exposure marks, but
        # cannot turn every ninety-turn C route into a fixed pressure failure.
        pressure_change = 0
    v3_effect = _v3_route_effect(state, phase, category, turn) if arc.version == 3 else {}
    pressure_change += int(v3_effect.get("pressure_delta") or 0)
    pressure = max(0, int(state.get("pressure") or 0) + pressure_change)
    v3_resolution = _v3_resolution_context(state, v3_effect)
    attitudes = _faction_attitudes(state, arc)
    _adjust_attitudes(attitudes, arc, category)
    story_event = _v3_story_event(arc, state, phase, category, turn) if arc.version == 3 else None
    status, ending, beat = _story_outcome(
        arc,
        phase,
        category,
        route_counts,
        pressure,
        turn,
        due,
        session,
        event,
        new_age,
        game_over_reason,
        v3_resolution,
    )
    if story_event is not None and due:
        beat = _format_v3_beat(phase, story_event, category, session, event, new_age)
    next_state = _next_story_state(
        state,
        arc,
        phase,
        category,
        route_counts,
        attitudes,
        pressure,
        turn,
        due,
        status,
        ending,
        beat,
    )
    reported_status = status
    if arc.version == 3:
        _apply_v3_turn_state(
            next_state,
            state,
            phase,
            category,
            turn,
            status,
            story_event,
            v3_effect,
        )
        if status in {"resolved", "failed"} and not game_over_reason:
            next_state["status"] = "post_arc"
            next_state["arc_resolution"] = status
            next_state["post_arc_turns"] = 0
            reported_status = "post_arc"
    return {
        "story_update": next_state,
        "story_phase": phase.title,
        "story_goal": phase.goal,
        "story_beat": beat,
        "story_status": reported_status,
    }


def _v3_commitments(arc: StoryArc, run_seed: str, character_name: str) -> list[dict[str, str]]:
    """Generate exactly two catalog-owned commitments for one v3 run."""
    seed = run_seed or f"catalog:{arc.key}:{character_name}"
    categories = ("稳妥", "机遇", "风险", "气运")
    ranked = sorted(
        categories,
        key=lambda category: hashlib.sha256(f"{seed}|{arc.key}|{category}".encode()).hexdigest(),
    )
    commitments: list[dict[str, str]] = []
    for index, category in enumerate(ranked[:2], start=1):
        commitments.append(
            {
                "commitment_id": f"{arc.key}:v3:{index}:{category}",
                "category": category,
                "description": arc.commitments[category],
                "trigger_condition": "前三阶段留下可复核钩子",
                "failure_condition": "第九阶段前未能承受对应代价或压力失控",
                "status": "pending",
            }
        )
    return commitments


def _v3_route_effect(
    state: dict[str, Any], phase: StoryPhase, category: str, turn: int
) -> dict[str, Any]:
    dimensions = dict(phase.route_consequences).get(category, ())
    if category == "稳妥":
        return {"dimensions": dimensions, "pressure_delta": -1}
    if category == "机遇":
        return {"dimensions": dimensions, "clue_delta": 1}
    if category == "风险":
        return {
            "dimensions": dimensions,
            "risk_mark_delta": 1 if turn % 4 == 0 else 0,
        }
    if category == "气运":
        return {
            "dimensions": dimensions,
            "weight_adjustment": 1 if turn % 2 else -1,
            "commitment_focus_delta": 1,
        }
    return {"dimensions": dimensions}


def _v3_story_event(
    arc: StoryArc,
    state: dict[str, Any],
    phase: StoryPhase,
    category: str,
    turn: int,
) -> StoryEvent | None:
    if not phase.events:
        return None
    recent = _string_list(state.get("recent_motifs"))[-5:]
    candidates = [event for event in phase.events if event.motif not in recent]
    seed = str(state.get("run_seed") or getattr(arc, "key", ""))
    digest = hashlib.sha256(f"{seed}|{arc.key}|{turn}|{category}".encode()).digest()
    if not candidates:
        selected = phase.events[int.from_bytes(digest[:2], "big") % len(phase.events)]
        return replace(selected, motif=f"{selected.motif}:turn-{turn}")
    return candidates[int.from_bytes(digest[:2], "big") % len(candidates)]


def _format_v3_beat(
    phase: StoryPhase,
    story_event: StoryEvent,
    category: str,
    session: Any,
    event: dict[str, Any],
    new_age: int,
) -> str:
    route_beat = phase.beats.get(category) or phase.beats["机遇"]
    return _format_beat(f"{story_event.summary} {route_beat}", session, event, new_age)


def _apply_v3_turn_state(
    next_state: dict[str, Any],
    previous_state: dict[str, Any],
    phase: StoryPhase,
    category: str,
    turn: int,
    status: str,
    story_event: StoryEvent | None,
    effect: dict[str, Any],
) -> None:
    """Record rule-owned v3 commitments, motifs, and route consequences."""
    motifs = _string_list(previous_state.get("recent_motifs"))
    if story_event is not None and turn % 4 == 0:
        motifs.append(story_event.motif)
    next_state["recent_motifs"] = motifs[-5:]
    clues = max(0, int(previous_state.get("clue_count") or 0) + int(effect.get("clue_delta") or 0))
    next_state["clue_count"] = clues
    weights = dict(previous_state.get("event_weight_modifiers") or {})
    weights.setdefault("稳妥", 0)
    weights.setdefault("机遇", 0)
    weights.setdefault("风险", 0)
    weights.setdefault("气运", 0)
    if "weight_adjustment" in effect:
        weights[category] = max(-3, min(3, int(weights[category]) + int(effect["weight_adjustment"])))
    next_state["event_weight_modifiers"] = weights
    next_state["risk_marks"] = max(
        0,
        int(previous_state.get("risk_marks") or 0) + int(effect.get("risk_mark_delta") or 0),
    )
    commitment_focus = max(
        0,
        int(previous_state.get("commitment_focus") or 0)
        + int(effect.get("commitment_focus_delta") or 0),
    )
    next_state["commitment_focus"] = commitment_focus
    next_state["commitments"] = _advance_v3_commitments(
        previous_state.get("commitments"),
        turn,
        status,
    )
    log_entries = list(previous_state.get("consequence_log") or [])
    dimensions = list(effect.get("dimensions") or ())
    log_entries.append(
        {
            "turn": turn,
            "phase": phase.key,
            "route": category,
            "dimensions": dimensions,
        }
    )
    next_state["consequence_log"] = log_entries[-30:]


def _v3_resolution_context(state: dict[str, Any], effect: dict[str, Any]) -> dict[str, int]:
    return {
        "clue_count": max(
            0,
            int(state.get("clue_count") or 0) + int(effect.get("clue_delta") or 0),
        ),
        "risk_marks": max(
            0,
            int(state.get("risk_marks") or 0) + int(effect.get("risk_mark_delta") or 0),
        ),
    }


def _v3_risk_arc_failed(session: Any, resolution: dict[str, int]) -> bool:
    """Resolve accumulated C-route exposure once at the v3 arc conclusion."""
    marks = max(0, int(resolution.get("risk_marks") or 0))
    if not marks:
        return False
    rng = rule_rng_for_session(session)
    if rng is None:
        return False
    attributes = getattr(session, "attributes", {})
    aptitude = (
        sum(int(attributes.get(key) or 0) for key in ("root_bone", "comprehension", "luck"))
        if isinstance(attributes, dict)
        else 0
    )
    chance = 0.05 + marks * 0.012
    if getattr(session, "difficulty", "普通") == "困难":
        chance += 0.08
    chance += max(0, 12 - aptitude) * 0.01
    return rng.random("v3_arc_risk") < min(0.65, chance)


def _advance_v3_commitments(
    value: Any,
    turn: int,
    status: str,
) -> list[dict[str, str]]:
    items = value if isinstance(value, list) else []
    stage = "hooked" if turn <= 30 else "pressured" if turn <= 60 else "due"
    stage_rank = {"pending": 0, "hooked": 1, "pressured": 2, "due": 3}
    out: list[dict[str, str]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        copied = {str(key): str(raw) for key, raw in item.items() if isinstance(raw, str)}
        if not copied.get("commitment_id"):
            continue
        current = copied.get("status") or "pending"
        # Both pre-registered commitments must remain visible across the arc.
        # Their route category decides the eventual resolution, not whether the
        # player ever sees the hook, pressure, and due stages.
        if stage_rank.get(stage, 0) > stage_rank.get(current, 0):
            current = stage
        if status == "resolved":
            current = "fulfilled" if current == "due" else "failed"
        elif status == "failed":
            current = "failed"
        copied["status"] = current
        out.append(copied)
    return out[:2]


def _post_arc_turn_delta(
    arc: StoryArc,
    state: dict[str, Any],
    category: str,
    event: dict[str, Any],
    new_age: int,
) -> dict[str, Any]:
    """Continue v3 after its main arc without replaying the final resolution."""
    turn = max(1, int(state.get("progress_turns") or 0) + 1)
    post_turns = max(1, int(state.get("post_arc_turns") or 0) + 1)
    motifs = _string_list(state.get("recent_motifs"))
    post_events = (
        ("余波整饬", "主线收束后的势力仍在重新分配旧账。"),
        ("远行新讯", "一份不属于旧主线的新讯从远方抵达。"),
        ("旧人回响", "此前同行者带来与旧结局不同的后续选择。"),
    )
    available = [item for item in post_events if item[0] not in motifs] or list(post_events)
    selected = available[(post_turns - 1) % len(available)]
    motifs.append(selected[0])
    next_state = dict(state)
    next_state.update(
        {
            "status": "post_arc",
            "post_arc_turns": post_turns,
            "progress_turns": turn,
            "recent_motifs": motifs[-5:],
            "phase_key": "post_arc",
            "phase_title": "余波",
            "stage_goal": "在主线收束后选择下一段道途，不重演已结算的因果。",
            "recent_beats": [*_string_list(state.get("recent_beats"))[-5:], f"{new_age}岁时，{selected[1]}"],
        }
    )
    beat = f"{new_age}岁时，{selected[1]}"
    return {
        "story_update": next_state,
        "story_phase": "余波",
        "story_goal": next_state["stage_goal"],
        "story_beat": beat,
        "story_status": "post_arc",
    }


def _session_story_binding(session: Any) -> tuple[StoryArc, dict[str, Any]] | None:
    story_key = str(getattr(session, "story_key", "") or "")
    try:
        story_version = int(getattr(session, "story_version", 0) or 0)
    except (TypeError, ValueError):
        story_version = 0
    arc = story_arc_for_binding(story_key, story_version)
    if arc is None:
        return None
    current = getattr(session, "story_state", None)
    state = (
        dict(current)
        if isinstance(current, dict)
        else opening_story_binding(
            arc.worlds[0],
            list(arc.fate_tags),
            content_version=arc.version,
            run_seed=str(getattr(session, "run_seed", "") or ""),
            character_name=str(getattr(session, "char_name", "") or ""),
        )["story_state"]
    )
    return arc, state


def _story_outcome(
    arc: StoryArc,
    phase: StoryPhase,
    category: str,
    route_counts: dict[str, int],
    pressure: int,
    turn: int,
    due: bool,
    session: Any,
    event: dict[str, Any],
    new_age: int,
    game_over_reason: str,
    v3_resolution: dict[str, int],
) -> tuple[str, str, str]:
    beat = (
        _format_beat(phase.beats.get(category) or phase.beats["机遇"], session, event, new_age)
        if due
        else ""
    )
    if game_over_reason:
        return "failed", arc.failure_branch, f"{game_over_reason}{arc.failure_branch}"
    if turn < arc.phases[-1].max_turn:
        return "active", "", beat
    if pressure >= 8:
        return ("failed" if arc.version == 3 else "resolved"), arc.failure_branch, arc.failure_branch
    if arc.version == 3:
        if _v3_risk_arc_failed(session, v3_resolution):
            return "failed", arc.failure_branch, arc.failure_branch
        if _dominant_route(route_counts) == "机遇" and int(
            v3_resolution.get("clue_count") or 0
        ) < 3:
            return "failed", arc.failure_branch, arc.failure_branch
    ending = arc.endings[_dominant_route(route_counts)]
    return "resolved", ending, ending


def _next_story_state(
    state: dict[str, Any],
    arc: StoryArc,
    phase: StoryPhase,
    category: str,
    route_counts: dict[str, int],
    attitudes: dict[str, int],
    pressure: int,
    turn: int,
    due: bool,
    status: str,
    ending: str,
    beat: str,
) -> dict[str, Any]:
    unresolved = _string_list(state.get("unresolved_threads"))
    if phase.thread not in unresolved:
        unresolved.append(phase.thread)
    promises = _string_list(state.get("key_promises"))
    promise = arc.commitments.get(category, "") if due else ""
    if promise and promise not in promises:
        promises.append(promise)
    recent_beats = _string_list(state.get("recent_beats"))
    if beat:
        recent_beats.append(beat)
    return {
        "status": status,
        "phase_key": phase.key,
        "phase_title": phase.title,
        "stage_goal": phase.goal,
        "progress_turns": turn,
        "route_counts": route_counts,
        "pressure": pressure,
        "unresolved_threads": unresolved[-6:] if status == "active" else [],
        "faction_attitudes": attitudes,
        "key_promises": promises[-6:],
        "recent_beats": recent_beats[-6:],
        "ending": ending,
    }


def _phase_for_turn(arc: StoryArc, turn: int) -> StoryPhase:
    for phase in arc.phases:
        if phase.min_turn <= turn <= phase.max_turn:
            return phase
    return arc.phases[-1]


def story_content_version() -> int:
    raw = os.environ.get("AGENS_STORY_CONTENT_VERSION", str(DEFAULT_STORY_CONTENT_VERSION)).strip()
    try:
        version = int(raw)
    except ValueError as exc:
        raise RuntimeError("AGENS_STORY_CONTENT_VERSION must be 1, 2, or 3.") from exc
    if version not in {1, 2, 3}:
        raise RuntimeError("AGENS_STORY_CONTENT_VERSION must be 1, 2, or 3.")
    return version


def _fate_tags(world_profile: dict[str, Any]) -> list[str]:
    tags = world_profile.get("fate_hooks")
    if isinstance(tags, list):
        return [str(tag) for tag in tags if str(tag).strip()]
    return []


def _route_counts(state: dict[str, Any]) -> dict[str, int]:
    raw = state.get("route_counts")
    out = {category: 0 for category in ("稳妥", "机遇", "风险", "气运")}
    if isinstance(raw, dict):
        for category in out:
            value = raw.get(category)
            if isinstance(value, int) and not isinstance(value, bool):
                out[category] = max(0, value)
    return out


def _pressure_change(category: str) -> int:
    # Pressure is charged only on four-turn story beats. Luck already carries
    # event-level variance, so it does not add unavoidable long-arc pressure.
    return {"稳妥": -1, "机遇": 0, "风险": 2, "气运": 0}.get(category, 0)


def _faction_attitudes(state: dict[str, Any], arc: StoryArc) -> dict[str, int]:
    defaults = {arc.ally_faction: 0, arc.rival_faction: 0, arc.neutral_faction: 0}
    raw = state.get("faction_attitudes")
    if isinstance(raw, dict):
        for key in defaults:
            value = raw.get(key)
            if isinstance(value, int) and not isinstance(value, bool):
                defaults[key] = max(-10, min(10, value))
    return defaults


def _adjust_attitudes(attitudes: dict[str, int], arc: StoryArc, category: str) -> None:
    if category == "稳妥":
        attitudes[arc.ally_faction] = min(10, attitudes[arc.ally_faction] + 1)
    elif category == "机遇":
        attitudes[arc.neutral_faction] = min(10, attitudes[arc.neutral_faction] + 1)
    elif category == "风险":
        attitudes[arc.rival_faction] = max(-10, attitudes[arc.rival_faction] - 1)


def _dominant_route(route_counts: dict[str, int]) -> str:
    order = ("稳妥", "机遇", "风险", "气运")
    return max(order, key=lambda category: (route_counts.get(category, 0), -order.index(category)))


def _format_beat(template: str, session: Any, event: dict[str, Any], new_age: int) -> str:
    event_lore = str(event.get("lore") or "").strip()
    prefix = f"{new_age}岁时，"
    if event_lore:
        return f"{prefix}{template} 同期外界记载：{event_lore}"
    return f"{prefix}{template}"


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]
