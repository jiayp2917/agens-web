"""Visible narrative and contract quality guards."""

from __future__ import annotations

from unittest.mock import patch

from agens_novel.engine.action_delta_policy import (
    merge_rule_delta,
    validate_narrative_delta_consistency,
)
from agens_novel.engine.choices import clean_visible_text, fallback_choices
from agens_novel.engine.game_engine import GameEngine
from agens_novel.engine.model_fallback_policy import (
    MODEL_CONTRACT_UNAVAILABLE_NOTICE,
    public_model_failure_notice,
)
from agens_novel.session.game_session import GameSession
from tests.unit.engine.quality_test_support import rule_outcome as _rule_outcome


def test_fallback_choices_vary_by_play_phase_without_changing_d_semantics() -> None:
    session = GameSession(location="青云山门")

    session.turn_count = 0
    early = fallback_choices(session)

    session.turn_count = 5
    middle = fallback_choices(session)

    session.turn_count = 12
    later = fallback_choices(session)

    assert early[:3] != middle[:3]
    assert middle[:3] != later[:3]
    assert early[3] == middle[3] == later[3]
    assert "气运" in early[3]


def test_model_contract_failure_notice_is_public_text() -> None:
    for reason in (
        "模型已返回叙事，但状态更新格式不完整。",
        "模型输出缺少叙事正文。",
        "模型已返回叙事，但未返回可用 A/B/C/D 选项。",
        "模型已返回叙事，但未返回恰好 4 个 A/B/C/D 选项。",
    ):
        text = public_model_failure_notice(reason)
        assert text == MODEL_CONTRACT_UNAVAILABLE_NOTICE
        assert "模型已返回" not in text
        assert "状态更新格式不完整" not in text
        assert "缺少叙事正文" not in text


def test_clean_visible_text_keeps_legitimate_quoted_lore_list() -> None:
    text = "墙上刻着“青木长生诀”、“庚金护身符”、“寒潭通行令”，皆为旧年传闻。"

    cleaned = clean_visible_text(text, allow_structured=False)

    assert "青木长生诀" in cleaned
    assert "庚金护身符" in cleaned
    assert "寒潭通行令" in cleaned


def test_authoritative_injury_claim_requires_structured_status() -> None:
    ok, reason = validate_narrative_delta_consistency(
        "你中了寒毒，伤势缠身。",
        {"character": {"attributes": {"willpower": 1}}},
    )

    assert ok is False
    assert "narrative/state mismatch" in reason

    ok, reason = validate_narrative_delta_consistency(
        "你中了寒毒，伤势缠身。",
        {"character": {"status_effects_add": ["寒毒"]}},
    )

    assert ok is True
    assert reason == ""


def test_malformed_authoritative_delta_does_not_count_as_settled_state() -> None:
    cases = [
        ("你中了寒毒，伤势缠身。", {"character": {"status_effects_add": "寒毒"}}),
        ("你中了寒毒，伤势缠身。", {"character": {"status_effects_add": []}}),
        ("你获封青云外门魁首称号。", {"world": {"lore_add": "获封青云外门魁首"}}),
        ("你获封青云外门魁首称号。", {"world": {"lore_add": []}}),
        ("你与陈师兄结为盟友。", {"world": {"npcs_present_add": {"name": "陈师兄"}}}),
        ("你与陈师兄结为盟友。", {"world": {"npcs_present_add": []}}),
        ("你服下延寿丹，寿元增加二十年。", {"character": {"lifespan": "+abc"}}),
    ]

    for narrative, delta in cases:
        ok, reason = validate_narrative_delta_consistency(narrative, delta)
        assert ok is False, narrative
        assert "narrative/state mismatch" in reason


def test_authoritative_lifespan_claim_requires_structured_lifespan_delta() -> None:
    ok, reason = validate_narrative_delta_consistency(
        "你服下延寿丹，寿元增加二十年。",
        {"character": {"attributes": {"physique": 1}}},
    )

    assert ok is False
    assert "narrative/state mismatch" in reason

    ok, reason = validate_narrative_delta_consistency(
        "你服下延寿丹，寿元增加二十年。",
        {"character": {"lifespan": "+20"}},
    )

    assert ok is True
    assert reason == ""


def test_ordinary_time_passage_does_not_force_lifespan_cap_delta() -> None:
    ok, reason = validate_narrative_delta_consistency(
        "三年闭关转瞬即逝，寿元耗去三年，你的根基略有进境。",
        {"character": {"attributes": {"willpower": 1}}},
    )

    assert ok is True
    assert reason == ""


def test_relationship_title_and_karma_claims_need_authoritative_record() -> None:
    cases = [
        ("你获封青云外门魁首称号。", {"world": {"current_scene": "演武场"}}),
        ("你获封青云外门魁首称号，心中只想继续修行。", {"world": {"current_scene": "演武场"}}),
        ("你与陈师兄结为盟友。", {"character": {"attributes": {"luck": 1}}}),
        ("旧日因果缠身，你的气运开始折损。", {"world": {"current_scene": "山门"}}),
    ]

    for narrative, delta in cases:
        ok, reason = validate_narrative_delta_consistency(narrative, delta)
        assert ok is False, narrative
        assert "narrative/state mismatch" in reason

    passing = [
        ("你获封青云外门魁首称号。", {"character": {"title_add": ["青云外门魁首"]}}),
        (
            "你与陈师兄结为盟友。",
            {"character": {"relationship_add": [{"name": "陈师兄", "relation": "盟友"}]}},
        ),
        ("旧日因果缠身，你的气运开始折损。", {"character": {"status_effects_add": ["因果缠身"]}}),
    ]

    for narrative, delta in passing:
        ok, reason = validate_narrative_delta_consistency(narrative, delta)
        assert ok is True, narrative
        assert reason == ""


