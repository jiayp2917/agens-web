"""Gap-locking tests for the 20-turn playable vertical slice.

These tests pin spec-intended behavior for known gameplay gaps from the
2026-06-29 playable roadmap. Strict xfail tests are real gaps: an XPASS means
that the implementation changed and the marker should be reviewed.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from agens_novel.engine.game_engine import GameEngine
from agens_novel.session.game_session import GameSession


def _canned_world_builder() -> dict[str, Any]:
    return {
        "generated_data": {
            "character": {
                "name": "Xu Man",
                "realm": "练气",
                "realm_stage": 1,
                "spirit_root": "火木双灵根",
                "spirit_root_grade": "地",
                "breakthrough_flags": [],
                "techniques": [{"name": "基础吐纳术", "level": 1, "type": "内功"}],
                "inventory": [{"name": "粗布道袍", "quantity": 1, "type": "防具"}],
                "status_effects": [],
                "lifespan": 100,
            },
            "world": {
                "current_scene": "晨雾中的青云山外门",
                "location": "青云山外门",
                "region": "东荒",
                "npcs_present": [],
                "active_quests": [],
                "discovered_locations": ["青云山外门"],
                "lore_facts": [],
                "day_count": 1,
            },
            "opening_narrative": "天道初开。",
            "choices": ["留在山门吐纳", "询问接引弟子", "观察灵气流向"],
        },
        "world_description": "",
        "opening_narrative": "",
        "output_path": "",
        "audit_path": "",
        "finished_at": "",
        "llm_error": "",
    }


def _canned_judge() -> dict[str, Any]:
    return {
        "approved": True,
        "corrected_delta": {},
        "judgment_note": "ok",
        "review_score": 8,
        "output_path": "",
        "audit_path": "",
        "finished_at": "",
        "llm_error": "",
    }


def _patch_turn_runner(call_log: list | None = None) -> Any:
    if call_log is None:
        call_log = []

    def fake_run_turn_sync(agent_name: str, user_input: str, session: GameSession, **kwargs) -> dict:
        call_log.append(agent_name)
        if agent_name == "narrator":
            return {
                "narrative": "你静坐吐纳，灵气缓缓涌入。",
                "state_delta": {"character": {"attributes": {"willpower": 1}}},
                "choices": ["继续吐纳", "请教师兄", "观察灵气流向"],
                "output_path": "",
                "audit_path": "",
                "finished_at": "",
                "llm_error": "",
            }
        if agent_name == "judge":
            return _canned_judge()
        if agent_name == "world_builder":
            return _canned_world_builder()
        return {}

    return patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=fake_run_turn_sync)


class TestPlayableGapLocks:
    @pytest.mark.xfail(
        strict=True,
        reason="P1-1a: silent inventory_add without narrative still persists today.",
    )
    def test_T1_silent_inventory_add_without_narrative_does_not_persist(self, monkeypatch) -> None:
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
        engine = GameEngine()
        engine.game_session.game_started = True
        engine.game_session.inventory = []

        def runner(agent_name, user_input, session, **kw):
            if agent_name == "narrator":
                return {
                    "narrative": "",
                    "state_delta": {
                        "character": {
                            "inventory_add": [{"name": "幽灵丹", "quantity": 1, "type": "丹药"}],
                        },
                    },
                    "choices": ["继续吐纳", "请教师兄", "观察灵气流向"],
                    "llm_error": "",
                }
            if agent_name == "judge":
                return _canned_judge()
            return {}

        with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=runner):
            engine.handle_action("修炼")

        assert not any(item.get("name") == "幽灵丹" for item in engine.game_session.inventory)

    @pytest.mark.xfail(
        strict=True,
        reason="P1-1b: local_story self-loop nodes still replay identical narrative.",
    )
    def test_T2_local_story_cultivation_self_loop_does_not_repeat_narrative(self, monkeypatch) -> None:
        from agens_novel.engine.local_story import advance_local_story, start_local_story

        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
        engine = GameEngine()
        engine.game_session.game_started = True

        session = engine.game_session
        start_local_story(session)
        advance_local_story(session, "按山门规矩登记入门，先求一个稳妥落脚处")
        advance_local_story(session, "按执事吩咐完成杂务，熟悉宗门规矩")
        narratives = [
            advance_local_story(session, "继续吐纳一夜，稳固根骨与心性").narrative
            for _ in range(3)
        ]
        assert len(set(narratives)) > 1

    @pytest.mark.xfail(
        strict=True,
        reason="P1-1b: invalid local_story action still consumes a turn today.",
    )
    def test_T3_local_story_no_match_does_not_consume_turn(self, monkeypatch) -> None:
        from agens_novel.engine.local_story import start_local_story

        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
        engine = GameEngine()
        engine.game_session.game_started = True
        start_local_story(engine.game_session)

        before = engine.game_session.turn_count
        engine.handle_action("unmatched-action-zzz123")
        assert engine.game_session.turn_count == before

    @pytest.mark.xfail(
        strict=True,
        reason="P1-1c: eligible breakthrough still does not append a settled turn.",
    )
    def test_T4_eligible_breakthrough_advances_turn_count_and_history(self, monkeypatch) -> None:
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
        engine = GameEngine()
        with _patch_turn_runner():
            engine.new_game("Xu Man")
        engine.game_session.realm = "练气"
        engine.game_session.realm_stage = 9
        engine.game_session.breakthrough_flags = ["foundation_aid"]

        turn_before = engine.game_session.turn_count
        history_before = len(engine.game_session.turn_history)

        with _patch_turn_runner():
            with patch("agens_novel.game.realm.random.random", return_value=0.001):
                engine.attempt_breakthrough()

        assert engine.game_session.realm == "筑基"
        assert engine.game_session.turn_count == turn_before + 1
        assert len(engine.game_session.turn_history) == history_before + 1

    def test_T5_settle_turn_marks_game_over_on_lifespan_exhausted(self, monkeypatch) -> None:
        from agens_novel.engine.turn_rules import settle_turn

        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
        engine = GameEngine()
        session = engine.game_session
        session.realm = "练气"
        session.age = 99
        session.lifespan = 100
        session.difficulty = "普通"

        delta = settle_turn("闭关修炼", session)

        assert delta["meta"]["game_over"] is True
        assert delta["meta"]["game_over_reason"] == "寿元耗尽，坐化而去。"

    def test_T6_start_profile_rejects_attribute_pool_not_summing_to_30(self, monkeypatch, tmp_path) -> None:
        from agens_novel import paths

        monkeypatch.setattr(paths, "SAVE_DIR", tmp_path)
        monkeypatch.delenv("AGNES_API_KEY", raising=False)
        engine = GameEngine()
        bad_attrs = {
            "physique": 5,
            "soul": 5,
            "luck": 5,
            "comprehension": 5,
            "willpower": 5,
            "root_bone": 4,
        }
        with pytest.raises(ValueError, match="sum to 30"):
            engine.start_from_profile({"char_name": "测试", "attributes": bad_attrs})

    def test_T7_start_profile_accepts_valid_30_point_pool(self, monkeypatch, tmp_path) -> None:
        from agens_novel import paths

        monkeypatch.setattr(paths, "SAVE_DIR", tmp_path)
        engine = GameEngine()
        attrs = {
            "physique": 5,
            "soul": 5,
            "luck": 5,
            "comprehension": 5,
            "willpower": 5,
            "root_bone": 5,
        }

        engine.start_from_profile({"char_name": "测试", "attributes": attrs})

        assert engine.game_session.attributes == attrs
