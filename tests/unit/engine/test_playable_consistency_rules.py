from __future__ import annotations

from unittest.mock import patch

from agens_novel.agents.narrator.nodes import _parse_narrator_output
from agens_novel.engine.choices import clean_choice_text, normalize_choices
from agens_novel.engine.game_engine import GameEngine
from agens_novel.engine.render import format_realm, format_status_bar, public_realm_label
from agens_novel.engine.turn_rules import settle_turn
from agens_novel.game.constants import compute_starting_lifespan, format_realm_name
from agens_novel.session.game_session import GameSession


def test_realm_display_uses_layers_only_for_qi_refining() -> None:
    assert format_realm_name("练气", 3) == "练气3层"
    assert format_realm_name("筑基", 2) == "筑基中期"
    assert format_realm_name("金丹", 4) == "金丹圆满"
    assert format_realm_name("飞升", 1) == "飞升"

    session = GameSession(realm="筑基", realm_stage=2)
    assert public_realm_label(session) == "筑基中期"
    assert "筑基中期" in format_status_bar(session)
    assert "筑基2层" not in format_status_bar(session)
    assert "筑基中期" in format_realm(session)


def test_choice_cleanup_handles_array_literals_and_english_terms() -> None:
    assert clean_choice_text("['响应青岚谷招募，换取声望与资源']") == "响应青岚谷招募，换取声望与资源"
    assert clean_choice_text('["实战 prowess 不增"]') == "实战 实战能力 不增"
    assert normalize_choices(["['返回百草坊']"]) == ["返回百草坊"]


def test_narrator_parse_strips_structured_debris_from_visible_text() -> None:
    text = (
        "此人沿山道探查，prowess 稍有精进。\n"
        "```json\n"
        "{\"state_delta\":{\"character\":{},\"world\":{},\"meta\":{}},"
        "\"choices\":[\"整理所得\",\"寻访坊市\",\"深入禁地\",\"随缘听命\"]}\n"
        "```"
    )
    narrative, delta, choices = _parse_narrator_output(text)

    assert "```" not in narrative
    assert "prowess" not in narrative
    assert "实战能力" in narrative
    assert delta == {"character": {}, "world": {}, "meta": {}}
    assert choices == ["整理所得", "寻访坊市", "深入禁地", "随缘听命"]


def test_starting_lifespan_uses_realm_range_and_attributes() -> None:
    weak = compute_starting_lifespan("练气", attributes={"physique": 0, "root_bone": 0})
    strong = compute_starting_lifespan("练气", attributes={"physique": 10, "root_bone": 10})
    assert 80 <= weak <= 120
    assert 80 <= strong <= 120
    assert strong > weak


def test_old_low_qi_refining_turn_adds_aging_pressure() -> None:
    session = GameSession(realm="练气", realm_stage=3, age=70, lifespan=100)
    delta = settle_turn("闭关稳固", session)

    assert delta["character"]["age"].startswith("+")
    assert delta["character"]["lifespan"] == "-8"
    assert delta["character"]["status_effects_add"] == ["气血衰败"]
    session.apply_delta(delta)
    assert session.lifespan == 92
    assert session.remaining_lifespan == session.lifespan - session.age
    assert session.game_over is False


def test_very_old_low_qi_refining_can_die_from_age_pressure() -> None:
    session = GameSession(realm="练气", realm_stage=3, age=89, lifespan=100)
    delta = settle_turn("闭关稳固", session)
    session.apply_delta(delta)

    assert delta["character"]["lifespan"] == "-15"
    assert "病衰" in session.status_effects
    assert session.game_over is True
    assert session.error == "年岁已高，根基未成，病衰坐化。"


def test_breakthrough_failure_does_not_advance_realm_and_blocks_stage_advance(monkeypatch) -> None:
    engine = GameEngine()
    engine.game_session.game_started = True
    engine.game_session.realm = "练气"
    engine.game_session.realm_stage = 9
    engine.game_session.age = 74
    engine.game_session.lifespan = 100
    engine.game_session.breakthrough_flags = ["foundation_aid"]
    engine.game_session.attributes = {"root_bone": 1, "comprehension": 1, "luck": 1}

    def runner(agent_name, user_input, session, **kwargs):
        if agent_name == "narrator":
            return {
                "narrative": "他一度以为自己踏入筑基，实则灵机反噬，修为尽废。",
                "state_delta": {"character": {"realm": "筑基", "realm_stage": 2}},
                "choices": ["疗伤稳固", "寻访丹师", "强行再冲", "听天由命"],
                "llm_error": "",
            }
        if agent_name == "judge":
            return {"approved": True, "corrected_delta": {}, "judgment_note": "", "llm_error": ""}
        return {}

    narratives: list[tuple[str, int]] = []
    engine.on_narrative = lambda text, turn: narratives.append((text, turn))

    with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=runner):
        with patch("agens_novel.game.realm.random.random", return_value=1.0):
            engine.attempt_breakthrough()

    assert engine.game_session.realm == "练气"
    assert engine.game_session.realm_stage == 9
    assert "根基重创" in engine.game_session.status_effects
    assert "修为未复" in engine.game_session.status_effects
    assert engine.realm_system.try_advance_stage(engine.game_session) is None
    assert narratives
    assert "修为尽废" not in narratives[-1][0]


