"""Failure-path coverage for GameEngine breakthrough flows."""

from __future__ import annotations

from unittest.mock import patch

from agens_novel.engine.game_engine import GameEngine


def test_breakthrough_flow_judge_exception_keeps_rule_settlement(monkeypatch) -> None:
    monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
    engine = GameEngine()
    engine.game_session.game_started = True
    engine.game_session.realm = "练气"
    engine.game_session.realm_stage = 9
    engine.game_session.breakthrough_flags = ["foundation_aid"]
    engine.game_session.last_choices = ["稳固道心", "请护法", "观察瓶颈", "随缘听天命"]
    game_overs: list[str] = []
    engine.on_game_over = lambda reason: game_overs.append(reason)

    def runner(agent_name, user_input, session, **kwargs):
        if agent_name == "narrator":
            return {
                "narrative": "你引动灵气冲击瓶颈。",
                "state_delta": {"character": {"attributes": {"willpower": 1}}},
                "choices": ["稳固道台", "拜谢护法", "查看新境界", "静候天命回响"],
                "llm_error": "",
            }
        if agent_name == "judge":
            raise RuntimeError("judge unavailable")
        return {}

    with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=runner):
        with patch("agens_novel.game.realm.random.random", return_value=0.001):
            engine.attempt_breakthrough()

    assert engine.game_session.game_over is False
    assert game_overs == []
    assert engine.game_session.realm == "筑基"


def test_breakthrough_flow_retries_incomplete_output_without_repair(monkeypatch) -> None:
    """Breakthroughs retry one strict response instead of invoking repair."""
    monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
    engine = GameEngine()
    engine.game_session.game_started = True
    engine.game_session.realm = "练气"
    engine.game_session.realm_stage = 9
    engine.game_session.breakthrough_flags = ["foundation_aid"]
    engine.game_session.last_choices = ["稳固道心", "请护法", "观察瓶颈", "随缘听天命"]
    captured: list[dict] = []

    def runner(agent_name, user_input, session, **kwargs):
        if agent_name == "narrator":
            captured.append(dict(kwargs))
            choices = (
                ["稳固道台", "拜谢护法", "查看新境界"]
                if len(captured) == 1
                else ["稳固道台", "拜谢护法", "查看新境界", "静候命数"]
            )
            return {
                "narrative": "你引动灵气冲击瓶颈。",
                "state_delta": {"character": {"attributes": {"willpower": 1}}},
                "choices": choices,
                "llm_error": "",
            }
        if agent_name == "judge":
            return {"approved": True, "corrected_delta": {}, "judgment_note": ""}
        return {}

    with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=runner):
        with patch("agens_novel.game.realm.random.random", return_value=0.001):
            engine.attempt_breakthrough()

    assert len(captured) == 2
    assert all(call.get("repair_incomplete_output") is False for call in captured)


def test_breakthrough_narrator_exception_freezes_rule_settlement(monkeypatch) -> None:
    monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
    engine = GameEngine()
    engine.game_session.game_started = True
    engine.game_session.realm = "练气"
    engine.game_session.realm_stage = 9
    engine.game_session.breakthrough_flags = ["foundation_aid"]
    engine.game_session.last_choices = ["稳固道心", "请护法", "观察瓶颈", "随缘听天命"]

    def runner(agent_name, user_input, session, **kwargs):
        if agent_name == "narrator":
            raise RuntimeError("narrator unavailable")
        if agent_name == "judge":
            return {"approved": True, "corrected_delta": {}, "judgment_note": ""}
        return {}

    with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=runner):
        with patch("agens_novel.game.realm.random.random", return_value=0.001):
            engine.attempt_breakthrough()

    assert engine.game_session.realm == "练气"
    assert engine.game_session.turn_count == 0
    pending = engine.pending_model_failure()
    assert pending is not None
    assert pending.stage == "breakthrough"
    assert pending.frozen_result["breakthrough_result"] == "success"


def test_failed_breakthrough_judge_cannot_add_realm_progress(monkeypatch) -> None:
    monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
    engine = GameEngine()
    session = engine.game_session
    session.game_started = True
    session.realm = "练气"
    session.realm_stage = 9
    session.breakthrough_flags = ["foundation_aid"]

    def runner(agent_name, user_input, current_session, **kwargs):
        if agent_name == "narrator":
            return {
                "narrative": "冲关未成，灵机反噬。",
                "state_delta": {},
                "choices": ["调息", "求助", "检查伤势", "随缘"],
                "llm_error": "",
            }
        if agent_name == "judge":
            return {
                "approved": False,
                "corrected_delta": {
                    "character": {"realm": "筑基", "realm_stage": 2, "lifespan": 999},
                    "meta": {"breakthrough_result": "failure"},
                },
                "judgment_note": "bad correction",
                "llm_error": "",
            }
        return {}

    with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=runner):
        with patch("agens_novel.game.realm.random.random", return_value=1.0):
            engine.attempt_breakthrough()

    assert session.realm == "练气"
    assert session.realm_stage == 9
    assert session.lifespan != 999
    assert session.turn_history[-1]["delta"]["meta"]["breakthrough_result"] == "failure"
