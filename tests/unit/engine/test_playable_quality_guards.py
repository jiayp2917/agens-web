"""Focused gameplay-quality guards for the playable vertical slice."""

from __future__ import annotations

from unittest.mock import patch

from agens_novel.engine.game_engine import GameEngine
from agens_novel.engine.action_delta_policy import validate_narrative_delta_consistency
from agens_novel.engine.choices import fallback_choices
from agens_novel.session.game_session import GameSession


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
        ("你获封青云外门魁首称号。", {"world": {"lore_add": ["获封青云外门魁首"]}}),
        ("你与陈师兄结为盟友。", {"world": {"npcs_present_add": [{"name": "陈师兄", "relation": "盟友"}]}}),
        ("旧日因果缠身，你的气运开始折损。", {"character": {"status_effects_add": ["因果缠身"]}}),
    ]

    for narrative, delta in passing:
        ok, reason = validate_narrative_delta_consistency(narrative, delta)
        assert ok is True, narrative
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

    assert any("基础规则结算" in msg for msg in infos)
    assert engine.game_session.status_effects == []
    assert all("寒毒" not in text for text, _turn in narratives)
    assert engine.game_session.turn_history[-1]["narrative"] == ""