def test_title_claim_must_match_final_rule_owned_title() -> None:
    merged = merge_rule_delta(
        {"character": {"title_add": ["青云外门魁首"]}},
        {"character": {"title_add": ["外门勤修弟子"]}},
    )

    ok, reason = validate_narrative_delta_consistency(
        "宗门记功，验真者获封青云外门魁首称号。",
        merged,
    )

    assert ok is False
    assert "narrative/state mismatch" in reason

    ok, reason = validate_narrative_delta_consistency(
        "宗门记功，验真者获封外门勤修弟子称号。",
        merged,
    )

    assert ok is True
    assert reason == ""


def test_chronicle_rumor_desire_and_condition_do_not_force_authoritative_delta() -> None:
    harmless = [
        "传闻外宗弟子曾经中了寒毒，后来远走北地。",
        "古籍记载延寿丹可增加寿元，但你只是读到此事。",
        "你得知前任掌门护山真人称号只是旧闻。",
        "你想成为内门弟子，却尚未拜入任何师门。",
        "若能与陈师兄结盟，日后或许能少走弯路。",
        "坊间传说气运改变会引来因果，但此刻只是闲谈。",
    ]

    for narrative in harmless:
        ok, reason = validate_narrative_delta_consistency(
            narrative,
            {"character": {"attributes": {"willpower": 1}}},
        )
        assert ok is True, narrative
        assert reason == ""


def test_harmless_chronicle_claim_is_not_suppressed_in_turn_flow(monkeypatch) -> None:
    monkeypatch.setenv("AGNES_API_KEY", "test-model-key")
    engine = GameEngine()
    engine.game_session.game_started = True
    narratives: list[tuple[str, int]] = []
    infos: list[str] = []
    engine.on_narrative = lambda text, turn: narratives.append((text, turn))
    engine.on_info = lambda msg: infos.append(msg)

    narrative = "古籍记载延寿丹可增加寿元，但你只是读到此事，并未得到丹药。"

    def runner(agent_name, user_input, session, **kw):
        if agent_name == "narrator":
            return {
                "narrative": narrative,
                "state_delta": {"character": {"attributes": {"comprehension": 1}}},
                "choices": ["继续翻阅古籍", "请教师兄注解", "前往藏书楼深处", "随缘抽取残卷"],
                "llm_error": "",
            }
        if agent_name == "judge":
            return {"approved": True, "corrected_delta": {}, "judgment_note": "", "llm_error": ""}
        return {}

    with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=runner):
        engine.handle_action("阅读藏书")

    assert narratives and narratives[-1][0] == narrative
    assert not any("基础规则结算" in msg for msg in infos)
    assert engine.game_session.turn_history[-1]["narrative"] == narrative


def test_json_only_narrator_output_creates_pending_failure(monkeypatch) -> None:
    monkeypatch.setenv("AGNES_API_KEY", "test-model-key")
    engine = GameEngine()
    engine.game_session.game_started = True
    engine.game_session.last_choices = ["稳妥修行", "拜访同门", "探查禁地", "随缘而行"]

    def runner(agent_name, user_input, session, **kw):
        if agent_name == "narrator":
            return {
                "narrative": "",
                "state_delta": {
                    "character": {},
                    "world": {"lore_add": ["模型只给结构化见闻"]},
                    "meta": {},
                },
                "choices": ["继续稳修", "打听消息", "探查边缘", "随缘行事"],
                "llm_error": "",
            }
        return {"approved": True, "corrected_delta": {}, "judgment_note": "", "llm_error": ""}

    with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=runner):
        engine.handle_action("A")

    assert engine.game_session.local_story_active is False
    assert engine.game_session.turn_count == 0
    assert engine.game_session.turn_history == []
    assert engine.pending_model_failure() is not None


def test_explicit_local_story_resolution_applies_authoritative_rule_event(monkeypatch) -> None:
    monkeypatch.setenv("AGNES_API_KEY", "test-model-key")
    engine = GameEngine()
    engine.game_session.game_started = True
    engine.game_session.last_choices = ["稳妥修行", "拜访同门", "探查禁地", "随缘而行"]
    rule_delta = {
        "character": {"age": "+3"},
        "world": {"lore_add": ["青岚谷外门重开药圃账册，验真者被列入新差事。"]},
        "meta": {
            "elapsed_years": 3,
            "choice_category": "稳妥",
            "event_lore": "青岚谷外门重开药圃账册，验真者被列入新差事。",
            "stage_goal": "推进药圃差事",
        },
    }

    def runner(agent_name, user_input, session, **kw):
        if agent_name == "narrator":
            return {"narrative": "", "state_delta": {}, "choices": [], "llm_error": ""}
        return {"approved": True, "corrected_delta": {}, "judgment_note": "", "llm_error": ""}

    with patch("agens_novel.engine.turn_flow.settle_turn_outcome", return_value=_rule_outcome(rule_delta)):
        with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=runner):
            engine.handle_action("A")
            assert engine.resolve_pending_model_failure("use_local_story") is True

    last_turn = engine.game_session.turn_history[-1]
    assert last_turn["delta"]["meta"]["local_story_fallback"] is True
    assert last_turn["delta"]["meta"]["elapsed_years"] == 3
    assert "药圃账册" in last_turn["narrative"]
    assert "岁月流转" in last_turn["narrative"]
