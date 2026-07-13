"""Focused failure-path coverage for split GameEngine flows."""

from __future__ import annotations

from unittest.mock import patch

from agens_novel.engine.game_engine import GameEngine
from agens_novel.engine.model_fallback_policy import public_model_failure_notice
from agens_novel.engine.world_generator import build_world_fallback


def test_start_flow_world_builder_exception_can_end_run(monkeypatch) -> None:
    monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
    engine = GameEngine()
    decisions: list[tuple[str, str]] = []
    game_overs: list[str] = []
    engine.on_model_failure_choice = lambda source, reason: (
        decisions.append((source, reason)) or "end"
    )
    engine.on_game_over = lambda reason: game_overs.append(reason)

    with patch(
        "agens_novel.engine.game_engine.run_turn_sync", side_effect=RuntimeError("network down")
    ):
        engine.new_game("许满")

    assert decisions and decisions[0][0] == "world_builder_exception"
    assert engine.game_session.game_over is True
    assert game_overs == ["模型不可用导致本局结束。"]


def test_profile_opening_retry_adds_visible_text_contract(monkeypatch) -> None:
    monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
    monkeypatch.setenv("AGENS_START_MODEL_WORLD", "1")
    engine = GameEngine()
    profile = {
        "char_name": "许满",
        "talent": "平平无奇",
        "spirit_root": "木灵根",
        "family_background": "寒门",
        "difficulty": "普通",
        "attributes": {
            "root_bone": 5,
            "comprehension": 5,
            "luck": 5,
            "willpower": 5,
            "physique": 5,
            "soul": 5,
        },
    }
    bad = build_world_fallback(profile)
    bad["world"] = {**bad["world"], "location": "English Place"}
    good = build_world_fallback(profile)
    captured: list[str] = []

    def runner(_agent_name, user_input, _session, **_kwargs):
        captured.append(user_input)
        return {"generated_data": bad if len(captured) == 1 else good, "llm_error": ""}

    with patch.object(engine, "run_agent", side_effect=runner):
        engine.start_from_profile(profile)

    assert len(captured) == 2
    assert "所有可见字符串必须是中文" in captured[1]
    assert engine.game_session.local_story_active is False


def test_profile_opening_empty_result_uses_strict_retry(monkeypatch) -> None:
    monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
    monkeypatch.setenv("AGENS_START_MODEL_WORLD", "1")
    engine = GameEngine()
    profile = {
        "char_name": "许满",
        "talent": "平平无奇",
        "spirit_root": "木灵根",
        "family_background": "寒门",
        "difficulty": "普通",
    }
    good = build_world_fallback(profile)
    calls: list[tuple[str, str]] = []

    def runner(_agent_name, user_input, _session, **kwargs):
        calls.append((user_input, str(kwargs.get("generation_type") or "")))
        if len(calls) == 1:
            return {"generated_data": {}, "llm_error": ""}
        return {"generated_data": good, "llm_error": ""}

    with patch.object(engine, "run_agent", side_effect=runner):
        engine.start_from_profile(profile)

    assert len(calls) == 2
    assert "严格重试要求" in calls[1][0]
    assert calls[1][1] == "profile_opening"
    assert engine.game_session.region == good["world"]["region"]


def test_turn_flow_judge_llm_error_rejects_delta_without_player_fallback(monkeypatch) -> None:
    monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
    engine = GameEngine()
    engine.game_session.game_started = True
    engine.game_session.last_choices = ["留在山门吐纳", "询问接引弟子", "强闯禁地", "随缘听天命"]
    decisions: list[tuple[str, str]] = []
    game_overs: list[str] = []
    engine.on_model_failure_choice = lambda source, reason: (
        decisions.append((source, reason)) or "end"
    )
    engine.on_game_over = lambda reason: game_overs.append(reason)

    def runner(agent_name, user_input, session, **kwargs):
        if agent_name == "narrator":
            return {
                "narrative": "你得了一件不该存在的秘宝。",
                "state_delta": {
                    "character": {"inventory_add": [{"name": "越权秘宝", "rarity": "橙"}]}
                },
                "choices": ["继续吐纳", "请教师兄", "观察灵气流向"],
                "llm_error": "",
            }
        if agent_name == "judge":
            return {"approved": False, "corrected_delta": {}, "llm_error": "HTTP 500"}
        return {}

    with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=runner):
        engine.handle_action("C")

    assert decisions == []
    assert engine.game_session.game_over is False
    assert engine.game_session.turn_count == 1
    assert game_overs == []
    assert not any(item.get("name") == "越权秘宝" for item in engine.game_session.inventory)


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
    engine.on_model_failure_choice = lambda source, reason: (
        decisions.append((source, reason)) or "end"
    )
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


