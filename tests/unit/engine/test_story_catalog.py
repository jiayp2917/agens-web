"""Tests for versioned long-form chronicle story bindings."""

from __future__ import annotations

import pytest

from agens_novel.engine.choices import fallback_choices
from agens_novel.engine.story_catalog import (
    STORY_ARCS,
    STORY_RESOLUTION_TURN,
    opening_story_binding,
    story_arc_for_binding,
    story_arc_for_world,
    story_turn_delta,
)
from agens_novel.engine.turn_rules import settle_turn
from agens_novel.session.game_session import GameSession

_ROUTE_EXPECTATIONS = {
    "稳妥": "route_ending",
    "机遇": "route_ending",
    "风险": "failure_branch",
    "气运": "route_ending",
}


def _bound_session(world_key: str = "forest") -> GameSession:
    binding = opening_story_binding(world_key, ["苦修", "宗门"])
    return GameSession(
        game_started=True,
        location="青岚药圃",
        region="青岚药境",
        story_key=binding["story_key"],
        story_version=binding["story_version"],
        story_state=binding["story_state"],
        world_profile={"world_key": world_key, "fate_hooks": ["苦修", "宗门"]},
    )


def test_story_catalog_has_versioned_complete_arcs() -> None:
    assert len(STORY_ARCS) >= 3
    assert len({(arc.key, arc.version) for arc in STORY_ARCS}) == len(STORY_ARCS)
    for arc in STORY_ARCS:
        assert arc.opening
        assert arc.failure_branch
        assert set(arc.endings) == {"稳妥", "机遇", "风险", "气运"}
        assert len(arc.phases) >= 5
        assert arc.phases[0].min_turn == 1
        assert arc.phases[-1].max_turn == STORY_RESOLUTION_TURN


def test_each_world_pack_selects_its_own_story() -> None:
    bindings = {
        world_key: story_arc_for_world(world_key, []).key
        for world_key in ("frontier", "clan", "ocean", "forest")
    }

    assert len(set(bindings.values())) == 4
    assert bindings["frontier"] == "border-vein-crisis"
    assert bindings["clan"] == "alliance-old-oath"
    assert bindings["ocean"] == "sunken-star-tide"
    assert bindings["forest"] == "herb-boundary-blight"


def test_story_binding_requires_exact_version() -> None:
    binding = opening_story_binding("ocean", ["天命"])

    assert story_arc_for_binding(binding["story_key"], binding["story_version"]) is not None
    assert story_arc_for_binding(binding["story_key"], binding["story_version"] + 1) is None


def test_story_progress_is_rule_owned_and_visible_every_four_turns() -> None:
    session = _bound_session()
    session.turn_count = 4

    delta = settle_turn("A", session)

    assert delta["meta"]["story_phase"] == "入局"
    assert delta["meta"]["story_goal"]
    assert delta["meta"]["story_beat"]
    assert delta["world"]["story_update"]["route_counts"]["稳妥"] == 1
    assert delta["world"]["story_update"]["key_promises"]
    assert delta["meta"]["story_beat"] in delta["world"]["lore_add"]

    session.apply_delta(delta)
    assert session.story_state["progress_turns"] == 4
    assert session.story_state["faction_attitudes"]["青岚谷"] == 1


def test_fallback_choices_reference_current_story_goal_and_thread() -> None:
    session = _bound_session()

    choices = fallback_choices(session)

    assert len(choices) == 4
    assert session.story_state["stage_goal"] in choices[0]
    assert session.story_state["unresolved_threads"][0] in choices[1]
    assert all(marker in choices[index] for index, marker in enumerate(("稳妥", "机遇", "风险", "气运")))


def test_story_progress_is_not_applied_before_delta_commit() -> None:
    session = _bound_session()
    session.turn_count = 4
    original = dict(session.story_state)

    delta = settle_turn("C", session)

    assert session.story_state == original
    assert delta["world"]["story_update"]["pressure"] == 2


def test_twenty_turn_slice_keeps_long_story_active() -> None:
    session = _bound_session("ocean")
    session.turn_count = 20
    session.story_state["route_counts"] = {"稳妥": 8, "机遇": 2, "风险": 0, "气运": 1}

    story = story_turn_delta(session, "稳妥", {}, 44)

    assert story["story_status"] == "active"
    assert story["story_update"]["ending"] == ""
    assert story["story_update"]["unresolved_threads"]


