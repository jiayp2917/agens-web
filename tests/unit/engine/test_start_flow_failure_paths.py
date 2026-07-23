"""Failure-path coverage for GameEngine opening flows."""

from __future__ import annotations

from unittest.mock import patch

from agens_novel.engine.game_engine import GameEngine
from agens_novel.engine.start_flow import _classify_opening_result
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
    bad["opening_narrative"] = "English opening"
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


def test_profile_opening_uses_minimal_envelope_without_world_parser() -> None:
    result = {
        "generated_data": {
            "chronicle_0_16": ["幼年听潮识字。", "少时在渡口学艺。", "十六岁抵达潮音渡。"],
            "initial_situation_16": "十六岁的潮音渡试炼即将开始。",
            "opening_narrative": "潮声渐紧，许满在渡口看见旧日因果浮现。",
            "choices": [
                "在潮音渡核对试炼名册",
                "拜访舟客打听灵潮消息",
                "夜探暗礁承担未知风险",
                "循着天命潮声随缘而行",
            ],
        },
        "provider_transport": "json_schema",
        "provider_json_envelope_ok": True,
        "llm_error": "",
    }

    status, payload = _classify_opening_result(result, profile_opening=True)

    assert status.kind.value == "ok"
    assert payload["initial_situation_16"].startswith("十六岁")
    assert len(payload["choices"]) == 4


def test_profile_opening_rejects_structured_transport_without_envelope() -> None:
    status, payload = _classify_opening_result(
        {
            "generated_data": {"opening_narrative": "不应接受的开场"},
            "provider_transport": "json_schema",
            "provider_json_envelope_ok": False,
            "llm_error": "",
        },
        profile_opening=True,
    )

    assert status.kind.value == "incomplete_output"
    assert payload == {}


def test_profile_opening_keeps_authoritative_fallback_world_bindings(monkeypatch) -> None:
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
    fallback = build_world_fallback(profile)
    generated = {
        "chronicle_0_16": ["幼年听潮。", "少时识得灵机。", "十六岁抵达渡口。"],
        "initial_situation_16": "十六岁的渡口试炼即将开始。",
        "opening_narrative": "潮声渐紧，许满在十六岁来到渡口，旧日因果也随之浮现。",
        "choices": ["留在渡口核对试炼名册", "拜访舟客打听旧事", "夜探暗礁承担风险", "循着天命潮声而行"],
        "world": {"region": "模型不可改写的世界"},
        "world_key": "模型不可改写的世界键",
        "story_key": "模型不可改写的剧情键",
        "story_version": 99,
        "character": {"name": "模型不可改写的角色"},
    }

    with patch.object(engine, "run_agent", return_value={"generated_data": generated, "llm_error": ""}):
        engine.start_from_profile(profile)

    assert engine.game_session.char_name == profile["char_name"]
    assert engine.game_session.region == generated["world"]["region"]
    assert engine.game_session.world_profile["world_key"] == fallback["world_key"]
    assert engine.game_session.story_key == fallback["story_key"]
    assert engine.game_session.story_version == fallback["story_version"]
    assert engine.game_session.last_choices == generated["choices"]


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


def test_profile_opening_canary_limit_suppresses_the_retry(monkeypatch) -> None:
    monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
    monkeypatch.setenv("AGENS_START_MODEL_WORLD", "1")
    monkeypatch.setenv("AGENS_EVALUATION_OPENING_MAX_ATTEMPTS", "1")
    engine = GameEngine()
    calls: list[str] = []

    def runner(_agent_name, _user_input, _session, **_kwargs):
        calls.append("world_builder")
        return {"generated_data": {}, "llm_error": ""}

    with patch.object(engine, "run_agent", side_effect=runner):
        engine.start_from_profile({"char_name": "canary"})

    assert calls == ["world_builder"]
