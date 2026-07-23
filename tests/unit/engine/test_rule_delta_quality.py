"""Rule-owned delta merge and history quality guards."""

from __future__ import annotations

from unittest.mock import patch

from agens_novel.engine.action_delta_policy import (
    enforce_event_delta_policy,
    merge_rule_delta,
)
from agens_novel.engine.game_engine import GameEngine
from agens_novel.engine.turn_rules import settle_turn
from agens_novel.session.game_session import GameSession
from tests.unit.engine.quality_test_support import rule_outcome as _rule_outcome


def test_merit_event_grants_rule_owned_title() -> None:
    session = GameSession(location="青岚山门", turn_count=8)
    event = {
        "id": "steady-merit-recognition",
        "event_type": "stage",
        "lore": "宗门将勤勉弟子正式记入榜册。",
        "stage_goal": "接受宗门记名",
        "allowed_delta_types": ["lore_add", "title_add"],
    }

    with patch("agens_novel.engine.turn_rules.select_chronicle_event", return_value=event):
        delta = settle_turn("A【稳妥】继续修行", session)

    assert delta["character"]["title_add"] == ["外门勤修弟子"]


def test_event_delta_policy_drops_changes_outside_selected_event_scope() -> None:
    filtered = enforce_event_delta_policy(
        {
            "character": {
                "inventory_add": [{"name": "无依据法器"}],
                "attributes": {"luck": 1},
            },
            "world": {
                "lore_add": ["可保留见闻"],
                "npcs_present_add": [{"name": "无依据人物"}],
            },
            "meta": {"game_over": True},
        },
        {"meta": {"allowed_delta_types": ["attributes", "lifespan", "lore_add"]}},
    )

    assert filtered == {
        "character": {},
        "world": {"lore_add": ["可保留见闻"]},
        "meta": {},
    }


def test_action_delta_sanitizer_drops_model_owned_lifespan() -> None:
    engine = GameEngine()

    sanitized = engine.sanitize_action_delta(
        {"character": {"lifespan": "+50"}, "world": {}, "meta": {}}
    )

    assert "lifespan" not in sanitized["character"]


def test_event_delta_policy_preserves_explicitly_allowed_reward() -> None:
    filtered = enforce_event_delta_policy(
        {"character": {"inventory_add": [{"name": "护身符"}]}},
        {"meta": {"allowed_delta_types": ["inventory_add"]}},
    )

    assert filtered["character"]["inventory_add"] == [{"name": "护身符"}]


def test_event_delta_policy_preserves_relationship_but_not_unapproved_title() -> None:
    filtered = enforce_event_delta_policy(
        {
            "character": {
                "relationship_add": [{"name": "陈师兄", "relation": "盟友"}],
                "title_add": ["外门魁首"],
            }
        },
        {"meta": {"allowed_delta_types": ["relationship_add"]}},
    )

    assert filtered["character"] == {"relationship_add": [{"name": "陈师兄", "relation": "盟友"}]}


def test_rule_world_delta_survives_model_merge() -> None:
    merged = merge_rule_delta(
        {"character": {}, "world": {"lore_add": ["模型见闻"]}, "meta": {}},
        {"world": {"lore_add": ["规则阶段反馈"]}, "meta": {"elapsed_years": 2}},
    )

    assert merged["world"]["lore_add"] == ["模型见闻", "规则阶段反馈"]
    assert merged["meta"]["elapsed_years"] == 2


def test_rule_breakthrough_preparation_survives_model_merge() -> None:
    merged = merge_rule_delta(
        {"character": {}, "world": {}, "meta": {}},
        {
            "character": {"breakthrough_flags_add": ["foundation_aid"]},
            "meta": {"breakthrough_preparation": ["foundation_aid"]},
        },
    )

    assert merged["character"]["breakthrough_flags_add"] == ["foundation_aid"]
    assert merged["meta"]["breakthrough_preparation"] == ["foundation_aid"]


def test_rule_status_effect_removal_survives_model_merge() -> None:
    merged = merge_rule_delta(
        {"character": {"status_effects_add": ["旧伤"]}},
        {"character": {"status_effects_remove": ["走火入魔"]}},
    )

    assert merged["character"]["status_effects_add"] == ["旧伤"]
    assert merged["character"]["status_effects_remove"] == ["走火入魔"]