def test_story_resolves_at_sixty_turns_without_switching_binding() -> None:
    session = _bound_session("ocean")
    session.turn_count = STORY_RESOLUTION_TURN
    session.story_state["route_counts"] = {"稳妥": 20, "机遇": 8, "风险": 3, "气运": 4}

    story = story_turn_delta(session, "稳妥", {}, 88)

    assert story["story_status"] == "resolved"
    assert story["story_update"]["ending"]
    assert story["story_update"]["unresolved_threads"] == []
    assert session.story_key == "sunken-star-tide"
    assert session.story_version == 1


def test_sixty_turn_story_resolution_ends_the_game_session() -> None:
    session = _bound_session("ocean")
    session.turn_count = STORY_RESOLUTION_TURN
    session.story_state["route_counts"] = {"稳妥": 20, "机遇": 8, "风险": 3, "气运": 4}

    delta = settle_turn("A", session)

    assert delta["meta"]["story_status"] == "resolved"
    assert delta["meta"]["game_over"] is True
    assert delta["meta"]["game_over_reason"]
    session.apply_delta(delta)
    assert session.game_over is True
    assert session.error == delta["meta"]["game_over_reason"]


def test_high_pressure_resolution_uses_failure_branch() -> None:
    session = _bound_session("frontier")
    session.turn_count = STORY_RESOLUTION_TURN
    session.story_state["pressure"] = 7
    arc = story_arc_for_binding(session.story_key, session.story_version)
    assert arc is not None

    story = story_turn_delta(session, "风险", {}, 52)

    assert story["story_update"]["ending"] == arc.failure_branch
    assert story["story_beat"] == arc.failure_branch


def test_resolved_story_is_not_settled_again() -> None:
    session = _bound_session("forest")
    session.story_state["status"] = "resolved"
    session.story_state["ending"] = "旧结局"
    session.turn_count = STORY_RESOLUTION_TURN + 1

    assert story_turn_delta(session, "机遇", {}, 90) == {}


@pytest.mark.parametrize(("category", "expected"), _ROUTE_EXPECTATIONS.items())
def test_sixty_turn_route_has_phase_feedback_and_reachable_ending(
    category: str,
    expected: str,
) -> None:
    session = _bound_session("clan")
    arc = story_arc_for_binding(session.story_key, session.story_version)
    assert arc is not None
    feedback_turns: list[int] = []
    phase_keys: list[str] = []

    for turn in range(1, STORY_RESOLUTION_TURN + 1):
        session.turn_count = turn
        story = story_turn_delta(
            session,
            category,
            {"lore": f"第{turn}回合外界旁证"},
            16 + turn,
        )
        assert story
        phase_keys.append(story["story_update"]["phase_key"])
        if story["story_beat"]:
            feedback_turns.append(turn)
        if turn < STORY_RESOLUTION_TURN:
            assert story["story_status"] == "active"
            assert story["story_update"]["unresolved_threads"]
        session.story_state = story["story_update"]

        if turn == 30:
            restored = GameSession.from_save_dict(session.to_save_dict())
            assert restored.story_key == session.story_key
            assert restored.story_version == session.story_version
            assert restored.story_state == session.story_state
            session = restored

    assert feedback_turns == list(range(4, STORY_RESOLUTION_TURN + 1, 4))
    assert set(phase_keys) == {"opening", "spread", "turning", "choice", "resolution"}
    assert session.story_state["status"] == "resolved"
    assert session.story_state["unresolved_threads"] == []
    expected_ending = arc.failure_branch if expected == "failure_branch" else arc.endings[category]
    assert session.story_state["ending"] == expected_ending


def test_moderate_risk_route_can_reach_risk_ending() -> None:
    session = _bound_session("frontier")
    arc = story_arc_for_binding(session.story_key, session.story_version)
    assert arc is not None
    for turn in range(1, STORY_RESOLUTION_TURN + 1):
        session.turn_count = turn
        category = "稳妥" if turn % 4 == 0 else "风险"
        story = story_turn_delta(session, category, {}, 16 + turn)
        session.story_state = story["story_update"]

    assert session.story_state["route_counts"]["风险"] > max(
        session.story_state["route_counts"][key]
        for key in ("稳妥", "机遇", "气运")
    )
    assert session.story_state["pressure"] < 8
    assert session.story_state["ending"] == arc.endings["风险"]
