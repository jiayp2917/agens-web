"""Failure-path coverage for GameEngine opening flows."""

from __future__ import annotations

from unittest.mock import patch

from agens_novel.engine.game_engine import GameEngine
from agens_novel.engine.start_flow import _classify_opening_result
from agens_novel.engine.world_generator import build_world_fallback


def _strict_profile_opening(generated: dict[str, object]) -> dict[str, object]:
    return {
        "generated_data": generated,
        "response_mode": "json_object",
        "provider_json_envelope_ok": True,
        "llm_error": "",
    }


def test_start_flow_world_builder_exception_waits_for_player_decision(monkeypatch) -> None:
    monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
    engine = GameEngine()
    game_overs: list[str] = []
    engine.on_game_over = lambda reason: game_overs.append(reason)

    with patch(
        "agens_novel.engine.game_engine.run_turn_sync", side_effect=RuntimeError("network down")
    ):
        engine.new_game("许满")

    pending = engine.pending_model_failure()
    assert pending is not None
    assert pending.stage == "opening"
    assert engine.game_session.game_over is False
    assert game_overs == []

    assert engine.resolve_pending_model_failure("end_model_failure") is True
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
        return _strict_profile_opening(bad if len(captured) == 1 else good)

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


def test_profile_opening_rejects_missing_transport_and_envelope_marker() -> None:
    status, payload = _classify_opening_result(
        {
            "generated_data": {
                "opening_narrative": "潮声渐紧，许满在渡口等候试炼。",
                "chronicle_0_16": ["幼时识字。", "少年练剑。", "十六岁抵达渡口。"],
                "initial_situation_16": "渡口试炼即将开始。",
                "choices": ["整理名册", "拜访船客", "夜探暗礁", "循着潮声前行"],
            },
            "llm_error": "",
        },
        profile_opening=True,
    )

    assert status.kind.value == "incomplete_output"
    assert payload == {}


def test_profile_opening_uses_model_without_legacy_environment_switch(monkeypatch) -> None:
    monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
    monkeypatch.delenv("AGENS_START_MODEL_WORLD", raising=False)
    monkeypatch.delenv("AGENS_START_MODEL_OPENING", raising=False)
    engine = GameEngine()
    calls: list[str] = []

    def runner(agent_name, _user_input, _session, **_kwargs):
        calls.append(agent_name)
        return {"generated_data": {}, "llm_error": ""}

    with patch.object(engine, "run_agent", side_effect=runner):
        engine.start_from_profile({"char_name": "许满"})

    assert calls == ["world_builder", "world_builder"]
    assert engine.pending_model_failure() is not None


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

    with patch.object(engine, "run_agent", return_value=_strict_profile_opening(generated)):
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
        return _strict_profile_opening(good)

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


def test_profile_opening_failure_freezes_binding_until_player_resolves(monkeypatch) -> None:
    monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
    monkeypatch.setenv("AGENS_START_MODEL_WORLD", "1")
    engine = GameEngine()
    profile = {"char_name": "许满"}

    with patch.object(engine, "run_agent", return_value={"generated_data": {}, "llm_error": ""}):
        engine.start_from_profile(profile)

    pending = engine.pending_model_failure()
    assert pending is not None
    assert pending.stage == "opening"
    assert engine.game_session.game_started is True
    assert engine.game_session.story_key
    assert engine.game_session.turn_count == 0
    assert engine.game_session.local_story_active is False
    assert engine.game_session.last_choices == []


def test_profile_opening_retry_uses_frozen_binding_and_settles_once(monkeypatch) -> None:
    monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
    monkeypatch.setenv("AGENS_START_MODEL_WORLD", "1")
    engine = GameEngine()
    profile = {"char_name": "许满"}
    good = build_world_fallback(profile)
    calls = 0

    def runner(_agent_name, _user_input, _session, **_kwargs):
        nonlocal calls
        calls += 1
        if calls == 3:
            return _strict_profile_opening(good)
        return {"generated_data": {}, "llm_error": ""}

    with patch.object(engine, "run_agent", side_effect=runner):
        engine.start_from_profile(profile)
        frozen_story_key = engine.game_session.story_key
        assert engine.resolve_pending_model_failure("retry_model") is True

    assert calls == 3
    assert engine.pending_model_failure() is None
    assert engine.game_session.story_key == frozen_story_key
    assert engine.game_session.turn_count == 0
    assert engine.game_session.local_story_active is False
    assert len(engine.game_session.last_choices) == 4


def test_profile_opening_local_story_requires_explicit_player_action(monkeypatch) -> None:
    monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
    monkeypatch.setenv("AGENS_START_MODEL_WORLD", "1")
    engine = GameEngine()

    with patch.object(engine, "run_agent", return_value={"generated_data": {}, "llm_error": ""}):
        engine.start_from_profile({"char_name": "许满"})
        frozen_story_key = engine.game_session.story_key
        assert engine.resolve_pending_model_failure("use_local_story") is True

    assert engine.pending_model_failure() is None
    assert engine.game_session.story_key == frozen_story_key
    assert engine.game_session.local_story_active is True
    assert engine.game_session.turn_count == 0
    assert len(engine.game_session.last_choices) == 4
