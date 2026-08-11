"""Tests for local preset story fallback."""

from __future__ import annotations

from unittest.mock import patch

from agens_novel.engine.choices import choice_with_semantic
from agens_novel.engine.game_engine import GameEngine
from agens_novel.engine.local_story import (
    DEFAULT_STORY_ID,
    NO_MATCH_NOTICE,
    advance_local_story,
    current_local_story_choices,
)
from agens_novel.session.game_session import GameSession


def test_profile_model_failure_waits_for_explicit_local_story_choice(monkeypatch, tmp_path) -> None:
    from agens_novel import paths

    monkeypatch.setattr(paths, "SAVE_DIR", tmp_path)
    monkeypatch.setenv("AGENS_START_MODEL_OPENING", "1")
    monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
    engine = GameEngine()
    infos: list[str] = []
    narratives: list[str] = []
    engine.on_info = lambda msg: infos.append(msg)
    engine.on_narrative = lambda text, turn: narratives.append(text)

    def runner(agent_name, user_input, session, **kwargs):
        return {"generated_data": {}, "llm_error": "timeout"}

    with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=runner):
        engine.start_from_profile({"char_name": "许满"})

    assert engine.game_session.local_story_active is False
    assert engine.game_session.local_story_id == ""
    assert engine.game_session.last_choices == []
    assert engine.pending_model_failure() is not None
    assert any("请选择重试" in message for message in infos)
    assert not narratives

    assert engine.resolve_pending_model_failure("use_local_story") is True
    assert engine.game_session.local_story_active is True
    assert len(engine.game_session.last_choices) == 4


def test_local_story_choice_advances_node_and_delta(monkeypatch, tmp_path) -> None:
    from agens_novel import paths

    monkeypatch.setattr(paths, "SAVE_DIR", tmp_path)
    monkeypatch.setenv("AGENS_START_MODEL_OPENING", "1")
    monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
    engine = GameEngine()
    engine.on_model_failure_choice = lambda source, reason: "fallback"
    with patch(
        "agens_novel.engine.game_engine.run_turn_sync",
        return_value={"generated_data": {}, "llm_error": "timeout"},
    ):
        engine.start_from_profile({"char_name": "许满"})
    engine._enter_local_story("unit-test", emit_narrative=False)

    before_willpower = engine.game_session.attributes["willpower"]
    before_age = engine.game_session.age
    first_choice = engine.game_session.last_choices[0]
    engine.handle_action(first_choice)

    assert engine.game_session.local_story_node_id == "outer_gate"
    assert len(engine.game_session.last_choices) == 4
    assert any(quest.get("name") == "外门入门试炼" for quest in engine.game_session.active_quests)
    assert engine.game_session.attributes["willpower"] > before_willpower
    assert engine.game_session.age > before_age
    assert engine.game_session.turn_history[-1]["delta"]["meta"]["elapsed_years"] >= 1

    # Regression: local-story turns must also feed chat_history (narrator prompt
    # context). Before record_turn, handle_local_story_action wrote only
    # turn_history and silently skipped chat_history append+compact.
    assert any(
        msg.get("role") == "user" and msg.get("content") == first_choice
        for msg in engine.game_session.chat_history
    )
    assert any(msg.get("role") == "assistant" for msg in engine.game_session.chat_history)


def test_local_story_d_keyword_match_and_no_match_keep_choices(monkeypatch, tmp_path) -> None:
    from agens_novel import paths

    monkeypatch.setattr(paths, "SAVE_DIR", tmp_path)
    monkeypatch.setenv("AGENS_START_MODEL_OPENING", "1")
    monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
    engine = GameEngine()
    engine.on_model_failure_choice = lambda source, reason: "fallback"
    infos: list[str] = []
    engine.on_info = lambda msg: infos.append(msg)
    with patch(
        "agens_novel.engine.game_engine.run_turn_sync",
        return_value={"generated_data": {}, "llm_error": "timeout"},
    ):
        engine.start_from_profile({"char_name": "许满"})
    engine._enter_local_story("unit-test", emit_narrative=False)

    engine.handle_action(engine.game_session.last_choices[3])
    assert engine.game_session.local_story_node_id == "herb_path"
    choices_after_match = list(engine.game_session.last_choices)

    engine.handle_action("我想做一件完全无关的事")
    assert engine.game_session.last_choices == choices_after_match
    assert any(NO_MATCH_NOTICE in msg for msg in infos)


