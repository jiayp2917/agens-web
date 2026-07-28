"""Judge invocation and chronicle-event quality guards."""

from __future__ import annotations

from unittest.mock import patch

from agens_novel.engine.event_catalog import (
    CHRONICLE_EVENTS,
    _format_event_lore,
    select_chronicle_event,
)
from agens_novel.engine.game_engine import GameEngine
from agens_novel.engine.turn_rules import classify_choice, settle_turn
from agens_novel.session.game_session import GameSession


def test_choice_category_accepts_visible_route_semantics() -> None:
    cases = [
        ("A\u3010\u7a33\u59a5\u3011\u95ed\u5173\u7a33\u56fa", "\u7a33\u59a5"),
        ("\u3010\u7a33\u59a5\u3011\u95ed\u5173\u7a33\u56fa", "\u7a33\u59a5"),
        ("\u673a\u9047\uff1a\u62dc\u8bbf\u540c\u95e8", "\u673a\u9047"),
        ("\u3010\u98ce\u9669\u3011\u63a2\u67e5\u7981\u5730", "\u98ce\u9669"),
        ("\u6c14\u8fd0:\u968f\u7f18\u800c\u884c", "\u6c14\u8fd0"),
    ]

    for text, expected in cases:
        assert classify_choice(text) == expected


def test_judge_not_triggered_for_plain_risk_word_without_authoritative_delta(monkeypatch) -> None:
    monkeypatch.setenv("AGNES_API_KEY", "test-model-key")
    engine = GameEngine()
    engine.game_session.game_started = True
    engine.game_session.last_choices = ["稳妥修行", "拜访同门", "探查禁地边缘", "随缘而行"]
    calls: list[str] = []

    def runner(agent_name, user_input, session, **kw):
        calls.append(agent_name)
        if agent_name == "narrator":
            return {
                "narrative": "他只在禁地边缘听闻旧事，并未真正涉险。",
                "state_delta": {
                    "character": {},
                    "world": {"lore_add": ["禁地边缘近日有人巡查"]},
                    "meta": {},
                },
                "choices": ["返回山门", "询问同门", "继续观察", "随缘而行"],
                "llm_error": "",
            }
        raise AssertionError("judge should not run for non-authoritative risk color text")

    with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=runner):
        engine.handle_action("探查禁地边缘")

    assert calls == ["narrator"]


def test_authoritative_rewards_are_not_taken_from_narrator_without_judge(monkeypatch) -> None:
    monkeypatch.setenv("AGNES_API_KEY", "test-model-key")
    monkeypatch.setattr(
        "agens_novel.engine.turn_rules.select_chronicle_event",
        lambda session, category, new_age: {
            "id": "reward-test",
            "category": category,
            "event_type": "risk",
            "stage_goal": "核验护身符来历",
            "lore": "医修要求核验护身符的真实来历。",
            "allowed_delta_types": ["techniques_add"],
            "choice_hints": ["调息", "问药", "试药", "随缘"],
        },
    )
    engine = GameEngine()
    engine.game_session.game_started = True
    engine.game_session.last_choices = ["稳妥修行", "拜访同门", "探查禁地边缘", "随缘而行"]
    calls: list[str] = []
    model_statuses: list[tuple[str, str]] = []
    engine.on_model_result = (
        lambda agent, source, status, model_set, base_url_set, key_set, config_source, diagnostics: (
            model_statuses.append((agent, status))
        )
    )

    def runner(agent_name, user_input, session, **kw):
        calls.append(agent_name)
        if agent_name == "narrator":
            return {
                "narrative": "验真者从医修处习得护身诀。",
                "state_delta": {
                    "character": {"techniques_add": [{"name": "护身诀", "level": 1}]},
                    "world": {},
                    "meta": {},
                },
                "choices": ["继续温养", "打听丹方", "试探禁地", "随缘行事"],
                "llm_error": "",
            }
        return {}

    with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=runner):
        engine.handle_action("习得护身诀")

    assert calls == ["narrator"]
    assert not any(agent == "judge" for agent, _status in model_statuses)
    assert engine.game_session.turn_count == 1
    assert not any(item.get("name") == "护身诀" for item in engine.game_session.techniques)


