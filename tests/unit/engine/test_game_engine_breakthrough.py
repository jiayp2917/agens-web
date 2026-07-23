"""Tests for GameEngine breakthrough routing and preparation."""

from __future__ import annotations

from unittest.mock import patch

from agens_novel.engine.action_delta_policy import is_pure_cultivation
from agens_novel.engine.choices import fallback_choices
from agens_novel.engine.game_engine import GameEngine
from agens_novel.engine.story_catalog import opening_story_binding
from tests.unit.engine.fixtures import canned_judge as _canned_judge
from tests.unit.engine.fixtures import canned_world_builder as _canned_world_builder
from tests.unit.engine.turn_test_support import FixedRuleRng as _FixedRuleRng
from tests.unit.engine.turn_test_support import patch_turn_runner_for_tests as _patch_turn_runner


class TestBreakthroughRouting:
    """Tests for natural-language breakthrough detection and routing."""

    def test_parse_breakthrough_action(self) -> None:
        """_parse_breakthrough_action detects breakthrough keywords."""
        engine = GameEngine()
        engine.game_session.game_started = True

        assert engine._parse_breakthrough_action("突破") is True
        assert engine._parse_breakthrough_action("尝试突破") is True
        assert engine._parse_breakthrough_action("冲击筑基") is True
        assert engine._parse_breakthrough_action("准备渡劫飞升") is True
        assert engine._parse_breakthrough_action("闭关修炼") is False
        assert engine._parse_breakthrough_action("探索秘境") is False

    def test_breakthrough_keyword_always_detected_in_game_mode(self) -> None:
        """Game-mode v5: combat is event-based; there is no structured combat
        state to suppress breakthrough intent. The keyword is detected normally."""
        engine = GameEngine()
        engine.game_session.game_started = True
        assert engine._parse_breakthrough_action("突破") is True

    def test_ineligible_breakthrough_choice_settles_as_ordinary_turn(self, monkeypatch) -> None:
        """A premature breakthrough button must not return success with no turn."""
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
        engine = GameEngine()
        infos: list[str] = []
        engine.on_info = lambda msg: infos.append(msg)
        call_log: list[str] = []

        with _patch_turn_runner():
            engine.new_game("许满")

        # Character is at stage 1, not max. The action still consumes a normal
        # turn so the web API cannot return HTTP 200 with unchanged turn_count.
        with _patch_turn_runner(call_log):
            engine.handle_action("尝试突破")

        assert any("继续推进" in m for m in infos)
        assert call_log == ["narrator", "judge"]
        assert engine.game_session.turn_count == 1
        assert engine.game_session.turn_history[-1]["turn"] == 1

    def test_ineligible_breakthrough_options_are_rewritten(self, monkeypatch) -> None:
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
        engine = GameEngine()
        engine.game_session.game_started = True
        engine.game_session.realm = "练气"
        engine.game_session.realm_stage = 1

        def runner(agent_name, user_input, session, **kw):
            if agent_name == "narrator":
                return {
                    "narrative": "你试探经脉，灵气尚浅。",
                    "state_delta": {"character": {"attributes": {"willpower": 1}}},
                    "choices": ["A：闭关吐纳", "B：请教师兄", "C：冲击筑基", "D：随缘听天命"],
                    "llm_error": "",
                }
            if agent_name == "judge":
                return _canned_judge()
            return {}

        with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=runner):
            engine.handle_action("检查修为")

        assert engine.game_session.turn_count == 1
        assert engine.game_session.last_choices[0] == "闭关吐纳"
        assert engine.game_session.last_choices[1] == "请教师兄"
        assert "冲击" not in engine.game_session.last_choices[2]
        assert "突破" not in engine.game_session.last_choices[2]

    def test_eligible_breakthrough_is_exposed_in_risk_slot(self) -> None:
        engine = GameEngine()
        engine.game_session.game_started = True
        engine.game_session.realm = "练气"
        engine.game_session.realm_stage = 9
        engine.game_session.breakthrough_flags = ["foundation_aid"]

        choices = engine._filter_unavailable_breakthrough_choices(
            ["闭关温养根基", "拜访同门问道", "深入古道查探", "静候命数回响"]
        )

        assert choices[:2] == ["闭关温养根基", "拜访同门问道"]
        assert "冲击筑基" in choices[2]
        assert choices[3] == "静候命数回响"

    def test_eligible_breakthrough_is_removed_from_non_risk_slots(self) -> None:
        engine = GameEngine()
        engine.game_session.game_started = True
        engine.game_session.realm = "练气"
        engine.game_session.realm_stage = 9
        engine.game_session.breakthrough_flags = ["foundation_aid"]

        choices = engine._filter_unavailable_breakthrough_choices(
            ["稳妥冲击筑基", "拜访同门问道", "深入古道查探", "随缘突破"]
        )

        assert "突破" not in choices[0] and "冲击" not in choices[0]
        assert "冲击筑基" in choices[2]
        assert "突破" not in choices[3]

    def test_blocked_breakthrough_options_force_healing_and_remove_retry(self) -> None:
        engine = GameEngine()
        engine.game_session.game_started = True
        engine.game_session.realm = "练气"
        engine.game_session.realm_stage = 9
        engine.game_session.breakthrough_flags = ["foundation_aid"]
        engine.game_session.status_effects = ["走火入魔", "旧伤"]

        choices = engine._filter_unavailable_breakthrough_choices(
            ["闭关温养", "拜访丹师", "再次冲击筑基", "静候命数回响"]
        )

        assert "疗伤" in choices[0]
        assert "走火入魔" in choices[0]
        assert all("突破" not in choice and "冲击筑基" not in choice for choice in choices)