def test_breakthrough_success_suppresses_conflicting_failure_narrative() -> None:
    engine = GameEngine()
    engine.game_session.game_started = True
    engine.game_session.realm = "练气"
    engine.game_session.realm_stage = 9
    engine.game_session.breakthrough_flags = ["foundation_aid"]
    engine.game_session.attributes = {"root_bone": 8, "comprehension": 8, "luck": 8}

    def runner(agent_name, user_input, session, **kwargs):
        if agent_name == "narrator":
            return {
                "narrative": "此人破境未成，灵机反噬，继而走火入魔，生死未卜。",
                "state_delta": {},
                "choices": ["稳固道台", "拜访师门", "查看新境", "随缘听命"],
                "llm_error": "",
            }
        if agent_name == "judge":
            return {"approved": True, "corrected_delta": {}, "judgment_note": "", "llm_error": ""}
        return {}

    narratives: list[tuple[str, int]] = []
    engine.on_narrative = lambda text, turn: narratives.append((text, turn))

    with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=runner):
        with patch("agens_novel.game.realm.random.random", return_value=0.0):
            engine.attempt_breakthrough()

    assert engine.game_session.realm == "筑基"
    assert engine.game_session.realm_stage == 1
    assert engine.game_session.lifespan >= 160
    assert "走火入魔" not in narratives[-1][0]
    assert "破境未成" not in narratives[-1][0]
    assert "灵机反噬" not in narratives[-1][0]
    assert "破境已成" in narratives[-1][0]


def test_breakthrough_success_rewrites_wrong_previous_realm_stage() -> None:
    engine = GameEngine()
    engine.game_session.game_started = True
    engine.game_session.realm = "大乘"
    engine.game_session.realm_stage = 4
    engine.game_session.breakthrough_flags = [
        "foundation_aid",
        "golden_core_aid",
        "nascent_soul_aid",
        "spirit_transformation_aid",
        "unity_law_aid",
        "mahayana_vow_aid",
        "tribulation_preparation",
        "tribulation_elixir",
    ]
    seen_inputs: list[str] = []

    def runner(agent_name, user_input, session, **kwargs):
        if agent_name == "narrator":
            seen_inputs.append(user_input)
            return {
                "narrative": "大乘后期瓶颈轰然破碎，一举踏入渡劫之境。",
                "state_delta": {},
                "choices": ["稳固根基", "拜访同道", "探查异象", "静候天机"],
                "llm_error": "",
            }
        if agent_name == "judge":
            return {"approved": True, "corrected_delta": {}, "judgment_note": "", "llm_error": ""}
        return {}

    narratives: list[tuple[str, int]] = []
    engine.on_narrative = lambda text, turn: narratives.append((text, turn))

    with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=runner):
        with patch("agens_novel.game.realm.random.random", return_value=0.0):
            engine.attempt_breakthrough()

    assert seen_inputs and "从大乘圆满突破至渡劫初期" in seen_inputs[0]
    assert engine.game_session.realm == "渡劫"
    assert engine.game_session.realm_stage == 1
    assert narratives[-1][0] == "破境已成，自大乘圆满踏入渡劫初期。"


def test_breakthrough_failure_suppresses_conflicting_stage_drop_claim() -> None:
    engine = GameEngine()
    engine.game_session.realm = "筑基"
    engine.game_session.realm_stage = 4

    narrative = engine._breakthrough_flow._coerce_breakthrough_narrative(
        "一百一十八载，其强行冲关后走火入魔，修为跌落至筑基初期。",
        "failure",
    )

    assert "筑基初期" not in narrative
    assert narrative == "破境未成，灵机反噬，需先稳住根基再图后续。"


def test_breakthrough_model_delta_cannot_inject_authoritative_character_state() -> None:
    engine = GameEngine()
    engine.game_session.game_started = True
    engine.game_session.realm = "练气"
    engine.game_session.realm_stage = 9
    engine.game_session.breakthrough_flags = ["foundation_aid"]
    engine.game_session.status_effects = ["旧伤"]

    def runner(agent_name, user_input, session, **kwargs):
        if agent_name == "narrator":
            return {
                "narrative": "破境已成，道台初立。",
                "state_delta": {
                    "character": {
                        "attributes": {"luck": 10},
                        "inventory_add": ["天外神丹"],
                        "title_add": ["天命之子"],
                        "relationship_add": [{"name": "天道化身", "relation": "盟友"}],
                        "techniques_add": ["无上仙法"],
                        "status_effects": [{"name": "走火入魔"}],
                        "status_effects_add": ["经脉寸断"],
                        "breakthrough_flags_add": ["ascension_protection"],
                    },
                    "world": {"lore_add": ["天象为此番破境留下记载。"]},
                    "meta": {"status_effect_add": "修为未复"},
                },
                "choices": ["稳固道台", "拜访师门", "查看新境", "随缘听命"],
                "llm_error": "",
            }
        if agent_name == "judge":
            return {"approved": True, "corrected_delta": {}, "judgment_note": "", "llm_error": ""}
        return {}

    with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=runner):
        with patch("agens_novel.game.realm.random.random", return_value=0.0):
            engine.attempt_breakthrough()

    assert engine.game_session.realm == "筑基"
    assert engine.game_session.status_effects == ["旧伤"]
    assert engine.game_session.inventory == []
    assert engine.game_session.titles == []
    assert engine.game_session.relationships == []
    assert engine.game_session.techniques == []
    assert engine.game_session.breakthrough_flags == ["foundation_aid"]
    assert "天象为此番破境留下记载。" in engine.game_session.lore_facts