def test_local_story_matches_slot_prefixed_choice_before_keywords() -> None:
    engine = GameEngine()
    session = engine.game_session
    session.game_started = True
    engine._enter_local_story("unit-test", emit_narrative=False)

    engine.handle_action(choice_with_semantic(0, session.last_choices[0]))
    engine.handle_action(choice_with_semantic(1, session.last_choices[1]))
    selected = choice_with_semantic(2, session.last_choices[2])
    engine.handle_action(selected)

    assert session.local_story_node_id == "preparation"
    assert "反复核对药引" in session.turn_history[-1]["narrative"]


def test_local_story_matches_visible_blocked_breakthrough_action() -> None:
    session = GameSession(
        game_started=True,
        local_story_active=True,
        local_story_id=DEFAULT_STORY_ID,
        local_story_node_id="preparation",
        realm="练气",
        realm_stage=3,
    )
    engine = GameEngine()
    engine.game_session = session
    engine._enter_local_story("unit-test", emit_narrative=False)

    engine.handle_action(session.last_choices[2])

    assert session.local_story_node_id == "preparation"
    assert session.turn_history[-1]["delta"]["meta"].get("breakthrough_result") is None


def test_local_story_save_round_trip_preserves_node() -> None:
    session = GameSession()
    session.local_story_active = True
    session.local_story_id = DEFAULT_STORY_ID
    session.local_story_node_id = "outer_gate"
    session.last_choices = ["按执事吩咐完成入门杂役，熟悉宗门规矩"]
    session.game_over = True
    session.error = "寿元耗尽，坐化而去。"

    loaded = GameSession.from_save_dict(session.to_save_dict())

    assert loaded.local_story_active is True
    assert loaded.local_story_id == DEFAULT_STORY_ID
    assert loaded.local_story_node_id == "outer_gate"
    assert loaded.last_choices == session.last_choices
    assert loaded.error == "寿元耗尽，坐化而去。"


def test_loaded_local_story_can_continue_from_saved_node(monkeypatch, tmp_path) -> None:
    from agens_novel import paths

    monkeypatch.setattr(paths, "SAVE_DIR", tmp_path)
    session = GameSession()
    session.game_started = True
    session.local_story_active = True
    session.local_story_id = DEFAULT_STORY_ID
    session.local_story_node_id = "outer_gate"
    session.last_choices = ["请教师兄如何准备筑基"]

    engine = GameEngine()
    engine.game_session = GameSession.from_save_dict(session.to_save_dict())
    engine.handle_action("请教师兄如何准备筑基")

    assert engine.game_session.local_story_active is True
    assert engine.game_session.local_story_node_id == "preparation"
    assert len(engine.game_session.last_choices) == 4
    assert any(item.get("name") == "残页筑基心得" for item in engine.game_session.inventory)


def test_loaded_local_story_rebuilds_choices_when_empty() -> None:
    session = GameSession()
    session.game_started = True
    session.local_story_active = True
    session.local_story_id = DEFAULT_STORY_ID
    session.local_story_node_id = "outer_gate"
    session.last_choices = []

    engine = GameEngine()
    engine.game_session = GameSession.from_save_dict(session.to_save_dict())
    engine.handle_action("请教师兄如何准备筑基")

    assert engine.game_session.local_story_active is True
    assert engine.game_session.local_story_node_id == "preparation"
    assert len(engine.game_session.last_choices) == 4
    assert any("筑基" in choice for choice in engine.game_session.last_choices)


def test_local_story_hides_breakthrough_choices_until_realm_allows() -> None:
    session = GameSession()
    session.game_started = True
    session.local_story_active = True
    session.local_story_id = DEFAULT_STORY_ID
    session.local_story_node_id = "preparation"
    session.realm = "练气"
    session.realm_stage = 3
    session.breakthrough_flags = []

    engine = GameEngine()
    engine.game_session = GameSession.from_save_dict(session.to_save_dict())
    engine._enter_local_story("unit-test", emit_narrative=False)

    assert len(engine.game_session.last_choices) == 4
    assert not any(
        engine._parse_breakthrough_action(choice)
        for choice in engine.game_session.last_choices
    )

    before_turn_count = engine.game_session.turn_count
    engine.handle_action(engine.game_session.last_choices[0])

    assert engine.game_session.turn_count == before_turn_count + 1
    assert engine.game_session.local_story_node_id == "preparation"
    assert engine.game_session.turn_history[-1]["delta"].get("meta", {}).get(
        "breakthrough_result"
    ) is None
    assert not any(
        engine._parse_breakthrough_action(choice)
        for choice in engine.game_session.last_choices
    )