def test_turn_flow_disables_narrator_repair_for_ordinary_turns(monkeypatch) -> None:
    """Ordinary turns avoid a second model call and use rule-delta fallback."""
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

    assert captured.get("repair_incomplete_output") is False


def test_turn_flow_uses_rule_delta_when_state_update_missing(monkeypatch) -> None:
    monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
    engine = GameEngine()
    engine.game_session.game_started = True
    engine.game_session.last_choices = ["留在山门吐纳", "询问接引弟子", "外出历练", "随缘听天命"]
    engine.game_session.age = 16

    def runner(agent_name, user_input, session, **kwargs):
        if agent_name == "narrator":
            return {
                "narrative": "三年山中岁月过去，他的吐纳越发沉稳。",
                "state_delta": None,
                "choices": ["继续稳固根基", "请教师兄", "外出历练", "随缘而行"],
                "llm_error": "",
            }
        return {}

    with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=runner):
        engine.handle_action("A")

    assert engine.game_session.turn_count == 1
    assert engine.game_session.age > 16
    assert engine.game_session.turn_history[-1]["delta"]["meta"]["elapsed_years"] >= 1
    assert engine.game_session.turn_history[-1]["narrative"]


def test_visible_english_contract_violation_is_not_shown_to_player(monkeypatch) -> None:
    monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
    engine = GameEngine()
    engine.game_session.game_started = True
    engine.game_session.last_choices = ["留在山门吐纳", "询问接引弟子", "外出历练", "随缘听天命"]

    def runner(agent_name, user_input, session, **kwargs):
        if agent_name == "narrator":
            return {
                "narrative": "He gains prowess at the gate.",
                "state_delta": {"character": {"inventory_add": [{"name": "model gift"}]}},
                "choices": ["Rest", "Explore", "Fight", "Trust luck"],
                "contract_diagnostics": {"english_residue": True},
                "llm_error": "",
            }
        return {}

    with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=runner):
        engine.handle_action("A")

    turn = engine.game_session.turn_history[-1]
    assert "prowess" not in turn["narrative"]
    assert "model gift" not in str(engine.game_session.inventory)
    assert engine.game_session.local_story_active is True


def test_json_only_terminal_delta_is_rejected_before_choices_are_cleared(monkeypatch) -> None:
    monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
    engine = GameEngine()
    engine.game_session.game_started = True
    engine.game_session.last_choices = ["A", "B", "C", "D"]
    engine.game_session.age = 16

    def runner(agent_name, user_input, session, **kwargs):
        if agent_name == "narrator":
            return {
                "narrative": "",
                "state_delta": {
                    "meta": {"game_over": True, "game_over_reason": "model-only terminal"}
                },
                "choices": [],
                "llm_error": "",
            }
        return {}

    with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=runner):
        engine.handle_action("A")

    assert engine.game_session.game_over is False
    assert engine.game_session.turn_count == 1
    assert len(engine.game_session.last_choices) == 4
    assert engine.game_session.turn_history[-1]["delta"]["meta"]["elapsed_years"] >= 1


def test_http_404_model_failure_notice_is_actionable_and_secret_safe() -> None:
    notice = public_model_failure_notice(
        '叙述失败: HTTP 404: {"error":{"message":"Not Found","code":"404"}}'
    )

    assert "叙事服务配置" in notice
    assert "系统默认" in notice
    assert "sk-" not in notice
    assert "http://" not in notice
    assert "https://" not in notice


def test_model_failure_notice_matrix_is_actionable_and_secret_safe() -> None:
    cases = [
        ("叙述失败: HTTP 401 Unauthorized", "鉴权未通过"),
        ("叙述失败: request timed out after 60s", "响应过久"),
        ("AGNES_API_KEY unavailable", "密钥未配置"),
        (
            "模型已返回叙事，但状态更新格式不完整: https://provider.example/v1 x-api-key sk-secret",
            "本回合记录暂未续上",
        ),
    ]

    for reason, expected in cases:
        notice = public_model_failure_notice(reason)
        assert expected in notice
        assert "sk-" not in notice
        assert "provider.example" not in notice
        assert "https://" not in notice


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


def test_breakthrough_narrator_exception_keeps_rule_settlement(monkeypatch) -> None:
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

    assert engine.game_session.realm == "筑基"
    assert engine.game_session.turn_count == 1
    assert len(engine.game_session.last_choices) == 4
    assert engine.game_session.turn_history[-1]["delta"]["meta"]["breakthrough_result"] == "success"


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