def test_rule_story_update_overrides_model_story_mutation() -> None:
    merged = merge_rule_delta(
        {"world": {"story_update": {"phase_key": "model-reset"}}},
        {
            "world": {"story_update": {"phase_key": "turning", "progress_turns": 9}},
            "meta": {"story_phase": "转折", "story_goal": "核对旧因"},
        },
    )

    assert merged["world"]["story_update"] == {
        "phase_key": "turning",
        "progress_turns": 9,
    }
    assert merged["meta"]["story_phase"] == "转折"
    assert merged["meta"]["story_goal"] == "核对旧因"


def test_model_cannot_mutate_rule_owned_story_state() -> None:
    engine = GameEngine()

    sanitized = engine.sanitize_action_delta(
        {
            "world": {
                "story_update": {"phase_key": "model-reset"},
                "lore_add": ["普通见闻"],
            }
        }
    )

    assert "story_update" not in sanitized["world"]
    assert sanitized["world"]["lore_add"] == ["普通见闻"]


def test_stage_feedback_is_applied_through_turn_flow(monkeypatch) -> None:
    monkeypatch.setenv("AGNES_API_KEY", "test-model-key")
    engine = GameEngine()
    engine.game_session.game_started = True
    engine.game_session.location = "青岚山门"
    engine.game_session.realm = "筑基"
    engine.game_session.realm_stage = 2
    engine.game_session.turn_count = 3
    engine.game_session.last_choices = ["闭关稳固", "拜访同道", "探查禁地", "随缘而行"]

    def runner(agent_name, user_input, session, **kw):
        if agent_name == "narrator":
            return {
                "narrative": "数年之间，他在山门中稳住根基。",
                "state_delta": {"character": {}, "world": {}, "meta": {}},
                "choices": ["继续闭关", "拜访同道", "探查禁地", "随缘而行"],
                "llm_error": "",
            }
        return {"approved": True, "corrected_delta": {}, "judgment_note": "", "llm_error": ""}

    with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=runner):
        engine.handle_action("A")

    lore = engine.game_session.turn_history[-1]["delta"]["world"]["lore_add"]
    assert lore
    assert lore[-1] in engine.game_session.lore_facts
    assert "筑基2层" not in lore[-1]


def test_turn_history_compaction_keeps_opening_chat_context(monkeypatch) -> None:
    monkeypatch.setenv("AGNES_API_KEY", "test-model-key")
    engine = GameEngine()
    engine.game_session.game_started = True
    engine.game_session.chat_history = [
        {"role": "assistant", "content": "开局设定：青岚界山门初开。"}
    ]
    engine.game_session.last_choices = ["闭关稳固", "拜访同道", "探查禁地", "随缘而行"]

    def runner(agent_name, user_input, session, **kw):
        if agent_name == "narrator":
            return {
                "narrative": f"第{session.turn_count}回合，他按部就班修行。",
                "state_delta": {"character": {}, "world": {}, "meta": {}},
                "choices": ["继续闭关", "拜访同道", "探查禁地", "随缘而行"],
                "llm_error": "",
            }
        return {"approved": True, "corrected_delta": {}, "judgment_note": "", "llm_error": ""}

    with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=runner):
        for _ in range(12):
            engine.handle_action("A")

    assert len(engine.game_session.chat_history) == 20
    assert engine.game_session.chat_history[0]["content"].startswith("开局设定")
    assert any("第12回合" in entry["content"] for entry in engine.game_session.chat_history)
    assert not any(
        entry["content"] == "第1回合，他按部就班修行。"
        for entry in engine.game_session.chat_history[1:]
    )