def test_stage_feedback_adds_world_lore_every_four_turns() -> None:
    session = GameSession(location="青岚山门", turn_count=4, realm="筑基", realm_stage=2)

    delta = settle_turn("A", session)

    assert delta["world"]["lore_add"]
    assert "青岚山门" in delta["world"]["lore_add"][0]
    assert "筑基中期" in delta["world"]["lore_add"][0]
    assert "筑基2层" not in delta["world"]["lore_add"][0]


def test_stage_feedback_uses_route_event_pools() -> None:
    expected_markers = {
        "A": ("根基", "课表", "差事"),
        "B": ("消息", "旧闻", "讲评"),
        "C": ("异动", "约斗", "旧伤"),
        "D": ("签文", "小兆", "因果账"),
    }
    for choice, markers in expected_markers.items():
        session = GameSession(location="青岚山门", turn_count=4, realm="筑基", realm_stage=2)
        delta = settle_turn(choice, session)
        lore = delta["world"]["lore_add"][0]
        assert any(marker in lore for marker in markers)
        assert "筑基中期" in lore or choice != "A"


def test_stage_feedback_pool_rotates_across_later_phases() -> None:
    session = GameSession(location="青岚山门", turn_count=4)
    early = settle_turn("B", session)["world"]["lore_add"][0]

    session.turn_count = 8
    middle = settle_turn("B", session)["world"]["lore_add"][0]

    session.turn_count = 12
    later = settle_turn("B", session)["world"]["lore_add"][0]

    assert len({early, middle, later}) == 3


def test_chronicle_event_context_is_selected_every_turn() -> None:
    session = GameSession(location="潮音渡口", region="沧澜群岛", turn_count=1)
    session.world_profile = {
        "world_name": "沧澜群岛",
        "world_key": "ocean",
        "fate_profile": [{"label": "天命", "score": 4}],
        "event_weights": {"气运": 3},
    }

    event = select_chronicle_event(session, "气运", 18)

    assert event["id"]
    assert event["category"] == "气运"
    assert event["stage_goal"]
    assert event["allowed_delta_types"]
    assert event["choice_hints"] and len(event["choice_hints"]) == 4
    assert "天命" in event["matched_fates"]


def test_event_lore_strips_terminal_punctuation_before_template_suffix() -> None:
    event = next(item for item in CHRONICLE_EVENTS if item.id == "luck-world-echo")
    session = GameSession(location="荒岭接引营", region="西陲裂土", turn_count=8)
    session.world_profile = {
        "world_name": "西陲裂土",
        "world_key": "frontier",
        "current_conflicts": ["镇岳宗与血煞盟在荒岭外围交锋。"],
    }

    lore = _format_event_lore(event, session, 32, "frontier")

    assert "交锋的传闻" in lore
    assert "。的传闻" not in lore


def test_fixed_route_chronicle_event_avoids_recent_reuse() -> None:
    session = GameSession(location="青岚山门", turn_count=1)
    seen: list[str] = []

    for turn in range(1, 9):
        session.turn_count = turn
        event = select_chronicle_event(session, "稳妥", 18 + turn)
        assert event["id"] not in seen[-3:]
        seen.append(event["id"])
        session.turn_history.append({"delta": {"meta": {"event_id": event["id"]}}})

    assert len(set(seen[:4])) == 4


def test_settle_turn_records_event_meta_without_forcing_authoritative_rewards() -> None:
    session = GameSession(location="青岚山门", turn_count=1)
    delta = settle_turn("B", session)

    assert delta["meta"]["event_id"]
    assert delta["meta"]["event_type"]
    assert delta["meta"]["event_lore"]
    assert delta["meta"]["stage_goal"]
    assert delta["meta"]["allowed_delta_types"]
    assert "inventory_add" not in delta["character"]
