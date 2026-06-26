"""Focused failure-path coverage for split GameEngine flows."""

from __future__ import annotations

from unittest.mock import patch

from agens_novel.engine.game_engine import GameEngine


def test_start_flow_world_builder_exception_can_end_run(monkeypatch) -> None:
    monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
    engine = GameEngine()
    decisions: list[tuple[str, str]] = []
    game_overs: list[str] = []
    engine.on_model_failure_choice = lambda source, reason: decisions.append((source, reason)) or "end"
    engine.on_game_over = lambda reason: game_overs.append(reason)

    with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=RuntimeError("network down")):
        engine.new_game("许满")

    assert decisions and decisions[0][0] == "world_builder_exception"
    assert engine.game_session.game_over is True
    assert game_overs == ["模型不可用导致本局结束。"]


def test_turn_flow_judge_llm_error_can_end_run(monkeypatch) -> None:
    monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
    engine = GameEngine()
    engine.game_session.game_started = True
    engine.game_session.last_choices = ["留在山门吐纳", "询问接引弟子", "强闯禁地", "随缘听天命"]
    decisions: list[tuple[str, str]] = []
    game_overs: list[str] = []
    engine.on_model_failure_choice = lambda source, reason: decisions.append((source, reason)) or "end"
    engine.on_game_over = lambda reason: game_overs.append(reason)

    def runner(agent_name, user_input, session, **kwargs):
        if agent_name == "narrator":
            return {
                "narrative": "你得了一笔不该存在的秘宝。",
                "state_delta": {"character": {"gold": "+77"}},
                "choices": ["继续吐纳", "请教师兄", "观察灵气流向"],
                "llm_error": "",
            }
        if agent_name == "judge":
            return {"approved": False, "corrected_delta": {}, "llm_error": "HTTP 500"}
        return {}

    with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=runner):
        engine.handle_action("C")

    assert decisions and decisions[0][0] == "judge_error"
    assert "天道审判失败" in decisions[0][1]
    assert engine.game_session.game_over is True
    assert engine.game_session.turn_count == 0
    assert game_overs == ["模型不可用导致本局结束。"]


def test_breakthrough_flow_judge_exception_can_end_run(monkeypatch) -> None:
    monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
    engine = GameEngine()
    engine.game_session.game_started = True
    engine.game_session.realm = "练气"
    engine.game_session.realm_stage = 9
    engine.game_session.breakthrough_flags = ["foundation_aid"]
    engine.game_session.last_choices = ["稳固道心", "请护法", "观察瓶颈", "随缘听天命"]
    decisions: list[tuple[str, str]] = []
    game_overs: list[str] = []
    engine.on_model_failure_choice = lambda source, reason: decisions.append((source, reason)) or "end"
    engine.on_game_over = lambda reason: game_overs.append(reason)

    def runner(agent_name, user_input, session, **kwargs):
        if agent_name == "narrator":
            return {
                "narrative": "你引动灵气冲击瓶颈。",
                "state_delta": {"character": {"attributes": {"willpower": 1}}},
                "choices": ["稳固道台", "拜谢护法", "查看新境界"],
                "llm_error": "",
            }
        if agent_name == "judge":
            raise RuntimeError("judge unavailable")
        return {}

    with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=runner):
        with patch("agens_novel.game.realm.random.random", return_value=0.001):
            engine.attempt_breakthrough()

    assert decisions and decisions[0][0] == "breakthrough_judge_exception"
    assert engine.game_session.game_over is True
    assert game_overs == ["模型不可用导致本局结束。"]


def test_turn_flow_enables_narrator_repair(monkeypatch) -> None:
    """Ordinary turns ask the narrator to repair incomplete structured output.

    The model frequently emits narrative without <state_update>/<choices> tags,
    which would otherwise force a local-story fallback. The narrator's repair
    pass recovers the tags on a second focused call (repaired_output is recorded
    in diagnostics). Regression guard: the turn path must keep repair enabled.
    """
    monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
    engine = GameEngine()
    engine.game_session.game_started = True
    engine.game_session.last_choices = ["留在山门吐纳", "询问接引弟子", "强闯禁地", "随缘听天命"]
    captured: dict = {}

    def runner(agent_name, user_input, session, **kwargs):
        if agent_name == "narrator":
            captured.update(kwargs)
            return {
                "narrative": "晨钟响起，你随弟子前往演武堂。",
                "state_delta": {"character": {}, "world": {}, "meta": {}},
                "choices": ["跟随弟子前往演武堂", "向守门弟子道谢", "留意石阶阵纹"],
                "llm_error": "",
            }
        return {}

    with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=runner):
        engine.handle_action("A")

    assert captured.get("repair_incomplete_output") is True


def test_breakthrough_flow_enables_narrator_repair(monkeypatch) -> None:
    """Breakthrough narrator calls must also enable repair for the same reasons.

    The breakthrough path calls the same narrator agent and faces the same
    risk of missing <state_update>/<choices> tags. Regression guard: the
    breakthrough path must keep repair enabled.
    """
    monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
    engine = GameEngine()
    engine.game_session.game_started = True
    engine.game_session.realm = "练气"
    engine.game_session.realm_stage = 9
    engine.game_session.breakthrough_flags = ["foundation_aid"]
    engine.game_session.last_choices = ["稳固道心", "请护法", "观察瓶颈", "随缘听天命"]
    captured: dict = {}

    def runner(agent_name, user_input, session, **kwargs):
        if agent_name == "narrator":
            captured.update(kwargs)
            return {
                "narrative": "你引动灵气冲击瓶颈。",
                "state_delta": {"character": {"attributes": {"willpower": 1}}},
                "choices": ["稳固道台", "拜谢护法", "查看新境界"],
                "llm_error": "",
            }
        if agent_name == "judge":
            return {"approved": True, "corrected_delta": {}, "judgment_note": ""}
        return {}

    with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=runner):
        with patch("agens_novel.game.realm.random.random", return_value=0.001):
            engine.attempt_breakthrough()

    assert captured.get("repair_incomplete_output") is True