def test_authoritative_mismatch_is_suppressed_in_turn_flow(monkeypatch) -> None:
    monkeypatch.setenv("AGNES_API_KEY", "test-model-key")
    engine = GameEngine()
    engine.game_session.game_started = True
    narratives: list[tuple[str, int]] = []
    infos: list[str] = []
    engine.on_narrative = lambda text, turn: narratives.append((text, turn))
    engine.on_info = lambda msg: infos.append(msg)

    def runner(agent_name, user_input, session, **kw):
        if agent_name == "narrator":
            return {
                "narrative": "你中了寒毒，伤势缠身，只能暂退一步。",
                "state_delta": {"character": {"attributes": {"willpower": 1}}},
                "choices": ["稳住气息", "寻找解毒线索", "冒险逼毒", "随缘求助"],
                "llm_error": "",
            }
        if agent_name == "judge":
            return {"approved": True, "corrected_delta": {}, "judgment_note": "", "llm_error": ""}
        return {}

    with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=runner):
        engine.handle_action("强行运功逼毒")

    assert not any("因果结算" in msg or "narrative/state mismatch" in msg for msg in infos)
    assert engine.game_session.status_effects == []
    assert all("寒毒" not in text for text, _turn in narratives)
    assert engine.game_session.turn_history[-1]["narrative"]
    assert "narrative/state mismatch" not in engine.game_session.turn_history[-1]["narrative"]


def test_model_only_attribute_claim_is_suppressed_after_sanitization(monkeypatch) -> None:
    monkeypatch.setenv("AGNES_API_KEY", "test-model-key")
    engine = GameEngine()
    engine.game_session.game_started = True
    engine.game_session.attributes["comprehension"] = 5
    narratives: list[tuple[str, int]] = []
    infos: list[str] = []
    engine.on_narrative = lambda text, turn: narratives.append((text, turn))
    engine.on_info = lambda msg: infos.append(msg)

    def runner(agent_name, user_input, session, **kw):
        if agent_name == "narrator":
            return {
                "narrative": "数年参悟后，他的悟性大涨。",
                "state_delta": {"character": {"attributes": {"comprehension": 2}}},
                "choices": ["稳住根基", "请教经义", "冒险试法", "随缘听命"],
                "llm_error": "",
            }
        return {"approved": True, "corrected_delta": {}, "judgment_note": "", "llm_error": ""}

    rule_delta = {
        "character": {"age": "+1"},
        "world": {},
        "meta": {"elapsed_years": 1, "choice_category": "机遇"},
    }

    with patch("agens_novel.engine.turn_flow.settle_turn_outcome", return_value=_rule_outcome(rule_delta)):
        with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=runner):
            engine.handle_action("参悟经义")

    assert not any("因果结算" in msg or "narrative/state mismatch" in msg for msg in infos)
    assert engine.game_session.attributes["comprehension"] == 5
    assert all("悟性大涨" not in text for text, _turn in narratives)
    assert engine.game_session.turn_history[-1]["narrative"]
    assert "narrative/state mismatch" not in engine.game_session.turn_history[-1]["narrative"]


def test_rule_owned_attribute_claim_can_remain_visible(monkeypatch) -> None:
    monkeypatch.setenv("AGNES_API_KEY", "test-model-key")
    engine = GameEngine()
    engine.game_session.game_started = True
    engine.game_session.attributes["comprehension"] = 5
    narratives: list[tuple[str, int]] = []
    engine.on_narrative = lambda text, turn: narratives.append((text, turn))

    def runner(agent_name, user_input, session, **kw):
        if agent_name == "narrator":
            return {
                "narrative": "数年参悟后，他的悟性大涨。",
                "state_delta": {"character": {}, "world": {}, "meta": {}},
                "choices": ["稳住根基", "请教经义", "冒险试法", "随缘听命"],
                "llm_error": "",
            }
        return {"approved": True, "corrected_delta": {}, "judgment_note": "", "llm_error": ""}

    rule_delta = {
        "character": {"age": "+1", "attributes": {"comprehension": 1}},
        "world": {},
        "meta": {"elapsed_years": 1, "choice_category": "机遇"},
    }

    with patch("agens_novel.engine.turn_flow.settle_turn_outcome", return_value=_rule_outcome(rule_delta)):
        with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=runner):
            engine.handle_action("参悟经义")

    assert narratives[-1][0] == "数年参悟后，他的悟性大涨。"
    assert engine.game_session.attributes["comprehension"] == 6
    assert engine.game_session.turn_history[-1]["narrative"] == "数年参悟后，他的悟性大涨。"