def test_steady_turn_recovers_breakthrough_blocker_but_preserves_other_injury() -> None:
    session = GameSession(realm="练气", realm_stage=9, age=30, lifespan=100)
    session.status_effects = ["走火入魔", {"name": "旧伤", "severity": "轻"}]

    delta = settle_turn("A【稳妥】疗伤调息，稳住根基", session)

    assert delta["character"]["status_effects_remove"] == ["走火入魔"]
    assert "已解除：走火入魔" in delta["meta"]["turn_summary"]
    session.apply_delta(delta)
    assert session.status_effects == [{"name": "旧伤", "severity": "轻"}]


def test_breakthrough_judge_cannot_flip_rule_failure_to_success() -> None:
    engine = GameEngine()
    engine.game_session.game_started = True
    engine.game_session.realm = "练气"
    engine.game_session.realm_stage = 9
    engine.game_session.age = 74
    engine.game_session.breakthrough_flags = ["foundation_aid"]
    engine.game_session.attributes = {"root_bone": 1, "comprehension": 1, "luck": 1}

    def runner(agent_name, user_input, session, **kwargs):
        if agent_name == "narrator":
            return {
                "narrative": "破境未成，灵机反噬。",
                "state_delta": {},
                "choices": ["疗伤稳固", "寻访丹师", "强行再冲", "听天由命"],
                "llm_error": "",
            }
        if agent_name == "judge":
            return {
                "approved": False,
                "corrected_delta": {
                    "character": {"realm": "筑基", "realm_stage": 1, "lifespan": 200},
                    "meta": {"breakthrough_result": "success", "new_realm": "筑基"},
                },
                "judgment_note": "错误翻案",
                "llm_error": "",
            }
        return {}

    with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=runner):
        with patch("agens_novel.game.realm.random.random", return_value=1.0):
            engine.attempt_breakthrough()

    assert engine.game_session.realm == "练气"
    assert engine.game_session.realm_stage == 9
    assert engine.game_session.turn_history[-1]["delta"]["meta"]["breakthrough_result"] == "failure"


def test_breakthrough_judge_cannot_flip_rule_success_to_failure() -> None:
    engine = GameEngine()
    engine.game_session.game_started = True
    engine.game_session.realm = "练气"
    engine.game_session.realm_stage = 9
    engine.game_session.breakthrough_flags = ["foundation_aid"]
    engine.game_session.attributes = {"root_bone": 8, "comprehension": 8, "luck": 8}

    def runner(agent_name, user_input, session, **kwargs):
        if agent_name == "narrator":
            return {
                "narrative": "破境已成，道台初立。",
                "state_delta": {},
                "choices": ["稳固道台", "拜访师门", "查看新境", "随缘听命"],
                "llm_error": "",
            }
        if agent_name == "judge":
            return {
                "approved": False,
                "corrected_delta": {
                    "character": {"realm": "练气", "realm_stage": 9},
                    "meta": {"breakthrough_result": "failure", "status_effect_add": "走火入魔"},
                },
                "judgment_note": "错误翻案",
                "llm_error": "",
            }
        return {}

    with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=runner):
        with patch("agens_novel.game.realm.random.random", return_value=0.0):
            engine.attempt_breakthrough()

    assert engine.game_session.realm == "筑基"
    assert engine.game_session.realm_stage == 1
    assert engine.game_session.turn_history[-1]["delta"]["meta"]["breakthrough_result"] == "success"


def test_stage_advance_info_uses_public_realm_label_for_higher_realms(monkeypatch) -> None:
    engine = GameEngine()
    engine.game_session.game_started = True
    engine.game_session.realm = "筑基"
    engine.game_session.realm_stage = 1
    engine.game_session.attributes = {"comprehension": 10, "root_bone": 10}
    infos: list[str] = []
    engine.on_info = lambda msg: infos.append(msg)

    with patch("agens_novel.game.realm.random.random", return_value=0.0):
        delta = engine._turn_flow._try_emit_stage_advance()

    assert delta is not None
    assert engine.game_session.realm_stage == 2
    assert any("筑基中期" in msg for msg in infos)
    assert not any("筑基第2层" in msg or "筑基2层" in msg for msg in infos)
