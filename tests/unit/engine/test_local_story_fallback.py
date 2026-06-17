"""Tests for local preset story fallback."""

from __future__ import annotations

from unittest.mock import patch

from agens_novel.engine.game_engine import GameEngine
from agens_novel.engine.local_story import DEFAULT_STORY_ID, NO_MATCH_NOTICE, validate_local_story_graph
from agens_novel.session.game_session import GameSession


def test_profile_model_failure_enters_local_story(monkeypatch, tmp_path) -> None:
    from agens_novel import paths

    monkeypatch.setattr(paths, "SAVE_DIR", tmp_path)
    engine = GameEngine()
    engine.on_model_failure_choice = lambda source, reason: "fallback"
    infos: list[str] = []
    narratives: list[str] = []
    engine.on_info = lambda msg: infos.append(msg)
    engine.on_narrative = lambda text, turn: narratives.append(text)

    def runner(agent_name, user_input, session, **kwargs):
        return {"generated_data": {}, "llm_error": "timeout"}

    with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=runner):
        engine.start_from_profile({"char_name": "许满"})

    assert engine.game_session.local_story_active is True
    assert engine.game_session.local_story_id == DEFAULT_STORY_ID
    assert len(engine.game_session.last_choices) == 3
    assert any("天道紊乱" in msg for msg in infos)
    assert narratives and "因果残影" in narratives[0]


def test_local_story_choice_advances_node_and_delta(monkeypatch, tmp_path) -> None:
    from agens_novel import paths

    monkeypatch.setattr(paths, "SAVE_DIR", tmp_path)
    engine = GameEngine()
    engine.on_model_failure_choice = lambda source, reason: "fallback"
    with patch(
        "agens_novel.engine.game_engine.run_turn_sync",
        return_value={"generated_data": {}, "llm_error": "timeout"},
    ):
        engine.start_from_profile({"char_name": "许满"})

    first_choice = engine.game_session.last_choices[0]
    engine.handle_action(first_choice)

    assert engine.game_session.local_story_node_id == "outer_gate"
    assert engine.game_session.insight >= 6
    assert len(engine.game_session.last_choices) == 3
    assert any(quest.get("name") == "外门入门试炼" for quest in engine.game_session.active_quests)


def test_local_story_graph_has_no_dead_nodes() -> None:
    assert validate_local_story_graph(DEFAULT_STORY_ID) == []


def test_local_story_d_keyword_match_and_no_match_keep_choices(monkeypatch, tmp_path) -> None:
    from agens_novel import paths

    monkeypatch.setattr(paths, "SAVE_DIR", tmp_path)
    engine = GameEngine()
    engine.on_model_failure_choice = lambda source, reason: "fallback"
    infos: list[str] = []
    engine.on_info = lambda msg: infos.append(msg)
    with patch(
        "agens_novel.engine.game_engine.run_turn_sync",
        return_value={"generated_data": {}, "llm_error": "timeout"},
    ):
        engine.start_from_profile({"char_name": "许满"})

    engine.handle_action("D: 我沿着灵雾观察药径")
    assert engine.game_session.local_story_node_id == "herb_path"
    choices_after_match = list(engine.game_session.last_choices)

    engine.handle_action("D: 我想做一件完全无关的事")
    assert engine.game_session.last_choices == choices_after_match
    assert any(NO_MATCH_NOTICE in msg for msg in infos)


def test_local_story_save_round_trip_preserves_node() -> None:
    session = GameSession()
    session.local_story_active = True
    session.local_story_id = DEFAULT_STORY_ID
    session.local_story_node_id = "outer_gate"
    session.last_choices = ["按执事吩咐完成入门杂役，熟悉宗门规矩"]

    loaded = GameSession.from_save_dict(session.to_save_dict())

    assert loaded.local_story_active is True
    assert loaded.local_story_id == DEFAULT_STORY_ID
    assert loaded.local_story_node_id == "outer_gate"
    assert loaded.last_choices == session.last_choices


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
    engine.handle_action("D: 我请教师兄筑基心得")

    assert engine.game_session.local_story_active is True
    assert engine.game_session.local_story_node_id == "preparation"
    assert len(engine.game_session.last_choices) == 3
    assert any(item.get("name") == "残页筑基心得" for item in engine.game_session.inventory)


def test_engine_load_rebuilds_local_story_choices(monkeypatch, tmp_path) -> None:
    from agens_novel import paths

    monkeypatch.setattr(paths, "SAVE_DIR", tmp_path)
    engine = GameEngine()
    engine.game_session.game_started = True
    engine.game_session.local_story_active = True
    engine.game_session.local_story_id = DEFAULT_STORY_ID
    engine.game_session.local_story_node_id = "outer_gate"
    engine.game_session.last_choices = []
    engine.save("local_story_slot")

    loaded = GameEngine()
    loaded.load("local_story_slot")

    assert loaded.game_session.local_story_active is True
    assert loaded.game_session.local_story_node_id == "outer_gate"
    assert len(loaded.game_session.last_choices) == 3
    assert any("筑基" in choice for choice in loaded.game_session.last_choices)


def test_local_story_can_reach_first_major_breakthrough(monkeypatch, tmp_path) -> None:
    from agens_novel import paths

    monkeypatch.setattr(paths, "SAVE_DIR", tmp_path)
    monkeypatch.setattr("agens_novel.game.realm.random.random", lambda: 0.0)
    engine = GameEngine()
    engine.on_model_failure_choice = lambda source, reason: "fallback"
    with patch(
        "agens_novel.engine.game_engine.run_turn_sync",
        return_value={"generated_data": {}, "llm_error": "timeout"},
    ):
        engine.start_from_profile({"char_name": "许满"})

    engine.handle_action("D: 我沿着灵雾观察药径")
    engine.handle_action("谨慎采摘灵草，炼成简易筑基药引")
    engine.handle_action("稳固心境后尝试冲击筑基")

    assert engine.game_session.realm == "筑基"
    assert engine.game_session.local_story_active is True
    assert len(engine.game_session.last_choices) == 3