def test_local_story_keeps_authored_choices_when_another_node_has_no_breakthrough() -> None:
    session = GameSession(
        game_started=True,
        local_story_active=True,
        local_story_id=DEFAULT_STORY_ID,
        local_story_node_id="outer_gate",
        realm="练气",
        realm_stage=9,
        breakthrough_flags=["foundation_aid"],
    )
    engine = GameEngine()
    engine.game_session = GameSession.from_save_dict(session.to_save_dict())
    engine._enter_local_story("unit-test", emit_narrative=False)

    assert len(engine.game_session.last_choices) == 4
    assert not any(
        engine._parse_breakthrough_action(choice)
        for choice in engine.game_session.last_choices
    )
    engine.handle_action(engine.game_session.last_choices[2])
    assert engine.game_session.turn_count == 1


def test_local_story_repeat_tracking_survives_save_load() -> None:
    session = GameSession(
        game_started=True,
        local_story_active=True,
        local_story_id=DEFAULT_STORY_ID,
        local_story_node_id="preparation",
    )
    session.last_choices = current_local_story_choices(session)

    first = advance_local_story(session, session.last_choices[1])
    session.last_choices = first.choices
    middle = advance_local_story(session, session.last_choices[1])
    session.last_choices = middle.choices

    restored = GameSession.from_save_dict(session.to_save_dict())
    repeated = advance_local_story(restored, restored.last_choices[1])

    assert repeated.narrative != first.narrative
    assert "值甲子之时" in repeated.narrative


def test_local_story_revisits_use_distinct_authored_context() -> None:
    session = GameSession(
        game_started=True,
        local_story_active=True,
        local_story_id=DEFAULT_STORY_ID,
        local_story_node_id="preparation",
    )
    session.last_choices = current_local_story_choices(session)
    preparation_visits: list[str] = []

    for _ in range(4):
        preparation_result = advance_local_story(session, session.last_choices[1])
        preparation_visits.append(preparation_result.narrative)
        session.last_choices = preparation_result.choices
        outer_gate_result = advance_local_story(session, session.last_choices[1])
        session.last_choices = outer_gate_result.choices

    assert len(set(preparation_visits)) == len(preparation_visits)
    assert "值甲子之时" in preparation_visits[1]
    assert "值乙丑之时" in preparation_visits[2]
    assert "值丙寅之时" in preparation_visits[3]


def test_local_story_can_reach_first_major_breakthrough(monkeypatch, tmp_path) -> None:
    from agens_novel import paths

    monkeypatch.setattr(paths, "SAVE_DIR", tmp_path)
    monkeypatch.setenv("AGENS_START_MODEL_OPENING", "1")
    monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
    engine = GameEngine()
    engine.on_model_failure_choice = lambda source, reason: "fallback"
    with patch(
        "agens_novel.engine.game_engine.run_turn_sync",
        return_value={"generated_data": {}, "llm_error": "timeout"},
    ):
        engine.start_from_profile({"char_name": "许满"})
    engine._enter_local_story("unit-test", emit_narrative=False)
    engine.game_session.realm_stage = 9
    monkeypatch.setattr(
        engine.realm_system,
        "attempt_breakthrough",
        lambda _session: {
            "character": {"realm": "筑基", "realm_stage": 1, "lifespan": 200},
            "meta": {"breakthrough_result": "success", "new_realm": "筑基"},
        },
    )

    engine.handle_action(engine.game_session.last_choices[3])
    engine.handle_action("谨慎采摘灵草，炼成简易筑基药引")
    engine.handle_action("稳固心境后尝试冲击筑基")

    assert engine.game_session.realm == "筑基"
    assert engine.game_session.local_story_active is True
    assert len(engine.game_session.last_choices) == 4
    last_delta = engine.game_session.turn_history[-1]["delta"]
    assert last_delta["character"]["realm"] == "筑基"
    assert last_delta["meta"]["breakthrough_result"] == "success"


def test_local_story_failure_blocks_retry_until_steady_recovery(monkeypatch) -> None:
    engine = GameEngine()
    session = engine.game_session
    session.game_started = True
    session.local_story_active = True
    session.local_story_id = DEFAULT_STORY_ID
    session.local_story_node_id = "foundation_result"
    session.realm = "练气"
    session.realm_stage = 9
    session.breakthrough_flags = ["foundation_aid"]
    session.last_choices = current_local_story_choices(session)

    monkeypatch.setattr("agens_novel.game.realm.random.random", lambda: 1.0)
    engine.handle_action("调用正式突破判定，尝试筑基")

    assert "走火入魔" in session.status_effects
    assert "疗伤" in session.last_choices[0]
    assert not any(engine._parse_breakthrough_action(choice) for choice in session.last_choices)

    engine.handle_action("A")

    assert "走火入魔" not in session.status_effects
    assert session.turn_history[-1]["delta"]["character"]["status_effects_remove"] == ["走火入魔"]
    assert "冲击筑基" in session.last_choices[2]
