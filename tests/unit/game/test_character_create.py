"""Tests for prototype-driven character creation flow."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from agens_novel.engine.game_engine import GameEngine
from agens_novel.engine.world_generator import build_world_fallback
from agens_novel.game.constants import ATTRIBUTE_KEYS


def _complete_model_opening() -> dict:
    generated = build_world_fallback({"char_name": "许满"})
    generated.update(
        {
            "world_name": "星河试界",
            "regions": [{"name": "星河山门", "description": "群峰环绕的入道门户"}],
            "sects": [{"name": "星河剑宗", "alignment": "正道", "description": "以剑观星"}],
            "current_conflicts": ["外门名额缩减"],
            "fate_hooks": ["平稳入道"],
            "initial_situation": "许满在星河接引台前候名。",
            "initial_situation_16": "十六岁这年，许满在星河接引台前候名。",
            "chronicle_0_16": [
                "零至六岁，许满在寒门读旧经。",
                "七至十二岁，许满随乡师辨认星图。",
                "十三至十五岁，许满攒下路资前往山门。",
            ],
            "opening_narrative": "星河剑宗钟声响起。",
            "choices": ["拜见接引弟子", "观察星河灵脉", "整理行囊", "随缘等候"],
        }
    )
    generated["world"].update(
        {
            "location": "星河剑宗山门",
            "region": "星河试界",
            "current_scene": "星河接引台",
            "lore_facts": ["星河试界外门名额缩减。"],
        }
    )
    return generated


@pytest.fixture(autouse=True)
def _remove_real_model_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep profile-opening unit tests on their local or explicitly mocked path."""
    monkeypatch.delenv("AGNES_API_KEY", raising=False)


def test_start_from_profile_initializes_session(tmp_path, monkeypatch):
    from agens_novel import paths

    monkeypatch.setattr(paths, "SAVE_DIR", tmp_path)

    engine = GameEngine()
    narratives = []
    engine.on_narrative = lambda text, turn: narratives.append((text, turn))
    engine.start_from_profile(
        {
            "char_name": "许满",
            "talent": "剑心微明",
            "spirit_root": "火灵根",
            "family_background": "寒门",
            "difficulty": "普通",
            "attributes": {key: 5 for key in ATTRIBUTE_KEYS},
        }
    )

    s = engine.game_session
    assert s.game_started is True
    assert s.char_name == "许满"
    assert s.talent == "剑心微明"
    assert s.spirit_root == "火灵根"
    assert s.family_background == "寒门"
    assert not hasattr(s, "game_mode")
    assert s.last_choices == []
    assert engine.pending_model_failure() is not None
    assert s.world_profile.get("chronicle_0_16")
    assert narratives == []


def test_unknown_profile_seed_is_not_special(tmp_path, monkeypatch):
    from agens_novel import paths

    monkeypatch.setattr(paths, "SAVE_DIR", tmp_path)

    engine = GameEngine()
    engine.start_from_profile(
        {
            "unknown_seed": "removed-special-start",
            "char_name": "许满",
            "talent": "天命道胎",
            "spirit_root": "火灵根",
            "family_background": "隐世仙族",
            "attributes": {key: 5 for key in ATTRIBUTE_KEYS},
        }
    )

    s = engine.game_session
    assert s.char_name == "许满"
    assert s.attributes == {key: 5 for key in ATTRIBUTE_KEYS}
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
        generated = _complete_model_opening()
        generated["world"]["location"] = "青玄宗山门"
        generated["world"]["current_scene"] = "接引台"
        generated["choices"] = ["拜见接引弟子", "观察灵气", "整理行囊", "随缘等候"]
        return {
            "generated_data": generated,
            "llm_error": "",
            "response_mode": "json_object",
            "provider_json_envelope_ok": True,
        }

    with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=runner):
        engine.start_from_profile({"char_name": "许满"})

    assert engine.game_session.last_choices == ["拜见接引弟子", "观察灵气", "整理行囊", "随缘等候"]
    assert engine.game_session.world_profile["world_name"] == "星河试界"


def test_start_from_profile_model_failure_preserves_profile_aware_binding(tmp_path, monkeypatch):
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
        engine.start_from_profile(
            {
                "char_name": "许满",
                "difficulty": "困难",
                "attributes": {
                    "root_bone": 2,
                    "comprehension": 4,
                    "luck": 2,
                    "willpower": 8,
                    "physique": 8,
                    "soul": 6,
                },
            }
        )

    assert engine.game_session.local_story_active is False
    assert engine.game_session.last_choices == []
    assert engine.pending_model_failure() is not None
    assert engine.game_session.world_profile["world_name"] == "西陲裂土"
    assert any("请选择重试" in msg for msg in infos)


def test_start_from_profile_model_failure_can_end_run_after_player_action(tmp_path, monkeypatch):
    from agens_novel import paths

    monkeypatch.setattr(paths, "SAVE_DIR", tmp_path)
    monkeypatch.setenv("AGENS_START_MODEL_OPENING", "1")
    monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
    engine = GameEngine()
    game_overs: list[str] = []
    engine.on_game_over = lambda reason: game_overs.append(reason)

    def runner(agent_name, user_input, session, **kwargs):
        return {"generated_data": {}, "llm_error": "timeout"}

    with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=runner):
        engine.start_from_profile({"char_name": "许满"})

    assert engine.game_session.game_over is False
    assert engine.pending_model_failure() is not None
    assert engine.resolve_pending_model_failure("end_model_failure") is True
    assert engine.game_session.game_over is True
    assert game_overs == ["模型不可用导致本局结束。"]
    assert engine.game_session.last_choices == []


def test_start_from_profile_model_failure_ignores_profile_choice_override_by_default(
    tmp_path, monkeypatch
):
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
        engine.start_from_profile(
            {
                "char_name": "许满",
                "choices": ["退回山门", "询问执事"],
            }
        )

    assert engine.game_session.local_story_active is False
    assert engine.game_session.last_choices != ["退回山门", "询问执事"]
    assert engine.game_session.last_choices == []
    assert engine.pending_model_failure() is not None
    assert any("请选择重试" in msg for msg in infos)


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
            "generated_data": _complete_model_opening(),
            "llm_error": "",
            "response_mode": "json_object",
            "provider_json_envelope_ok": True,
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


def test_different_profiles_get_different_fallback_worlds(tmp_path, monkeypatch):
    from agens_novel import paths

    monkeypatch.setattr(paths, "SAVE_DIR", tmp_path)
    monkeypatch.delenv("AGENS_START_MODEL_OPENING", raising=False)
    monkeypatch.delenv("AGENS_START_MODEL_WORLD", raising=False)

    high_luck = GameEngine()
    high_luck.start_from_profile(
        {
            "char_name": "许满",
            "family_background": "寒门",
            "randomize_attributes": True,
            "attributes": {
                "root_bone": 3,
                "comprehension": 5,
                "luck": 9,
                "willpower": 5,
                "physique": 4,
                "soul": 4,
            },
        }
    )
    hard = GameEngine()
    hard.start_from_profile(
        {
            "char_name": "许满",
            "difficulty": "困难",
            "randomize_attributes": True,
            "attributes": {
                "root_bone": 2,
                "comprehension": 4,
                "luck": 2,
                "willpower": 8,
                "physique": 8,
                "soul": 6,
            },
        }
    )

    assert high_luck.game_session.world_profile["world_name"] == "沧澜群岛"
    assert hard.game_session.world_profile["world_name"] == "西陲裂土"
    assert high_luck.game_session.current_scene != hard.game_session.current_scene