class TestBreakthroughPreparationGate:
    """Tests for the v5 breakthrough preparation gate and cultivation classification."""

    def test_is_pure_cultivation_detection(self) -> None:
        """Meditation phrases are pure cultivation; other deeds are not."""
        assert is_pure_cultivation("闭关修炼") is True
        assert is_pure_cultivation("打坐修行") is True
        assert is_pure_cultivation("静坐吐纳") is True
        assert is_pure_cultivation("盘膝运功") is True
        assert is_pure_cultivation("吸纳天地灵气") is True
        # Practising a martial art / exploring / contemplating are NOT pure.
        assert is_pure_cultivation("修炼剑法") is False
        assert is_pure_cultivation("外出历练") is False
        assert is_pure_cultivation("参悟功法") is False
        assert is_pure_cultivation("打坐参悟") is False
        assert is_pure_cultivation("") is False

    def test_legacy_insight_delta_is_ignored(self, monkeypatch) -> None:
        """Legacy insight/experience deltas do not create removed fields."""
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
        engine = GameEngine()

        def narrator_with_legacy_fields(agent_name, user_input, session, **kwargs):
            if agent_name == "world_builder":
                return _canned_world_builder()
            if agent_name == "narrator":
                return {
                    "narrative": "你闭关吐纳。",
                    "state_delta": {"character": {"experience": "+20", "insight": "+50"}},
                    "choices": ["继续吐纳", "检查瓶颈", "出门历练"],
                }
            if agent_name == "judge":
                return _canned_judge()
            return {}

        with patch(
            "agens_novel.engine.game_engine.run_turn_sync", side_effect=narrator_with_legacy_fields
        ):
            engine.new_game("许满")
            engine.handle_action("闭关修炼")

        assert not hasattr(engine.game_session, "insight")
        assert not hasattr(engine.game_session, "experience")

    def test_breakthrough_blocked_without_preparation(self, monkeypatch) -> None:
        """Max layer without breakthrough preparation is blocked."""
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
        engine = GameEngine()
        infos: list[str] = []
        engine.on_info = lambda msg: infos.append(msg)

        engine.game_session.game_started = True
        engine.game_session.realm = "练气"
        engine.game_session.realm_stage = 9  # max layer
        engine.game_session.breakthrough_flags = []

        engine.attempt_breakthrough()

        assert engine.game_session.realm == "练气", "Breakthrough must be blocked"
        assert any("破境准备不足" in m for m in infos), infos

    def test_breakthrough_allowed_with_preparation(self, monkeypatch) -> None:
        """Max layer + required preparation can break through."""
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
        engine = GameEngine()

        with _patch_turn_runner():
            engine.new_game("许满")

        engine.game_session.realm = "练气"
        engine.game_session.realm_stage = 9
        engine.game_session.breakthrough_flags = ["foundation_aid"]

        with _patch_turn_runner():
            with patch("agens_novel.game.realm._breakthrough_roll", return_value=0.001):
                engine.attempt_breakthrough()

        assert engine.game_session.realm == "筑基", (
            f"Breakthrough should reach 筑基, got {engine.game_session.realm}"
        )
        assert engine.game_session.local_story_active is False
        assert len(engine.game_session.last_choices) == 4

    def test_v3_breakthrough_turn_advances_the_main_story(self, monkeypatch) -> None:
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
        engine = GameEngine()

        with _patch_turn_runner():
            engine.new_game("许满")

        session = engine.game_session
        binding = opening_story_binding(
            "forest",
            ["苦修", "天命"],
            content_version=3,
            run_seed="breakthrough-v3",
            character_name=session.char_name,
        )
        session.story_key = binding["story_key"]
        session.story_version = binding["story_version"]
        session.story_state = binding["story_state"]
        session.turn_count = 89
        session.realm = "练气"
        session.realm_stage = 9
        session.breakthrough_flags = ["foundation_aid"]

        with _patch_turn_runner():
            with patch("agens_novel.game.realm._breakthrough_roll", return_value=0.001):
                engine.attempt_breakthrough()

        assert session.turn_count == 90
        assert session.story_state["arc_resolution"] in {"resolved", "failed"}
        assert session.story_state["status"] == "post_arc"

    def test_breakthrough_updates_model_choices(self, monkeypatch) -> None:
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
        engine = GameEngine()

        with _patch_turn_runner():
            engine.new_game("许满")

        engine.game_session.realm = "练气"
        engine.game_session.realm_stage = 9
        engine.game_session.breakthrough_flags = ["foundation_aid"]

        def runner(agent_name, user_input, session, **kw):
            if agent_name == "narrator":
                return {
                    "narrative": "你破开瓶颈。",
                    "state_delta": {},
                    "choices": ["稳固筑基道台", "拜谢护法长老", "查看新功法"],
                    "llm_error": "",
                }
            if agent_name == "judge":
                return _canned_judge()
            return {}

        with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=runner):
            with patch("agens_novel.game.realm._breakthrough_roll", return_value=0.001):
                engine.attempt_breakthrough()

        assert engine.game_session.realm == "筑基"
        assert engine.game_session.last_choices == [
            "稳固筑基道台",
            "拜谢护法长老",
            "查看新功法",
            fallback_choices(engine.game_session)[3],
        ]

    def test_breakthrough_narrator_error_keeps_rule_settlement(self, monkeypatch) -> None:
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
        engine = GameEngine()
        infos: list[str] = []
        narratives: list[str] = []
        engine.on_info = lambda msg: infos.append(msg)
        engine.on_narrative = lambda text, _turn: narratives.append(text)

        with _patch_turn_runner():
            engine.new_game("许满")

        engine.game_session.realm = "练气"
        engine.game_session.realm_stage = 9
        engine.game_session.breakthrough_flags = ["foundation_aid"]

        def runner(agent_name, user_input, session, **kw):
            if agent_name == "narrator":
                return {"narrative": "", "state_delta": {}, "choices": [], "llm_error": "timeout"}
            return {}

        with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=runner):
            with patch(
                "agens_novel.game.realm.rule_rng_for_session",
                return_value=_FixedRuleRng(0.0),
            ):
                engine.attempt_breakthrough()

        assert engine.game_session.realm == "筑基"
        assert len(engine.game_session.last_choices) == 4
        assert any("破境已成" in text for text in narratives)
        assert not any("突破概率" in msg or "破境准备" in msg for msg in infos)

    def test_breakthrough_emits_model_diagnostics_without_internal_info(self, monkeypatch) -> None:
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
        engine = GameEngine()
        infos: list[str] = []
        model_results: list[tuple[str, str, str]] = []
        engine.on_info = lambda msg: infos.append(msg)
        engine.on_model_result = lambda agent, source, status, *_args: model_results.append(
            (agent, source, status)
        )
        engine.game_session.game_started = True
        engine.game_session.realm = "练气"
        engine.game_session.realm_stage = 9
        engine.game_session.breakthrough_flags = ["foundation_aid"]

        def runner(agent_name, user_input, session, **kw):
            if agent_name == "narrator":
                return {
                    "narrative": "灵机贯通，旧有瓶颈就此松脱，其人稳稳踏入筑基初期。",
                    "state_delta": {},
                    "choices": ["稳固道台", "拜访执事", "深入古道", "静候天机"],
                    "llm_error": "",
                }
            if agent_name == "judge":
                return _canned_judge()
            return {}

        with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=runner):
            with patch("agens_novel.game.realm.random.random", return_value=0.001):
                engine.attempt_breakthrough()

        assert ("narrator", "breakthrough", "ok") in model_results
        assert ("judge", "breakthrough", "ok") in model_results
        assert not any("突破概率" in msg or "破境准备" in msg for msg in infos)

    def test_breakthrough_duplicate_choices_retry_live_once(self) -> None:
        engine = GameEngine()
        engine.game_session.game_started = True
        engine.game_session.realm = "练气"
        engine.game_session.realm_stage = 9
        engine.game_session.breakthrough_flags = ["foundation_aid"]
        narrator_calls = 0

        def runner(agent_name, user_input, session, **kw):
            nonlocal narrator_calls
            if agent_name == "narrator":
                narrator_calls += 1
                if narrator_calls == 1:
                    return {
                        "narrative": "灵机贯通，其人踏入筑基初期。",
                        "state_delta": {"character": {}, "world": {}, "meta": {}},
                        "choices": ["稳固道台", "拜访执事", "查看新境", "查看新境"],
                        "provider_json_schema": True,
                        "provider_json_envelope_ok": True,
                        "llm_error": "",
                    }
                return {
                    "narrative": "灵机贯通，其人踏入筑基初期，山门旧局也随之改变。",
                    "state_delta": {"character": {}, "world": {}, "meta": {}},
                    "choices": ["稳固道台", "拜访执事", "查看新境", "静候命数"],
                    "provider_json_schema": True,
                    "provider_json_envelope_ok": True,
                    "llm_error": "",
                }
            return _canned_judge()

        with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=runner):
            with patch("agens_novel.game.realm.random.random", return_value=0.0):
                engine.attempt_breakthrough()

        assert narrator_calls == 2
        assert engine.game_session.realm == "筑基"
        assert engine.game_session.last_choices == ["稳固道台", "拜访执事", "查看新境", "静候命数"]

    def test_narrator_retry_recovers_transient_404_without_fallback(self, monkeypatch) -> None:
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
        engine = GameEngine()
        infos: list[str] = []
        narratives: list[tuple[str, int]] = []
        engine.on_info = lambda msg: infos.append(msg)
        engine.on_narrative = lambda text, turn: narratives.append((text, turn))
        engine.on_model_failure_choice = lambda source, reason: "fallback"

        with _patch_turn_runner():
            engine.new_game("许满")

        calls = {"narrator": 0}

        def runner(agent_name, user_input, session, **kw):
            if agent_name == "narrator":
                calls["narrator"] += 1
                if calls["narrator"] == 1:
                    return {
                        "narrative": "",
                        "state_delta": {},
                        "choices": [],
                        "llm_error": 'HTTP 404: {"error":{"type":"upstream_error","code":"404"}}',
                    }
                return {
                    "narrative": "你将地图副本交入执事堂，换得一段清静修行时日。",
                    "state_delta": {"character": {"attributes": {"willpower": 1}}},
                    "choices": ["回院吐纳", "打听赏格", "追查地图", "随缘等候"],
                    "llm_error": "",
                }
            if agent_name == "judge":
                return _canned_judge()
            return {}

        with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=runner):
            engine.handle_action("将地图副本上交执事堂")

        assert calls["narrator"] == 2
        assert engine.game_session.turn_count == 1
        assert engine.game_session.local_story_active is False
        assert len(engine.game_session.last_choices) == 4
        assert narratives and "地图副本" in narratives[-1][0]
        assert not any("上游模型" in msg for msg in infos)
