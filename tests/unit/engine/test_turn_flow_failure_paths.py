"""Failure-path coverage for ordinary GameEngine turns."""

from __future__ import annotations

from unittest.mock import patch

from agens_novel.engine.game_engine import GameEngine
from agens_novel.engine.model_fallback_policy import public_model_failure_notice


def test_turn_flow_ignores_model_delta_without_judge(monkeypatch) -> None:
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
                "choices": ["继续吐纳", "请教师兄", "观察灵气流向", "顺应天命静候"],
                "llm_error": "",
            }
        return {}

    with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=runner):
        engine.handle_action("C")

    assert decisions == []
    assert engine.game_session.game_over is False
    assert engine.game_session.turn_count == 1
    assert game_overs == []
    assert not any(item.get("name") == "越权秘宝" for item in engine.game_session.inventory)


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
                "choices": ["跟随弟子前往演武堂", "向守门弟子道谢", "留意石阶阵纹", "随缘静候钟声"],
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


def test_json_object_narrator_incomplete_output_retries_once(monkeypatch) -> None:
    monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
    engine = GameEngine()
    engine.game_session.game_started = True
    engine.game_session.last_choices = ["留在山门吐纳", "询问接引弟子", "外出历练", "随缘听天命"]
    calls = 0

    def runner(agent_name, _user_input, _session, **_kwargs):
        nonlocal calls
        assert agent_name == "narrator"
        calls += 1
        if calls == 1:
            return {
                "narrative": "English residue",
                "state_delta": {},
                "choices": [],
                "provider_transport": "json_object",
                "provider_json_object": True,
                "provider_json_envelope_ok": False,
                "contract_diagnostics": {"english_residue": True, "structured_residue": True},
                "llm_error": "",
            }
        return {
            "narrative": "山门风起，他收束杂念后重新审视眼前道路。",
            "state_delta": {},
            "choices": ["继续吐纳稳住根基", "拜访同门打听机缘", "前往山径承担风险", "顺着天命灵机而行"],
            "provider_transport": "json_object",
            "provider_json_object": True,
            "provider_json_envelope_ok": True,
            "contract_diagnostics": {"english_residue": False, "structured_residue": False},
            "llm_error": "",
        }

    with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=runner):
        engine.handle_action("A")

    assert calls == 2
    assert engine.game_session.turn_count == 1
    assert engine.game_session.local_story_active is False


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

    assert engine.game_session.turn_history == []
    assert engine.game_session.turn_count == 0
    assert engine.game_session.local_story_active is False
    assert engine.pending_model_failure() is not None
    assert "model gift" not in str(engine.game_session.inventory)


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
    assert engine.game_session.turn_count == 0
    assert len(engine.game_session.last_choices) == 4
    assert engine.pending_model_failure() is not None


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
            "模型暂不可用，请选择处理方式。",
        ),
    ]

    for reason, expected in cases:
        notice = public_model_failure_notice(reason)
        assert expected in notice
        assert "sk-" not in notice
        assert "provider.example" not in notice
        assert "https://" not in notice
