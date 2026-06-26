"""Tests for prototype-driven character creation flow."""

from __future__ import annotations

from unittest.mock import patch

from agens_novel.engine.game_engine import GameEngine
from agens_novel.game.constants import ATTRIBUTE_KEYS


def test_start_from_profile_initializes_session(tmp_path, monkeypatch):
    from agens_novel import paths
    monkeypatch.setattr(paths, "SAVE_DIR", tmp_path)

    engine = GameEngine()
    narratives = []
    engine.on_narrative = lambda text, turn: narratives.append((text, turn))
    engine.start_from_profile({
        "char_name": "许满",
        "talent": "剑心微明",
        "spirit_root": "火灵根",
        "family_background": "寒门",
        "difficulty": "普通",
        "attributes": {key: 60 for key in ATTRIBUTE_KEYS},
    })

    s = engine.game_session
    assert s.game_started is True
    assert s.char_name == "许满"
    assert s.talent == "剑心微明"
    assert s.spirit_root == "火灵根"
    assert s.family_background == "寒门"
    assert not hasattr(s, "game_mode")
    assert len(s.last_choices) == 4
    assert s.last_choices[-1] == "【气运】随缘而行，听天命、赌因果"
    assert narratives and narratives[0][1] == 0


def test_unknown_profile_seed_is_not_special(tmp_path, monkeypatch):
    from agens_novel import paths
    monkeypatch.setattr(paths, "SAVE_DIR", tmp_path)

    engine = GameEngine()
    engine.start_from_profile({
        "unknown_seed": "removed-special-start",
        "char_name": "许满",
        "talent": "天命道胎",
        "spirit_root": "火灵根",
        "family_background": "隐世仙族",
        "attributes": {key: 50 for key in ATTRIBUTE_KEYS},
    })

    s = engine.game_session
    assert s.char_name == "许满"
    assert s.attributes == {key: 50 for key in ATTRIBUTE_KEYS}
    assert s.family_background == "隐世仙族"
    assert s.talent == "天命道胎"
    assert s.spirit_root == "火灵根"
    assert not hasattr(s, "gold")


def test_start_from_profile_generates_opening_choices_from_model(tmp_path, monkeypatch):
    from agens_novel import paths
    monkeypatch.setattr(paths, "SAVE_DIR", tmp_path)
    monkeypatch.setenv("AGENS_START_MODEL_OPENING", "1")
    monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")

    engine = GameEngine()

    def runner(agent_name, user_input, session, **kwargs):
        assert agent_name == "world_builder"
        return {
            "generated_data": {
                "world": {"location": "青玄宗山门", "current_scene": "接引台"},
                "opening_narrative": "接引钟声响起。",
                "choices": ["拜见接引弟子", "观察灵气", "整理行囊"],
            },
            "llm_error": "",
        }

    with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=runner):
        engine.start_from_profile({"char_name": "许满"})

    assert engine.game_session.last_choices == ["拜见接引弟子", "观察灵气", "整理行囊", "【气运】随缘而行，听天命、赌因果"]


def test_start_from_profile_model_failure_uses_tiandao_fallback(tmp_path, monkeypatch):
    from agens_novel import paths
    monkeypatch.setattr(paths, "SAVE_DIR", tmp_path)
    monkeypatch.setenv("AGENS_START_MODEL_OPENING", "1")
    monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
    engine = GameEngine()
    infos: list[str] = []
    engine.on_info = lambda msg: infos.append(msg)

    def runner(agent_name, user_input, session, **kwargs):
        return {"generated_data": {}, "llm_error": "timeout"}

    with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=runner):
        engine.start_from_profile({"char_name": "许满"})

    assert engine.game_session.local_story_active is True
    assert len(engine.game_session.last_choices) == 4
    assert any("天道紊乱" in msg for msg in infos)


def test_start_from_profile_model_failure_can_end_run(tmp_path, monkeypatch):
    from agens_novel import paths
    monkeypatch.setattr(paths, "SAVE_DIR", tmp_path)
    monkeypatch.setenv("AGENS_START_MODEL_OPENING", "1")
    monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
    engine = GameEngine()
    game_overs: list[str] = []
    engine.on_model_failure_choice = lambda source, reason: "end"
    engine.on_game_over = lambda reason: game_overs.append(reason)

    def runner(agent_name, user_input, session, **kwargs):
        return {"generated_data": {}, "llm_error": "timeout"}

    with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=runner):
        engine.start_from_profile({"char_name": "许满"})

    assert engine.game_session.game_over is True
    assert game_overs == ["模型不可用导致本局结束。"]
    assert engine.game_session.last_choices == []


def test_start_from_profile_model_failure_enters_local_story_not_profile_choices(tmp_path, monkeypatch):
    from agens_novel import paths
    monkeypatch.setattr(paths, "SAVE_DIR", tmp_path)
    monkeypatch.setenv("AGENS_START_MODEL_OPENING", "1")
    monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
    engine = GameEngine()
    infos: list[str] = []
    engine.on_info = lambda msg: infos.append(msg)

    def runner(agent_name, user_input, session, **kwargs):
        assert agent_name == "world_builder"
        return {"generated_data": {}, "llm_error": "timeout"}

    with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=runner):
        engine.start_from_profile({
            "char_name": "许满",
            "choices": ["退回山门", "询问执事"],
        })

    assert engine.game_session.local_story_active is True
    assert engine.game_session.last_choices != ["退回山门", "询问执事"]
    assert len(engine.game_session.last_choices) == 4
    assert any("天道紊乱" in msg for msg in infos)


def test_unknown_profile_seed_is_not_sent_to_world_builder_prompt(tmp_path, monkeypatch):
    from agens_novel import paths
    monkeypatch.setattr(paths, "SAVE_DIR", tmp_path)
    monkeypatch.setenv("AGENS_START_MODEL_OPENING", "1")
    monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
    engine = GameEngine()
    seen_inputs: list[str] = []

    def runner(agent_name, user_input, session, **kwargs):
        assert agent_name == "world_builder"
        seen_inputs.append(user_input)
        return {
            "generated_data": {
                "world": {"location": "星河剑宗山门", "current_scene": "星河接引台"},
                "opening_narrative": "星河剑宗钟声响起。",
                "choices": ["拜见接引弟子", "观察星河灵脉", "整理行囊"],
            },
            "llm_error": "",
        }

    with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=runner):
        engine.start_from_profile({"unknown_seed": "星河剑宗", "char_name": "许满"})

    assert seen_inputs and "星河剑宗" not in seen_inputs[0]
    assert engine.game_session.location == "星河剑宗山门"


def test_unknown_profile_seed_does_not_change_local_fallback_opening(tmp_path, monkeypatch):
    from agens_novel import paths
    monkeypatch.setattr(paths, "SAVE_DIR", tmp_path)
    monkeypatch.delenv("AGNES_API_KEY", raising=False)

    first = GameEngine()
    first.start_from_profile({"unknown_seed": "云海纪", "char_name": "许满"})
    second = GameEngine()
    second.start_from_profile({"unknown_seed": "赤霄录", "char_name": "许满"})

    assert first.game_session.location == second.game_session.location
    assert "云海纪" not in first.game_session.location
    assert "赤霄录" not in second.game_session.location
