"""Tests for ordinary GameEngine turn execution."""

from __future__ import annotations

from unittest.mock import patch

from agens_novel.engine.game_engine import GameEngine
from tests.unit.engine.fixtures import canned_judge as _canned_judge
from tests.unit.engine.turn_test_support import patch_turn_runner_for_tests as _patch_turn_runner


class TestGameEngineHandleAction:
    def test_action_runs_narrator_without_judge(self, monkeypatch) -> None:
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
        call_log: list[str] = []
        engine = GameEngine()

        # Set up a started game.
        with _patch_turn_runner():
            engine.new_game("许满")
        engine.game_session.last_choices = [
            "留在山门吐纳",
            "询问接引弟子",
            "强闯禁地",
            "随缘听天命",
        ]

        def runner(agent_name, user_input, session, **kw):
            call_log.append(agent_name)
            if agent_name == "narrator":
                return {
                    "narrative": "你强闯禁地边缘，被阴风擦过经脉。",
                    "state_delta": {"character": {"status_effects_add": ["阴风侵体"]}},
                    "choices": ["返回山门", "请教师兄", "继续观察", "随缘听天命"],
                    "output_path": "",
                    "audit_path": "",
                    "finished_at": "",
                    "llm_error": "",
                }
            return {}

        with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=runner):
            engine.handle_action("C")

        assert call_log == ["narrator"]
        assert engine.game_session.turn_count == 1
        assert not hasattr(engine.game_session, "experience")
        assert engine.game_session.age > 16

    def test_choice_letter_routes_to_current_choice(self, monkeypatch) -> None:
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
        seen_inputs: list[str] = []
        engine = GameEngine()
        with _patch_turn_runner():
            engine.start_from_profile(
                {
                    "char_name": "许满",
                    "choices": ["留在山门吐纳", "询问接引弟子", "观察灵气流向"],
                    "_allow_choice_override": True,
                }
            )

        def runner(agent_name, user_input, session, **kw):
            if agent_name == "narrator":
                seen_inputs.append(user_input)
                return {
                    "narrative": "你向接引弟子行礼。",
                    "state_delta": {"character": {"attributes": {"willpower": 1}}},
                    "choices": ["继续询问", "返回山门", "观察弟子神色", "顺着天命静候"],
                    "llm_error": "",
                }
            if agent_name == "judge":
                return _canned_judge()
            return {}

        with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=runner):
            engine.handle_action("B")

        assert seen_inputs[0].startswith("B【机遇】询问接引弟子")
        assert engine.game_session.last_choices == [
            "继续询问",
            "返回山门",
            "观察弟子神色",
            "顺着天命静候",
        ]

    def test_choice_letter_ignores_missing_slot(self, monkeypatch) -> None:
        engine = GameEngine()
        engine.game_session.game_started = True
        engine.game_session.last_choices = ["只给一条"]

        assert engine._resolve_choice_input("C") is None

    def test_d_prefix_is_not_free_typed_action(self, monkeypatch) -> None:
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
        engine = GameEngine()
        engine.game_session.game_started = True
        engine.game_session.last_choices = [
            "留在山门吐纳",
            "询问接引弟子",
            "观察灵气流向",
            "随缘听天命",
        ]

        assert engine._resolve_choice_input("D: 沿石阶寻找隐藏碑文") is None
        assert engine._resolve_choice_input("D") == "D【气运】随缘听天命"

    def test_action_without_game(self, monkeypatch) -> None:
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
        engine = GameEngine()
        infos: list[str] = []
        engine.on_info = lambda msg: infos.append(msg)
        engine.handle_action("修炼")
        assert "尚未开始" in infos[0]

    def test_action_game_over(self, monkeypatch) -> None:
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
        engine = GameEngine()
        engine.game_session.game_started = True
        engine.game_session.game_over = True
        engine.game_session.error = "魂飞魄散"
        infos: list[str] = []
        engine.on_info = lambda msg: infos.append(msg)
        engine.handle_action("修炼")
        assert "游戏已结束" in infos[0]

    def test_narrator_exception_restores_turn(self, monkeypatch) -> None:
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
        engine = GameEngine()
        engine.game_session.game_started = True
        infos: list[str] = []
        engine.on_info = lambda msg: infos.append(msg)

        def fake_runner(agent_name, user_input, session, **kw):
            raise RuntimeError("LLM exploded")

        with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=fake_runner):
            engine.handle_action("修炼")

        assert engine.game_session.turn_count == 0
        assert engine.game_session.local_story_active is False
        assert len(engine.game_session.last_choices) == 0
        assert engine.pending_model_failure() is not None
        assert any("请选择重试" in msg for msg in infos)

    def test_narrator_exception_can_end_run_from_ui_choice(self, monkeypatch) -> None:
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
        engine = GameEngine()
        engine.game_session.game_started = True
        def fake_runner(agent_name, user_input, session, **kw):
            raise RuntimeError("LLM exploded")

        with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=fake_runner):
            engine.handle_action("修炼")

        assert engine.game_session.turn_count == 0
        assert engine.game_session.game_over is False
        assert engine.pending_model_failure() is not None

    def test_narrative_without_choices_creates_pending_failure(self, monkeypatch) -> None:
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
        engine = GameEngine()
        engine.game_session.game_started = True
        narratives: list[tuple[str, int]] = []
        engine.on_narrative = lambda text, turn: narratives.append((text, turn))
        infos: list[str] = []
        engine.on_info = lambda msg: infos.append(msg)
        calls: list[str] = []

        def runner(agent_name, user_input, session, **kw):
            calls.append(agent_name)
            if agent_name == "narrator":
                return {
                    "narrative": "你在山门前盘膝吐纳，晨雾沿石阶慢慢散开。",
                    "state_delta": {},
                    "choices": [],
                    "llm_error": "",
                }
            return {"approved": True, "corrected_delta": {}, "llm_error": ""}

        with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=runner):
            engine.handle_action("修炼")

        assert engine.game_session.game_over is False
        assert engine.game_session.turn_count == 0
        assert engine.game_session.local_story_active is False
        assert engine.game_session.last_choices == []
        assert calls == ["narrator", "narrator"]
        assert narratives == []
        assert engine.game_session.turn_history == []
        assert engine.pending_model_failure() is not None

    def test_narrative_reward_claim_without_choices_remains_pending(
        self, monkeypatch
    ) -> None:
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
        engine = GameEngine()
        engine.game_session.game_started = True
        engine.game_session.inventory = []
        narratives: list[tuple[str, int]] = []
        infos: list[str] = []
        engine.on_narrative = lambda text, turn: narratives.append((text, turn))
        engine.on_info = lambda msg: infos.append(msg)

        def runner(agent_name, user_input, session, **kw):
            if agent_name == "narrator":
                return {
                    "narrative": "你获得一枚清灵丹。",
                    "state_delta": {},
                    "choices": [],
                    "llm_error": "",
                }
            return {"approved": True, "corrected_delta": {}, "llm_error": ""}

        with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=runner):
            engine.handle_action("修炼")

        assert engine.game_session.game_over is False
        assert engine.game_session.turn_count == 0
        assert engine.game_session.local_story_active is False
        assert engine.game_session.last_choices == []
        assert engine.game_session.inventory == []
        assert narratives == []
        assert engine.game_session.turn_history == []
        assert engine.pending_model_failure() is not None

    def test_empty_model_output_creates_pending_failure(self, monkeypatch) -> None:
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
        engine = GameEngine()
        engine.game_session.game_started = True
        infos: list[str] = []
        errors: list[str] = []
        engine.on_info = lambda msg: infos.append(msg)
        engine.on_error = lambda msg: errors.append(msg)

        def runner(agent_name, user_input, session, **kw):
            if agent_name == "narrator":
                return {"narrative": "", "state_delta": {}, "choices": [], "llm_error": ""}
            return {"approved": True, "corrected_delta": {}, "llm_error": ""}

        with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=runner):
            engine.handle_action("观察山门")

        assert errors == []
        assert any("请选择重试" in msg for msg in infos)
        assert engine.game_session.local_story_active is False
        assert engine.game_session.last_choices == []
        assert engine.pending_model_failure() is not None

    def test_unrecoverable_empty_narrator_output_retries_live_once(self, monkeypatch) -> None:
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
        engine = GameEngine()
        engine.game_session.game_started = True
        engine.game_session.last_choices = ["闭门吐纳", "外出访友", "夜探山径", "随缘静候"]
        narratives: list[tuple[str, int]] = []
        infos: list[str] = []
        calls: list[tuple[str, str]] = []
        engine.on_narrative = lambda text, turn: narratives.append((text, turn))
        engine.on_info = lambda msg: infos.append(msg)
        engine.on_model_failure_choice = lambda source, reason: "fallback"

        def runner(agent_name, user_input, session, **kw):
            calls.append((agent_name, user_input))
            if (
                agent_name == "narrator"
                and len([call for call in calls if call[0] == "narrator"]) == 1
            ):
                return {"narrative": "", "state_delta": {}, "choices": [], "llm_error": ""}
            if agent_name == "narrator":
                return {
                    "narrative": "此后，许满避开山径纷争，借村落香火安稳调息。",
                    "state_delta": {"character": {}, "world": {}, "meta": {}},
                    "choices": ["继续静养", "打听山门消息", "查看旧伤", "随缘等候"],
                    "llm_error": "",
                    "retried_after_incomplete_output": True,
                }
            return {"approved": True, "corrected_delta": {}, "llm_error": ""}

        with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=runner):
            engine.handle_action("D")

        narrator_calls = [call for call in calls if call[0] == "narrator"]
        assert len(narrator_calls) == 2
        assert "输出契约提醒" in narrator_calls[1][1]
        assert engine.game_session.turn_count == 1
        assert engine.game_session.local_story_active is False
        assert "local_story" not in engine.game_session.turn_history[-1]
        assert engine.game_session.turn_history[-1]["delta"]["meta"]["choice_category"] in {
            "稳妥",
            "机遇",
            "风险",
            "气运",
        }
        assert narratives and "村落香火" in narratives[-1][0]
        assert not any("天道紊乱" in msg or "因果结算" in msg for msg in infos)

    def test_schema_narrator_with_duplicate_choice_retries_live_once(self) -> None:
        engine = GameEngine()
        engine.game_session.game_started = True
        engine.game_session.last_choices = ["闭门吐纳", "外出访友", "夜探山径", "随缘静候"]
        narrator_calls = 0

        def runner(agent_name, user_input, session, **kw):
            nonlocal narrator_calls
            if agent_name == "narrator":
                narrator_calls += 1
                if narrator_calls == 1:
                    return {
                        "narrative": "此后三年，山门旧案再起波澜，其人循线查访。",
                        "state_delta": {"character": {}, "world": {}, "meta": {}},
                        "choices": ["闭门整理", "拜访执事", "夜探山径", "夜探山径"],
                        "provider_json_schema": True,
                        "provider_json_envelope_ok": True,
                        "llm_error": "",
                    }
                return {
                    "narrative": "此后三年，山门旧案再起波澜，其人循线查访并确认新的去向。",
                    "state_delta": {"character": {}, "world": {}, "meta": {}},
                    "choices": ["闭门整理", "拜访执事", "夜探山径", "静候命数"],
                    "provider_json_schema": True,
                    "provider_json_envelope_ok": True,
                    "llm_error": "",
                }
            return {"approved": True, "corrected_delta": {}, "llm_error": ""}

        with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=runner):
            engine.handle_action("A")

        assert narrator_calls == 2
        assert engine.game_session.turn_count == 1
        assert engine.game_session.local_story_active is False
        assert engine.game_session.last_choices == ["闭门整理", "拜访执事", "夜探山径", "静候命数"]

    def test_schema_narrator_retries_english_residue_with_chinese_contract(self) -> None:
        engine = GameEngine()
        engine.game_session.game_started = True
        engine.game_session.last_choices = ["闭门吐纳", "外出访友", "夜探山径", "随缘静候"]
        calls: list[str] = []

        def runner(agent_name, user_input, session, **kw):
            if agent_name == "narrator":
                calls.append(user_input)
                if len(calls) == 1:
                    return {
                        "narrative": "他在宗门外整理 old records，等候新的榜文。",
                        "state_delta": {"character": {}, "world": {}, "meta": {}},
                        "choices": ["闭门吐纳", "寻访同门", "夜探山径", "随缘静候"],
                        "contract_diagnostics": {
                            "english_residue": True,
                            "narrative_english_residue": True,
                            "choice_english_indices": [],
                        },
                        "provider_json_schema": True,
                        "provider_json_envelope_ok": True,
                        "llm_error": "",
                    }
                return {
                    "narrative": "其人在宗门外整理旧录，等候新榜传来，外门执事已开始清查旧案。",
                    "state_delta": {"character": {}, "world": {}, "meta": {}},
                    "choices": ["闭门吐纳", "寻访同门", "夜探山径", "随缘静候"],
                    "contract_diagnostics": {
                        "english_residue": False,
                        "narrative_english_residue": False,
                        "choice_english_indices": [],
                    },
                    "provider_json_schema": True,
                    "provider_json_envelope_ok": True,
                    "llm_error": "",
                }
            return {"approved": True, "corrected_delta": {}, "llm_error": ""}

        with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=runner):
            engine.handle_action("A")

        assert len(calls) == 2
        assert "不得含任何英文字母" in calls[1]
        assert engine.game_session.local_story_active is False
        assert engine.game_session.turn_count == 1
        assert "old records" not in engine.game_session.turn_history[-1]["narrative"]

    def test_schema_narrator_two_english_attempts_create_pending_failure(self) -> None:
        engine = GameEngine()
        engine.game_session.game_started = True
        engine.game_session.last_choices = ["闭门吐纳", "外出访友", "夜探山径", "随缘静候"]
        calls = 0

        def runner(agent_name, user_input, session, **kw):
            nonlocal calls
            if agent_name == "narrator":
                calls += 1
                return {
                    "narrative": "He keeps a foreign chronicle in the hall.",
                    "state_delta": {"character": {}, "world": {}, "meta": {}},
                    "choices": ["闭门吐纳", "寻访同门", "夜探山径", "随缘静候"],
                    "contract_diagnostics": {
                        "english_residue": True,
                        "narrative_english_residue": True,
                        "choice_english_indices": [],
                    },
                    "provider_json_schema": True,
                    "provider_json_envelope_ok": True,
                    "llm_error": "",
                }
            return {"approved": True, "corrected_delta": {}, "llm_error": ""}

        with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=runner):
            engine.handle_action("A")

        assert calls == 2
        assert engine.game_session.local_story_active is False
        assert engine.game_session.turn_history == []
        assert engine.pending_model_failure() is not None

    def test_turn_rewrites_model_invented_exact_time_span(self) -> None:
        engine = GameEngine()
        engine.game_session.game_started = True
        engine.game_session.last_choices = ["闭门吐纳", "外出访友", "夜探山径", "随缘静候"]

        def runner(agent_name, user_input, session, **kw):
            if agent_name == "narrator":
                return {
                    "narrative": "四十二载间，山门旧案未平，其人仍在洞府中调息。",
                    "state_delta": {"character": {}, "world": {}, "meta": {}},
                    "choices": ["闭门吐纳", "寻访同门", "夜探山径", "随缘静候"],
                    "llm_error": "",
                }
            return {"approved": True, "corrected_delta": {}, "llm_error": ""}

        with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=runner):
            engine.handle_action("A")

        narrative = engine.game_session.turn_history[-1]["narrative"]
        assert "四十二载" not in narrative
        assert "岁月流转" in narrative

    def test_json_only_narrator_delta_creates_pending_failure(
        self, monkeypatch
    ) -> None:
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
        engine = GameEngine()
        engine.game_session.game_started = True
        engine.game_session.last_choices = ["闭门吐纳", "外出访友", "夜探山径", "随缘静候"]
        narratives: list[tuple[str, int]] = []
        infos: list[str] = []
        calls: list[tuple[str, str]] = []
        engine.on_narrative = lambda text, turn: narratives.append((text, turn))
        engine.on_info = lambda msg: infos.append(msg)

        def runner(agent_name, user_input, session, **kw):
            calls.append((agent_name, user_input))
            if agent_name == "narrator":
                return {
                    "narrative": "",
                    "state_delta": {
                        "character": {
                            "attributes": {"luck": 9},
                            "status_effects_add": ["轻躁"],
                        },
                        "world": {
                            "current_scene": "青岚坊市",
                            "location": "青岚坊市",
                        },
                        "meta": {},
                    },
                    "choices": [],
                    "llm_error": "",
                }
            return {"approved": True, "corrected_delta": {}, "llm_error": ""}

        with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=runner):
            engine.handle_action("B")

        narrator_calls = [call for call in calls if call[0] == "narrator"]
        assert len(narrator_calls) == 2
        assert engine.game_session.turn_count == 0
        assert engine.game_session.local_story_active is False
        assert engine.game_session.turn_history == []
        assert engine.game_session.attributes.get("luck") != 9
        assert "轻躁" not in engine.game_session.status_effects
        assert engine.game_session.current_scene != "青岚坊市"
        assert len(engine.game_session.last_choices) == 4
        assert narratives == []
        assert engine.pending_model_failure() is not None

    def test_malformed_state_update_with_narrative_recovers_as_rule_settled_turn(
        self, monkeypatch
    ) -> None:
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
        engine = GameEngine()
        engine.game_session.game_started = True
        infos: list[str] = []
        engine.on_info = lambda msg: infos.append(msg)
        engine.on_model_failure_choice = lambda source, reason: "fallback"

        def runner(agent_name, user_input, session, **kw):
            if agent_name == "narrator":
                return {
                    "narrative": "你在山门前停步，听见执事提起一卷残缺竹简。",
                    "state_delta": None,
                    "choices": ["登记借阅名册", "询问执事来历", "夜里潜去旧架", "随缘抽取一卷"],
                    "llm_error": "",
                }
            return {"approved": True, "corrected_delta": {}, "llm_error": ""}

        with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=runner):
            engine.handle_action("A")

        assert engine.game_session.turn_count == 1
        assert engine.game_session.local_story_active is False
        assert engine.game_session.turn_history[-1]["delta"]["meta"]["choice_category"] in {
            "稳妥",
            "机遇",
            "风险",
            "气运",
        }
        assert "local_story_fallback" not in engine.game_session.turn_history[-1]["delta"]["meta"]
        assert len(engine.game_session.last_choices) == 4
        assert not any("补齐下一步选择" in msg or "因果结算" in msg for msg in infos)

    def test_narrative_claim_without_structured_delta_settles_rule_turn(self, monkeypatch) -> None:
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
        engine = GameEngine()
        engine.game_session.game_started = True
        engine.game_session.inventory = []
        engine.game_session.techniques = []
        infos: list[str] = []
        narratives: list[tuple[str, int]] = []
        engine.on_info = lambda msg: infos.append(msg)
        engine.on_narrative = lambda text, turn: narratives.append((text, turn))

        def runner(agent_name, user_input, session, **kw):
            if agent_name == "narrator":
                return {
                    "narrative": "你获得一枚清灵丹，又习得云水诀。",
                    "state_delta": {"character": {"attributes": {"willpower": 1}}},
                    "choices": ["查看丹药", "演练功法", "拜谢师兄", "顺着命数静候"],
                    "llm_error": "",
                }
            if agent_name == "judge":
                return _canned_judge()
            return {}

        with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=runner):
            engine.handle_action("接受师兄指点")

        assert engine.game_session.inventory == []
        assert engine.game_session.techniques == []
        assert not hasattr(engine.game_session, "mp")
        assert narratives
        assert "清灵丹" not in narratives[-1][0]
        assert "云水诀" not in narratives[-1][0]
        assert not any("因果结算" in msg or "narrative/state mismatch" in msg for msg in infos)
        assert not any("状态栏为准" in msg or "state_delta" in msg for msg in infos)
        assert all(
            "清灵丹" not in choice and "云水诀" not in choice
            for choice in engine.game_session.last_choices
        )
        assert not any(
            engine._parse_breakthrough_action(choice) for choice in engine.game_session.last_choices
        )
        assert engine.game_session.turn_count == 1
        assert engine.game_session.turn_history[-1]["turn"] == 1
        assert engine.game_session.turn_history[-1]["narrative"]
        assert "清灵丹" not in engine.game_session.turn_history[-1]["narrative"]
        assert "云水诀" not in engine.game_session.turn_history[-1]["narrative"]
        assert "elapsed_years" in engine.game_session.turn_history[-1]["delta"]["meta"]

    def test_minor_narrative_item_claim_does_not_force_inventory_entry(self, monkeypatch) -> None:
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
        engine = GameEngine()
        engine.game_session.game_started = True
        engine.game_session.inventory = []
        narratives: list[tuple[str, int]] = []
        infos: list[str] = []
        engine.on_narrative = lambda text, turn: narratives.append((text, turn))
        engine.on_info = lambda msg: infos.append(msg)

        def runner(agent_name, user_input, session, **kw):
            if agent_name == "narrator":
                return {
                    "narrative": "你在山道旁拾得一枚残破木符，只觉其纹路有些古怪。",
                    "state_delta": {"character": {"attributes": {"luck": 1}}},
                    "choices": ["收好木符继续前行", "询问路过弟子", "绕去后山查看", "顺着天命静候"],
                    "llm_error": "",
                }
            if agent_name == "judge":
                return _canned_judge()
            return {}

        with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=runner):
            engine.handle_action("沿山道看看")

        assert engine.game_session.inventory == []
        assert narratives and "残破木符" in narratives[-1][0]
        assert not any("基础规则结算" in msg or "状态栏为准" in msg for msg in infos)

    def test_notice_board_narrative_keeps_non_reward_text_but_ignores_model_location(
        self, monkeypatch
    ) -> None:
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
        monkeypatch.setattr("agens_novel.game.realm.random.random", lambda: 0.0)
        monkeypatch.setattr(
            "agens_novel.engine.turn_rules.select_chronicle_event",
            lambda *_args, **_kwargs: {
                "id": "notice-board",
                "event_type": "稳妥",
                "lore": "悬赏榜公布了新一批外门差事。",
                "stage_goal": "核对可接取的外门差事",
                "allowed_delta_types": ["location", "current_scene"],
            },
        )
        engine = GameEngine()
        engine.game_session.game_started = True
        infos: list[str] = []
        narratives: list[tuple[str, int]] = []
        engine.on_info = lambda msg: infos.append(msg)
        engine.on_narrative = lambda text, turn: narratives.append((text, turn))

        board_text = (
            "你步入悬赏榜广场，墙上贴满各色任务。采集凝露草十株，报酬二十块下品灵石，"
            "建议练气三层以上接取；灵田驱鼠任务练气一层即可。你只是阅读条目，尚未登记。"
        )

        def runner(agent_name, user_input, session, **kw):
            if agent_name == "narrator":
                return {
                    "narrative": board_text,
                    "state_delta": {
                        "world": {
                            "current_scene": "悬赏榜前广场，一面青石墙壁上贴满各色悬赏",
                            "location": "青云小传宗·悬赏榜广场",
                        }
                    },
                    "choices": [
                        "先整理榜上稳妥委托",
                        "接下采集凝露草的任务",
                        "接下驱赶噬灵鼠的任务",
                        "暂且观望榜单变化",
                    ],
                    "llm_error": "",
                }
            if agent_name == "judge":
                return _canned_judge()
            return {}

        with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=runner):
            engine.handle_action("去悬赏榜看看")

        assert narratives and narratives[-1][0] == board_text
        assert engine.game_session.location == ""
        assert engine.game_session.current_scene == ""
        assert engine.game_session.active_quests == []
        assert engine.game_session.turn_history[-1]["delta"]["meta"]["model_state_update_ignored"]
        assert not any("状态栏为准" in msg for msg in infos)

    def test_model_structured_delta_cannot_grant_inventory_skills_quests_or_map(
        self, monkeypatch
    ) -> None:
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
        engine = GameEngine()
        engine.game_session.game_started = True

        def runner(agent_name, user_input, session, **kw):
            if agent_name == "narrator":
                return {
                    "narrative": "你获得清灵丹，习得云水诀，发现后山药谷，并接取采药任务。",
                    "state_delta": {
                        "character": {
                            "inventory_add": [{"name": "清灵丹", "quantity": 1, "type": "丹药"}],
                            "techniques_add": [{"name": "云水诀", "level": 1, "type": "术法"}],
                        },
                        "world": {
                            "discovered_add": ["后山药谷"],
                            "active_quests_add": [{"name": "采药任务", "status": "active"}],
                        },
                    },
                    "choices": ["去药谷", "修习云水诀", "查看丹药", "顺着命数静候"],
                    "llm_error": "",
                }
            if agent_name == "judge":
                return _canned_judge()
            return {}

        event = {
            "id": "reward-test",
            "event_type": "reward",
            "lore": "师门按功授予修行资源。",
            "stage_goal": "验证授权奖励完整落账",
            "allowed_delta_types": [
                "inventory_add",
                "techniques_add",
                "discovered_add",
                "active_quests_add",
            ],
            "choice_hints": [],
        }
        with (
            patch("agens_novel.engine.turn_rules.select_chronicle_event", return_value=event),
            patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=runner),
        ):
            engine.handle_action("接受师兄赠丹并请教功法")

        assert engine.game_session.inventory == []
        assert engine.game_session.techniques == []
        assert engine.game_session.discovered_locations == []
        assert engine.game_session.active_quests == []
        assert engine.game_session.turn_history[-1]["delta"]["meta"]["model_state_update_ignored"]

    def test_judge_exception_fallback(self, monkeypatch) -> None:
        """Judge crashes — default to NOT approving (safe default)."""
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
        engine = GameEngine()

        with _patch_turn_runner():
            engine.new_game("许满")
        engine.game_session.last_choices = [
            "留在山门吐纳",
            "询问接引弟子",
            "强闯禁地",
            "随缘听天命",
        ]

        call_log: list[str] = []
        decisions: list[tuple[str, str]] = []
        engine.on_model_failure_choice = lambda source, reason: (
            decisions.append((source, reason)) or "end"
        )

        def selective_runner(agent_name, user_input, session, **kw):
            call_log.append(agent_name)
            if agent_name == "narrator":
                return {
                    "narrative": "你得了一笔不该存在的秘宝。",
                    "state_delta": {"character": {"gold": "+77"}},
                    "choices": ["继续吐纳", "请教师兄", "观察灵气流向", "顺着天命静候"],
                    "output_path": "",
                    "audit_path": "",
                    "finished_at": "",
                    "llm_error": "",
                }
            if agent_name == "judge":
                raise ConnectionError("Judge down")
            return {}

        with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=selective_runner):
            engine.handle_action("C")

        assert engine.game_session.turn_count == 1
        # Judge exception -> model delta is not applied; v5 rule settlement may still advance the turn.
        assert not hasattr(engine.game_session, "gold")
        assert decisions == []

    def test_judge_rejects(self, monkeypatch) -> None:
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
        engine = GameEngine()

        with _patch_turn_runner():
            engine.new_game("许满")
        engine.game_session.last_choices = [
            "留在山门吐纳",
            "询问接引弟子",
            "强闯禁地",
            "随缘听天命",
        ]

        def selective_runner(agent_name, user_input, session, **kw):
            if agent_name == "narrator":
                return {
                    "narrative": "你强闯禁地边缘，被阴风擦过经脉。",
                    "state_delta": {"character": {"status_effects_add": ["阴风侵体"]}},
                    "choices": ["返回山门", "请教师兄", "继续观察", "随缘听天命"],
                    "output_path": "",
                    "audit_path": "",
                    "finished_at": "",
                    "llm_error": "",
                }
            if agent_name == "judge":
                return {
                    "approved": False,
                    "corrected_delta": {"character": {"status_effects_add": ["轻伤"]}},
                    "judgment_note": "状态变更过大",
                    "review_score": 3,
                    "output_path": "",
                    "audit_path": "",
                    "finished_at": "",
                    "llm_error": "",
                }
            return {}

        with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=selective_runner):
            engine.handle_action("C")

        assert "轻伤" not in engine.game_session.status_effects
        assert "阴风侵体" not in engine.game_session.status_effects
        assert engine.game_session.turn_history[-1]["delta"]["meta"]["model_state_update_ignored"]

    def test_model_world_delta_is_ignored_without_judge(self, monkeypatch) -> None:
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
        engine = GameEngine()

        with _patch_turn_runner():
            engine.new_game("许满")
        engine.game_session.last_choices = [
            "留在山门吐纳",
            "询问接引弟子",
            "强闯内门",
            "随缘听天命",
        ]

        narratives: list[tuple[str, int]] = []
        infos: list[str] = []
        engine.on_narrative = lambda text, turn: narratives.append((text, turn))
        engine.on_info = lambda msg: infos.append(msg)

        def selective_runner(agent_name, user_input, session, **kw):
            if agent_name == "narrator":
                return {
                    "narrative": "虚空之中，混沌未开。",
                    "state_delta": {"world": {"current_scene": "混沌虚空"}},
                    "choices": ["退回山门", "询问执事", "静观其变", "顺着天命静候"],
                    "llm_error": "",
                }
            return {}

        with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=selective_runner):
            engine.handle_action("修炼")

        assert narratives
        assert engine.game_session.current_scene != "混沌虚空"
        assert not any("因果结算" in msg or "narrative/state mismatch" in msg for msg in infos)
        assert engine.game_session.current_scene == "晨雾中的青云山外门"
        assert engine.game_session.turn_count == 1

    def test_judge_reject_without_correction_keeps_model_choices(self, monkeypatch) -> None:
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
        engine = GameEngine()

        with _patch_turn_runner():
            engine.new_game("许满")

        infos: list[str] = []
        engine.on_info = lambda msg: infos.append(msg)

        def selective_runner(agent_name, user_input, session, **kw):
            if agent_name == "narrator":
                return {
                    "narrative": "你试图强闯内门。",
                    "state_delta": {"character": {"attributes": {"willpower": 1}}},
                    "choices": ["向执事解释来意", "退回山门等候", "寻找外门任务", "顺着天命静候"],
                    "llm_error": "",
                }
            if agent_name == "judge":
                return {
                    "approved": False,
                    "corrected_delta": {},
                    "judgment_note": "越权强闯不成立",
                    "review_score": 0,
                    "llm_error": "",
                }
            return {}

        with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=selective_runner):
            engine.handle_action("C")

        assert engine.game_session.last_choices == [
            "向执事解释来意",
            "退回山门等候",
            "寻找外门任务",
            "顺着天命静候",
        ]
        assert not any("天道紊乱" in msg for msg in infos)
        assert engine.game_session.current_scene == "晨雾中的青云山外门"
        assert engine.game_session.turn_count == 1

    def test_action_delta_filters_identity_and_reset_scene(self, monkeypatch) -> None:
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
        engine = GameEngine()
        monkeypatch.setattr(engine.realm_system, "try_advance_stage", lambda session: None)

        with _patch_turn_runner():
            engine.new_game("许满")

        def selective_runner(agent_name, user_input, session, **kw):
            if agent_name == "narrator":
                return {
                    "narrative": "你仍在山门前吐纳。",
                    "state_delta": {
                        "character": {
                            "realm": "凡人",
                            "realm_stage": 1,
                            "spirit_root": "undetermined",
                            "inventory": [],
                            "techniques": [],
                            "experience": "+10",
                        },
                        "world": {"current_scene": "混沌虚空", "day_count": 2},
                    },
                    "choices": ["继续吐纳", "请教师兄", "观察灵气流向"],
                    "llm_error": "",
                }
            if agent_name == "judge":
                return _canned_judge()
            return {}

        with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=selective_runner):
            engine.handle_action("修炼")

        s = engine.game_session
        assert s.realm == "练气"
        assert s.realm_stage == 1
        assert s.spirit_root == "火木双灵根"
        assert s.inventory == [{"name": "粗布道袍", "quantity": 1, "type": "防具"}]
        assert s.techniques == [{"name": "基础吐纳术", "level": 1, "type": "内功"}]
        assert s.current_scene == "晨雾中的青云山外门"
        assert s.day_count == 1
        assert not hasattr(s, "experience")

    def test_start_from_profile_seeds_opening_chat_history(self, monkeypatch, tmp_path) -> None:
        from agens_novel import paths

        monkeypatch.setattr(paths, "SAVE_DIR", tmp_path)
        monkeypatch.delenv("AGNES_API_KEY", raising=False)
        engine = GameEngine()
        engine.start_from_profile(
            {
                "char_name": "许满",
                "talent": "剑心微明",
                "spirit_root": "火灵根",
                "family_background": "寒门",
            }
        )

        assert engine.pending_model_failure() is not None
        assert engine.game_session.chat_history == []

    def test_typed_combat_action_is_none_in_game_mode(self, monkeypatch, tmp_path) -> None:
        """Game-mode v5: combat is event-based; there is no typed combat action.
        A combat-flavored phrase routes to the narrator like any other action."""
        from agens_novel import paths

        monkeypatch.setattr(paths, "SAVE_DIR", tmp_path)
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")

        engine = GameEngine()
        with _patch_turn_runner():
            engine.start_from_profile(
                {
                    "char_name": "许满",
                    "techniques": [{"name": "基础吐纳术", "level": 1, "type": "内功"}],
                }
            )

        assert not hasattr(engine, "_parse_typed_combat_action")
        assert not hasattr(engine.game_session, "combat")

    def test_narrator_combat_delta_is_dropped_in_game_mode(self, monkeypatch, tmp_path) -> None:
        """Game-mode v5: a structured combat delta in the narrator output is
        dropped (combat is event-based); no structured combat is initialized."""
        from agens_novel import paths

        monkeypatch.setattr(paths, "SAVE_DIR", tmp_path)
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")

        engine = GameEngine()
        with _patch_turn_runner():
            engine.start_from_profile({"char_name": "许满"})

        def selective_runner(agent_name, user_input, session, **kw):
            if agent_name == "narrator":
                return {
                    "narrative": "山雾里冲出一头妖兽。",
                    "state_delta": {
                        "character": {
                            "combat": {
                                "enemy": {
                                    "name": "山魈",
                                    "hp": 60,
                                    "hp_max": 60,
                                    "realm": "练气",
                                }
                            }
                        }
                    },
                    "choices": ["观察妖兽", "后退防备", "呼喊同门"],
                    "llm_error": "",
                }
            if agent_name == "judge":
                return _canned_judge()
            return {}

        with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=selective_runner):
            engine.handle_action("查看山门外的异响")

        # Game-mode v5: structured combat delta is dropped; no combat state kept.
        assert not hasattr(engine.game_session, "combat")
        assert "combat" not in engine.game_session.to_save_dict()["character"]
