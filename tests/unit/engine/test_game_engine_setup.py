"""Tests for GameEngine initialization and configuration — UI-agnostic game logic service."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

from agens_novel.engine.choices import fallback_choices, normalize_choices
from agens_novel.engine.game_engine import GameEngine
from agens_novel.engine.world_generator import build_world_fallback
from tests.unit.engine.fixtures import canned_judge as _canned_judge
from tests.unit.engine.fixtures import patch_turn_runner as _patch_turn_runner_base

# ═══════════════════════════════════════════════════════════════════════════════
# Canned helpers
# ═══════════════════════════════════════════════════════════════════════════════


def _canned_world_builder() -> dict[str, Any]:
    generated = build_world_fallback(
        {
            "char_name": "许满",
            "talent": "平平无奇",
            "spirit_root": "火木双灵根",
            "spirit_root_grade": "地",
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
    )
    generated["world"].update(
        {
            "current_scene": "晨雾中的青云山外门",
            "location": "青云山外门",
            "region": "东荒",
        }
    )
    generated["choices"] = [
        "留在山门吐纳",
        "询问接引弟子",
        "观察灵气流向",
        "【气运】随缘听天命",
    ]
    return {
        "generated_data": generated,
        "world_description": "",
        "opening_narrative": "",
        "output_path": "",
        "audit_path": "",
        "finished_at": "",
        "llm_error": "",
        "response_mode": "json_object",
        "provider_json_envelope_ok": True,
    }


def _complete_profile_world_builder() -> dict[str, Any]:
    generated = build_world_fallback(
        {
            "char_name": "许满",
            "talent": "平平无奇",
            "spirit_root": "木灵根",
            "family_background": "寒门",
            "difficulty": "普通",
        }
    )
    generated.update(
        {
            "world_name": "归墟潮界",
            "regions": [{"name": "潮音渡口", "description": "边境渡口"}],
            "sects": [{"name": "潮音阁", "alignment": "正道", "description": "镇守灵潮"}],
            "current_conflicts": ["边境灵潮提前"],
            "fate_hooks": ["散修命途"],
            "chronicle_0_16": [
                "零至六岁，他在边关听潮长大。",
                "七至十二岁，他开始辨认潮汐灵机。",
                "十三至十五岁，他随商队抵达渡口。",
            ],
            "initial_situation": "十六岁这年，仙途在潮音渡口开启。",
            "initial_situation_16": "十六岁这年，仙途在潮音渡口开启。",
            "opening_narrative": "十六岁这年，他来到潮音渡口，修行编年由此展开。",
            "choices": ["留守渡口", "打听灵潮", "夜探沉礁", "随潮而行"],
        }
    )
    generated["world"].update(
        {
            "current_scene": "十六岁这年，仙途在潮音渡口开启。",
            "location": "潮音渡口",
            "region": "归墟潮界",
            "lore_facts": ["边境灵潮提前。"],
        }
    )
    return {
        "generated_data": generated,
        "world_description": "潮声记录着边关旧事。",
        "opening_narrative": "十六岁这年，他来到潮音渡口，修行编年由此展开。",
        "output_path": "",
        "audit_path": "",
        "finished_at": "",
        "llm_error": "",
        "response_mode": "json_object",
        "provider_json_envelope_ok": True,
    }


def _canned_narrator() -> dict[str, Any]:
    return {
        "narrative": "你静坐吐纳，灵气缓缓涌入。",
        "state_delta": {"character": {"attributes": {"willpower": 1}}},
        "choices": [],
        "output_path": "",
        "audit_path": "",
        "finished_at": "",
        "llm_error": "",
    }


def _patch_turn_runner(call_log: list | None = None) -> Any:
    return _patch_turn_runner_base(
        narrator=_canned_narrator,
        judge=_canned_judge,
        world_builder=_canned_world_builder,
        call_log=call_log,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestGameEngineNewGame:
    def test_new_game_initializes_session(self, monkeypatch) -> None:
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
        engine = GameEngine()
        narratives: list[tuple[str, int]] = []
        engine.on_narrative = lambda text, turn: narratives.append((text, turn))

        with _patch_turn_runner():
            engine.new_game("我叫许满")

        assert engine.game_session.game_started is True
        assert engine.game_session.char_name == "许满"
        assert engine.game_session.realm == "练气"
        assert engine.game_session.attributes["root_bone"] == 5
        assert not hasattr(engine.game_session, "hp")
        assert not hasattr(engine.game_session, "mp")
        assert (
            engine.game_session.last_choices == _canned_world_builder()["generated_data"]["choices"]
        )
        assert len(narratives) == 1

    def test_incomplete_world_builder_choices_are_retried_then_rejected(self, monkeypatch) -> None:
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
        engine = GameEngine()
        calls = 0

        def runner(agent_name, user_input, session, **kw):
            nonlocal calls
            if agent_name == "world_builder":
                calls += 1
                data = _canned_world_builder()
                data["generated_data"]["choices"] = ["请教陈师兄", "查看山门规矩"]
                return data
            return {}

        with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=runner):
            engine.new_game("许满")

        assert calls == 2
        assert engine.game_session.game_started is False
        assert engine.game_session.last_choices == []

    def test_profile_opening_retries_transient_world_builder_failure(self, monkeypatch) -> None:
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
        monkeypatch.setenv("AGENS_START_MODEL_WORLD", "1")
        engine = GameEngine()
        infos: list[str] = []
        calls: list[str] = []
        engine.on_info = lambda msg: infos.append(msg)

        def runner(agent_name, user_input, session, **kw):
            calls.append(agent_name)
            if agent_name == "world_builder" and calls.count("world_builder") == 1:
                return {
                    "generated_data": {},
                    "llm_error": 'HTTP 404: {"error":{"type":"upstream_error","code":"404"}}',
                }
            if agent_name == "world_builder":
                return _complete_profile_world_builder()
            return {}

        with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=runner):
            engine.start_from_profile({"char_name": "许满"})

        assert calls.count("world_builder") == 2
        assert engine.game_session.region == "归墟潮界"
        assert engine.game_session.last_choices == ["留守渡口", "打听灵潮", "夜探沉礁", "随潮而行"]
        assert not any("模型" in msg or "fallback" in msg.lower() for msg in infos)

    def test_profile_opening_retries_visible_english_contract_violation(self, monkeypatch) -> None:
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
        monkeypatch.setenv("AGENS_START_MODEL_WORLD", "1")
        engine = GameEngine()
        calls: list[str] = []
        narratives: list[str] = []
        engine.on_narrative = lambda text, _turn: narratives.append(text)

        def runner(agent_name, user_input, session, **kw):
            calls.append(agent_name)
            result = _complete_profile_world_builder()
            if calls.count("world_builder") == 1:
                result["generated_data"]["opening_narrative"] = (
                    "十六岁前，他在 Harvest 与劳作间长大。"
                )
            return result

        with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=runner):
            engine.start_from_profile({"char_name": "许满"})

        assert calls.count("world_builder") == 2
        assert narratives == ["十六岁这年，他来到潮音渡口，修行编年由此展开。"]

    def test_model_choice_prefixes_are_cleaned(self) -> None:
        assert normalize_choices(["A：A 稳妥：闭关吐纳", "B. B、外出历练"]) == [
            "闭关吐纳",
            "外出历练",
        ]
        assert normalize_choices(["【气运】随缘而行"]) == ["【气运】随缘而行"]

    def test_visible_english_choice_is_replaced_without_shifting_route_semantics(self) -> None:
        engine = GameEngine()
        engine.game_session.location = "荒岭接引营"
        source = [
            "留在营中稳固根基",
            "寻找可能 bypass 常规试炼的门路",
            "前往山脉边缘承担受伤风险",
            "随缘等待未知因果显现",
        ]

        used_fallback = engine.set_choices(source, source="test")

        assert used_fallback is False
        assert engine.game_session.last_choices[0] == source[0]
        assert engine.game_session.last_choices[1] == fallback_choices(engine.game_session)[1]
        assert engine.game_session.last_choices[2:] == source[2:]

    def test_empty_model_choices_create_pending_failure(self, monkeypatch) -> None:
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
        engine = GameEngine()
        infos: list[str] = []
        engine.on_info = lambda msg: infos.append(msg)
        with _patch_turn_runner():
            engine.start_from_profile({"char_name": "许满", "choices": ["观察山门"]})

        def runner(agent_name, user_input, session, **kw):
            if agent_name == "narrator":
                return {
                    "narrative": "风声一滞。",
                    "state_delta": {"character": {"attributes": {"willpower": 1}}},
                    "choices": [],
                    "llm_error": "timeout",
                }
            return {}

        with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=runner):
            engine.handle_action("观察")

        assert len(engine.game_session.last_choices) == 4
        assert engine.pending_model_failure() is not None
        assert any("请选择重试" in msg for msg in infos)

    def test_successful_narrative_without_choices_shows_recovery_notice(self, monkeypatch) -> None:
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
        engine = GameEngine()
        infos: list[str] = []
        engine.on_info = lambda msg: infos.append(msg)
        with _patch_turn_runner():
            engine.start_from_profile(
                {"char_name": "许满", "opening_narrative": "山门初开。", "choices": ["观察"]}
            )

        def runner(agent_name, user_input, session, **kw):
            if agent_name == "narrator":
                return {
                    "narrative": "你听见钟声。",
                    "state_delta": {"character": {"attributes": {"willpower": 1}}},
                    "choices": [],
                    "llm_error": "",
                }
            if agent_name == "judge":
                return _canned_judge()
            return {}

        with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=runner):
            engine.handle_action("观察")

        assert engine.pending_model_failure() is not None
        assert not any("补齐下一步选择" in msg or "因果结算" in msg for msg in infos)
        assert engine.game_session.local_story_active is False

    def test_new_game_without_api_key_creates_pending_failure(self, monkeypatch) -> None:
        """World Builder configuration errors wait for an explicit decision."""
        monkeypatch.delenv("AGNES_API_KEY", raising=False)
        engine = GameEngine()
        engine.new_game("test")
        pending = engine.pending_model_failure()
        assert pending is not None
        assert pending.stage == "opening"

    def test_new_game_empty_concept(self, monkeypatch) -> None:
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
        engine = GameEngine()
        infos: list[str] = []
        engine.on_info = lambda msg: infos.append(msg)
        engine.new_game("")
        assert "取消" in infos[0]

    def test_new_game_llm_error(self, monkeypatch) -> None:
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
        engine = GameEngine()

        def fake_runner(agent_name, user_input, session, **kw):
            return {**_canned_world_builder(), "llm_error": "API rate limit"}

        with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=fake_runner):
            engine.new_game("test")
        pending = engine.pending_model_failure()
        assert pending is not None
        assert pending.error_code == "request_failed"

    def test_new_game_empty_data(self, monkeypatch) -> None:
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
        engine = GameEngine()
        infos: list[str] = []
        engine.on_info = lambda msg: infos.append(msg)

        def fake_runner(agent_name, user_input, session, **kw):
            return {"generated_data": {}, "llm_error": ""}

        with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=fake_runner):
            engine.new_game("test")
        assert engine.pending_model_failure() is not None
        assert any("请选择重试" in message for message in infos)


class TestGameEngineReset:
    def test_reset(self) -> None:
        engine = GameEngine()
        engine.game_session.char_name = "许满"
        engine.game_session.game_started = True
        engine.game_session.turn_count = 50
        engine.reset()
        assert engine.game_session.char_name == ""
        assert engine.game_session.game_started is False
