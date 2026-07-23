"""Narrative duplication and authority-consistency quality guards."""

from __future__ import annotations

from unittest.mock import patch

from agens_novel.engine.game_engine import GameEngine
from agens_novel.engine.turn_flow import (
    _generic_distinct_chronicle,
    _has_unapproved_time_span,
    _has_visible_authoritative_delta,
    _is_recent_duplicate_narrative,
    _narrative_conflicts_with_authoritative_realm,
    _narrative_conflicts_with_stage_delta,
    _narrative_key,
    _narrative_keys_overlap,
)
from agens_novel.session.game_session import GameSession
from tests.unit.engine.quality_test_support import rule_outcome as _rule_outcome


def test_duplicate_model_narrative_is_replaced_by_rule_chronicle(monkeypatch) -> None:
    monkeypatch.setenv("AGNES_API_KEY", "test-model-key")
    engine = GameEngine()
    engine.game_session.game_started = True
    engine.game_session.turn_count = 1
    duplicate = "青岚谷重定名册，验真者按册修行，外界暗流仍在山门之外。"
    engine.game_session.turn_history.append(
        {
            "turn": 1,
            "input": "A",
            "narrative": duplicate,
            "delta": {"character": {}, "world": {}, "meta": {}},
            "choices": [],
        }
    )
    engine.game_session.last_choices = ["稳住课业", "打听消息", "探查边缘", "随缘行事"]

    rule_delta = {
        "character": {"age": "+1"},
        "world": {"lore_add": ["青岚谷讲师重排低阶课表，验真者被分入新讲席。"]},
        "meta": {
            "elapsed_years": 1,
            "choice_category": "稳妥",
            "event_lore": "青岚谷讲师重排低阶课表，验真者被分入新讲席。",
            "stage_goal": "把稳妥路线写成课业反馈",
        },
    }

    def runner(agent_name, user_input, session, **kw):
        if agent_name == "narrator":
            return {
                "narrative": duplicate,
                "state_delta": {"character": {}, "world": {}, "meta": {}},
                "choices": ["继续课业", "请教同门", "外出试炼", "随缘旁听"],
                "llm_error": "",
            }
        return {"approved": True, "corrected_delta": {}, "judgment_note": "", "llm_error": ""}

    with patch("agens_novel.engine.turn_flow.settle_turn_outcome", return_value=_rule_outcome(rule_delta)):
        with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=runner):
            engine.handle_action("A")

    assert engine.game_session.turn_history[-1]["narrative"] != duplicate
    assert "新讲席" in engine.game_session.turn_history[-1]["narrative"]


def test_duplicate_narrative_replacement_does_not_render_model_only_delta(
    monkeypatch,
) -> None:
    monkeypatch.setenv("AGNES_API_KEY", "test-model-key")
    engine = GameEngine()
    engine.game_session.game_started = True
    engine.game_session.turn_count = 1
    duplicate = "青岚谷重定名册，验真者按册修行，外界暗流仍在山门之外。"
    engine.game_session.turn_history.append(
        {
            "turn": 1,
            "input": "A",
            "narrative": duplicate,
            "delta": {"character": {}, "world": {}, "meta": {}},
            "choices": [],
        }
    )
    engine.game_session.last_choices = ["稳住课业", "打听消息", "探查边缘", "随缘行事"]
    rule_delta = {
        "character": {"age": "+1"},
        "world": {"lore_add": ["青岚谷讲师重排低阶课表，验真者被分入新讲席。"]},
        "meta": {
            "elapsed_years": 1,
            "choice_category": "稳妥",
            "event_lore": "青岚谷讲师重排低阶课表。",
        },
    }

    def runner(agent_name, user_input, session, **kw):
        if agent_name == "narrator":
            return {
                "narrative": duplicate,
                "state_delta": {
                    "character": {"status_effects_add": ["旧伤复发"]},
                    "world": {},
                    "meta": {},
                },
                "choices": ["继续课业", "请教同门", "外出试炼", "随缘旁听"],
                "llm_error": "",
            }
        return {"approved": True, "corrected_delta": {}, "judgment_note": "", "llm_error": ""}

    with patch("agens_novel.engine.turn_flow.settle_turn_outcome", return_value=_rule_outcome(rule_delta)):
        with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=runner):
            engine.handle_action("A")

    last_turn = engine.game_session.turn_history[-1]
    assert last_turn["narrative"] != duplicate
    assert "旧伤复发" not in last_turn["narrative"]
    assert "旧伤复发" not in engine.game_session.status_effects
    assert last_turn["delta"]["meta"]["model_state_update_ignored"]


def test_duplicate_narrative_with_lifespan_delta_is_not_replaced(monkeypatch) -> None:
    monkeypatch.setenv("AGNES_API_KEY", "test-model-key")
    engine = GameEngine()
    engine.game_session.game_started = True
    engine.game_session.turn_count = 1
    engine.game_session.lifespan = 100
    duplicate = "验真者服下延寿灵露，寿元增加一年。"
    engine.game_session.turn_history.append(
        {
            "turn": 1,
            "input": "B",
            "narrative": duplicate,
            "delta": {"character": {}, "world": {}, "meta": {}},
            "choices": [],
        }
    )
    engine.game_session.last_choices = ["稳住课业", "打听消息", "探查边缘", "随缘行事"]
    rule_delta = {
        "character": {"age": "+1", "lifespan": "+1"},
        "world": {"lore_add": ["青岚药圃封存旧灵露记录，另起新册。"]},
        "meta": {
            "elapsed_years": 1,
            "choice_category": "机缘",
            "event_lore": "青岚药圃封存旧灵露记录。",
        },
    }

    def runner(agent_name, user_input, session, **kw):
        if agent_name == "narrator":
            return {
                "narrative": duplicate,
                "state_delta": {"character": {}, "world": {}, "meta": {}},
                "choices": ["温养药力", "追查丹方", "冒险试药", "随缘静候"],
                "llm_error": "",
            }
        return {"approved": True, "corrected_delta": {}, "judgment_note": "", "llm_error": ""}

    with patch("agens_novel.engine.turn_flow.settle_turn_outcome", return_value=_rule_outcome(rule_delta)):
        with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=runner):
            engine.handle_action("服下延寿灵露")

    assert engine.game_session.turn_history[-1]["narrative"] == duplicate
    assert engine.game_session.lifespan == 101


def test_duplicate_narrative_with_attribute_delta_is_not_replaced(monkeypatch) -> None:
    monkeypatch.setenv("AGNES_API_KEY", "test-model-key")
    engine = GameEngine()
    engine.game_session.game_started = True
    engine.game_session.turn_count = 1
    engine.game_session.attributes["comprehension"] = 5
    duplicate = "数年参悟后，他的悟性大涨。"
    engine.game_session.turn_history.append(
        {
            "turn": 1,
            "input": "B",
            "narrative": duplicate,
            "delta": {"character": {}, "world": {}, "meta": {}},
            "choices": [],
        }
    )
    engine.game_session.last_choices = ["稳住课业", "打听消息", "探查边缘", "随缘行事"]
    rule_delta = {
        "character": {"age": "+1", "attributes": {"comprehension": 1}},
        "world": {"lore_add": ["青岚讲席记下新一轮经义评议。"]},
        "meta": {
            "elapsed_years": 1,
            "choice_category": "机缘",
            "event_lore": "青岚讲席记下新一轮经义评议。",
        },
    }

    def runner(agent_name, user_input, session, **kw):
        if agent_name == "narrator":
            return {
                "narrative": duplicate,
                "state_delta": {"character": {}, "world": {}, "meta": {}},
                "choices": ["稳住根基", "请教经义", "冒险试法", "随缘听命"],
                "llm_error": "",
            }
        return {"approved": True, "corrected_delta": {}, "judgment_note": "", "llm_error": ""}

    with patch("agens_novel.engine.turn_flow.settle_turn_outcome", return_value=_rule_outcome(rule_delta)):
        with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=runner):
            engine.handle_action("参悟经义")

    assert engine.game_session.turn_history[-1]["narrative"] == duplicate
    assert engine.game_session.attributes["comprehension"] == 6


def test_realm_stage_delta_blocks_duplicate_replacement_only_when_visible() -> None:
    delta = {"character": {"realm_stage": 2}, "world": {}, "meta": {}}

    assert _has_visible_authoritative_delta(delta, "数年苦修后，其修为提升至练气二层。")
    assert not _has_visible_authoritative_delta(delta, "青岚谷重定名册，验真者按册修行。")


def test_generic_replacement_chronicles_remain_distinct_across_repeated_stage_goal() -> None:
    session = GameSession()
    delta = {
        "character": {"age": "+1"},
        "world": {},
        "meta": {
            "elapsed_years": 1,
            "choice_category": "机遇",
            "story_goal": "判断边境裂脉的影响范围，并选择可信的同行者",
        },
    }
    keys = []
    for turn in (5, 10, 15, 20, 25):
        session.turn_count = turn
        keys.append(_narrative_key(_generic_distinct_chronicle(delta, session)))

    assert len(set(keys)) == 5
    assert all(
        not _narrative_keys_overlap(left, right)
        for index, left in enumerate(keys)
        for right in keys[index + 1 :]
    )


def test_generic_replacement_has_no_exact_reuse_across_sixty_turns() -> None:
    session = GameSession()
    delta = {
        "character": {"age": "+1"},
        "world": {},
        "meta": {
            "elapsed_years": 1,
            "choice_category": "气运",
            "story_goal": "判断边境裂脉的影响范围，并选择可信的同行者",
        },
    }

    keys = []
    for turn in range(1, 61):
        session.turn_count = turn
        chronicle = _generic_distinct_chronicle(delta, session)
        assert not any(marker in chronicle for marker in ("旁证", "卷册", "本阶段"))
        keys.append(_narrative_key(chronicle))

    assert len(set(keys)) == 60


def test_time_span_guard_accepts_authoritative_years_and_rejects_conflicts() -> None:
    three_years = {"meta": {"elapsed_years": 3}}
    forty_two_years = {"meta": {"elapsed_years": 42}}

    assert not _has_unapproved_time_span("三年间，山门旧案未平。", three_years)
    assert not _has_unapproved_time_span("42年后，旧案终于有了回音。", forty_two_years)
    assert not _has_unapproved_time_span("四十二载间，山门旧案未平。", forty_two_years)
    assert _has_unapproved_time_span("四十二载间，山门旧案未平。", three_years)
    assert _has_unapproved_time_span("三年间，冲关未成。", {"meta": {"elapsed_years": 0}})


def test_recent_narrative_hashes_survive_compacted_history() -> None:
    session = GameSession()
    duplicate = "潮音阁将验真者正式记入勤修榜，渡口同门纷纷效仿。"
    session.record_turn("A", duplicate, {})
    session.turn_history = []

    assert _is_recent_duplicate_narrative(session, duplicate)


def test_current_realm_guard_rejects_lone_stale_player_stage_claim() -> None:
    session = GameSession(realm="合体", realm_stage=2)

    assert _narrative_conflicts_with_authoritative_realm(
        "潮音阁将验真者记入勤修榜，其合体初期根基愈发深厚。", session
    )
    assert not _narrative_conflicts_with_authoritative_realm(
        "潮音阁将验真者记入勤修榜，其合体中期根基愈发深厚。", session
    )


def test_post_settlement_stage_claim_must_match_authoritative_stage() -> None:
    session = GameSession(realm="练气", realm_stage=9)
    delta = {"character": {"realm_stage": 9}, "meta": {"stage_advanced": True}}

    assert _narrative_conflicts_with_stage_delta("练气八层根基愈发扎实。", delta, session)
    assert not _narrative_conflicts_with_stage_delta("其由练气八层迈入练气九层。", delta, session)
    assert not _narrative_conflicts_with_stage_delta(
        "其根基又有精进，外界局势随之变化。", delta, session
    )


def test_stage_requirement_is_not_treated_as_player_realm_claim() -> None:
    session = GameSession(realm="练气", realm_stage=2)
    delta = {"character": {"realm_stage": 2}, "meta": {"stage_advanced": True}}
    narrative = (
        "悬赏榜标明，练气三层以上方可接取采集任务，练气一层即可登记杂役差事；"
        "执事另建议练气四层以上接取护送委托。"
    )

    assert not _narrative_conflicts_with_stage_delta(narrative, delta, session)


def test_task_sentence_with_player_breakthrough_is_checked() -> None:
    session = GameSession(realm="练气", realm_stage=2)
    delta = {"character": {"realm_stage": 2}, "meta": {"stage_advanced": True}}

    assert _narrative_conflicts_with_stage_delta(
        "完成宗门任务后，他突破至练气三层。",
        delta,
        session,
    )


def test_higher_realm_requirement_and_player_transition_are_disambiguated() -> None:
    session = GameSession(realm="筑基", realm_stage=2)
    delta = {"character": {"realm_stage": 2}, "meta": {"stage_advanced": True}}

    assert not _narrative_conflicts_with_stage_delta(
        "执事说明，筑基后期以上方可接取此项差事。",
        delta,
        session,
    )
    assert _narrative_conflicts_with_stage_delta(
        "完成差事后，他晋入筑基后期。",
        delta,
        session,
    )


def test_post_settlement_phase_claim_must_match_authoritative_stage() -> None:
    session = GameSession(realm="筑基", realm_stage=2)
    delta = {"character": {"realm_stage": 2}, "meta": {"stage_advanced": True}}

    assert _narrative_conflicts_with_stage_delta("其筑基初期根基已经稳固。", delta, session)
    assert not _narrative_conflicts_with_stage_delta("其由筑基初期迈入筑基中期。", delta, session)


def test_browser_threshold_near_duplicate_narrative_is_detected() -> None:
    previous = (
        "三十九岁，验真者循着断云古道旧路重开的消息，在接引营中物色起色。"
        "同门多畏惧妖兽，唯有一落魄散修愿结伴探路。"
        "商栈传言古道深处或有低阶灵材，足以弥补修为短板，众人议论纷纷，气氛微妙。"
    )
    repeated = (
        "四十岁，验真者循着驼铃商栈的线索，在接引营中物色起色。"
        "同门多畏惧妖兽，唯有一落魄散修愿结伴探路。"
        "商栈传言古道深处或有低阶灵材，足以弥补修为短板，众人议论纷纷，气氛微妙。"
    )

    assert _narrative_keys_overlap(_narrative_key(previous), _narrative_key(repeated))


def test_short_narrative_reusing_previous_ending_is_detected() -> None:
    previous = (
        "八十九岁，砺锋院重修低阶课业簿，荒岭接引营弟子开始按月比对吐纳进度。"
        "练气九层的根基有了可见标尺，验真者依循新规，于喧嚣中理清头绪，静待清算。"
    )
    repeated = "九十岁，验真者依循新规，于喧嚣中理清头绪，静待清算。"

    assert _narrative_keys_overlap(_narrative_key(previous), _narrative_key(repeated))


def test_age_variant_duplicate_model_narrative_is_replaced(monkeypatch) -> None:
    monkeypatch.setenv("AGNES_API_KEY", "test-model-key")
    engine = GameEngine()
    engine.game_session.game_started = True
    engine.game_session.turn_count = 32
    previous = (
        "七十五岁，山径夜半灵光乍现。验真者静观其变，未妄动。"
        "坊市传闻四起，皆言此乃异兆。他知机缘难得，亦伴凶险。"
        "因果账目渐清，他决定顺势而为，探寻那抹微光的源头，静待天命回响。"
    )
    repeated = previous.replace("七十五岁", "七十岁")
    engine.game_session.turn_history.append(
        {
            "turn": 32,
            "input": "B",
            "narrative": previous,
            "delta": {"character": {}, "world": {}, "meta": {}},
            "choices": [],
        }
    )
    engine.game_session.last_choices = ["稳住课业", "打听消息", "探查边缘", "随缘行事"]

    rule_delta = {
        "character": {"age": "+1"},
        "world": {"lore_add": ["青岚药圃把旧异兆归档，验真者转向新的因果线索。"]},
        "meta": {
            "elapsed_years": 1,
            "choice_category": "机缘",
            "event_lore": "青岚药圃把旧异兆归档，验真者转向新的因果线索。",
            "stage_goal": "把机缘路线写成新线索推进",
        },
    }

    def runner(agent_name, user_input, session, **kw):
        if agent_name == "narrator":
            return {
                "narrative": repeated,
                "state_delta": {"character": {}, "world": {}, "meta": {}},
                "choices": ["回头复盘", "追查新线索", "冒险试探", "听天命"],
                "llm_error": "",
            }
        return {"approved": True, "corrected_delta": {}, "judgment_note": "", "llm_error": ""}

    with patch("agens_novel.engine.turn_flow.settle_turn_outcome", return_value=_rule_outcome(rule_delta)):
        with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=runner):
            engine.handle_action("B")

    final_narrative = engine.game_session.turn_history[-1]["narrative"]
    assert final_narrative != repeated
    assert "新的因果线索" in final_narrative


def test_calendar_variant_duplicate_model_narrative_is_replaced(monkeypatch) -> None:
    monkeypatch.setenv("AGNES_API_KEY", "test-model-key")
    engine = GameEngine()
    engine.game_session.game_started = True
    engine.game_session.turn_count = 11
    previous = (
        "玄历四十四年，验真者四十四岁。青岚谷外门新贴因果账，称雾萝山径近来得失相抵，"
        "受益者日后多半也要偿一笔人情。此人静观其变，未随波逐流，只将异象化为心底警戒。"
        "坊市风声鹤唳，因果账目清晰，他深知此时当以静制动，任气运流转，静待后续变数。"
    )
    repeated = previous.replace("四十四年", "五十三年").replace("四十四岁", "五十三岁")
    engine.game_session.turn_history.append(
        {
            "turn": 11,
            "input": "D",
            "narrative": previous,
            "delta": {"character": {}, "world": {}, "meta": {}},
            "choices": [],
        }
    )
    engine.game_session.last_choices = ["稳住课业", "打听消息", "探查边缘", "随缘行事"]

    rule_delta = {
        "character": {"age": "+1", "realm_stage": 6},
        "world": {"lore_add": ["青岚谷把旧因果账封存，另有一条签文落到验真者案前。"]},
        "meta": {
            "elapsed_years": 1,
            "choice_category": "气运",
            "event_lore": "青岚谷把旧因果账封存，另有一条签文落到验真者案前。",
            "stage_goal": "把气运路线写成新签文推进",
            "stage_advanced": True,
            "new_stage": 6,
            "max_stage": 9,
        },
    }

    def runner(agent_name, user_input, session, **kw):
        if agent_name == "narrator":
            return {
                "narrative": repeated,
                "state_delta": {"character": {}, "world": {}, "meta": {}},
                "choices": ["继续复盘", "追问签文", "冒险验签", "随缘接签"],
                "llm_error": "",
            }
        return {"approved": True, "corrected_delta": {}, "judgment_note": "", "llm_error": ""}

    with patch("agens_novel.engine.turn_flow.settle_turn_outcome", return_value=_rule_outcome(rule_delta)):
        with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=runner):
            engine.handle_action("D")

    final_narrative = engine.game_session.turn_history[-1]["narrative"]
    assert final_narrative != repeated
    assert "签文落到验真者案前" in final_narrative or "新签文推进" in final_narrative


def test_high_similarity_duplicate_model_narrative_is_replaced(monkeypatch) -> None:
    monkeypatch.setenv("AGNES_API_KEY", "test-model-key")
    engine = GameEngine()
    engine.game_session.game_started = True
    engine.game_session.turn_count = 3
    previous = (
        "坊市流传雾萝山径因果账，称得失必偿人情。验真者静坐三年，对风波充耳不闻，"
        "仅凭金灵根稳固根基。岁月流逝，其心如止水，在青岚药圃边缘继续吐纳，"
        "静待那笔尚未落定的人情债何时清算，心境在无声中愈发坚韧。"
    )
    repeated = previous.replace("雾萝山径", "无名签文")
    engine.game_session.turn_history.append(
        {
            "turn": 3,
            "input": "D",
            "narrative": previous,
            "delta": {"character": {}, "world": {}, "meta": {}},
            "choices": [],
        }
    )
    engine.game_session.last_choices = ["稳住课业", "打听消息", "探查边缘", "随缘行事"]

    rule_delta = {
        "character": {"age": "+3"},
        "world": {"lore_add": ["青岚药圃将旧账移入巡册，验真者另得一条地方风声。"]},
        "meta": {
            "elapsed_years": 3,
            "choice_category": "气运",
            "event_lore": "青岚药圃将旧账移入巡册，验真者另得一条地方风声。",
            "stage_goal": "把气运路线写成地方变化",
        },
    }

    def runner(agent_name, user_input, session, **kw):
        if agent_name == "narrator":
            return {
                "narrative": repeated,
                "state_delta": {"character": {}, "world": {}, "meta": {}},
                "choices": ["继续复盘", "追问签文", "冒险验签", "随缘接签"],
                "llm_error": "",
            }
        return {"approved": True, "corrected_delta": {}, "judgment_note": "", "llm_error": ""}

    with patch("agens_novel.engine.turn_flow.settle_turn_outcome", return_value=_rule_outcome(rule_delta)):
        with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=runner):
            engine.handle_action("D")

    final_narrative = engine.game_session.turn_history[-1]["narrative"]
    assert final_narrative != repeated
    assert "地方风声" in final_narrative or "地方变化" in final_narrative


def test_contained_duplicate_model_narrative_is_replaced(monkeypatch) -> None:
    monkeypatch.setenv("AGNES_API_KEY", "test-model-key")
    engine = GameEngine()
    engine.game_session.game_started = True
    engine.game_session.turn_count = 13
    previous = (
        "1年间，青岚谷外门新贴因果账，称雾萝山径近来得失相抵，"
        "受益者日后多半也要偿一笔人情。 本次记为复盘札，侧重短板补足。"
    )
    repeated = "青岚谷外门新贴因果账，称雾萝山径近来得失相抵，受益者日后多半也要偿一笔人情。"
    engine.game_session.turn_history.append(
        {
            "turn": 13,
            "input": "D",
            "narrative": previous,
            "delta": {"character": {}, "world": {}, "meta": {}},
            "choices": [],
        }
    )
    engine.game_session.last_choices = ["稳住课业", "打听消息", "探查边缘", "随缘行事"]

    rule_delta = {
        "character": {"age": "+1"},
        "world": {"lore_add": ["青岚谷把旧因果账封存，另有一条签文落到验真者案前。"]},
        "meta": {
            "elapsed_years": 1,
            "choice_category": "气运",
            "event_lore": "青岚谷把旧因果账封存，另有一条签文落到验真者案前。",
            "stage_goal": "把气运路线写成新签文推进",
        },
    }

    def runner(agent_name, user_input, session, **kw):
        if agent_name == "narrator":
            return {
                "narrative": repeated,
                "state_delta": {"character": {}, "world": {}, "meta": {}},
                "choices": ["继续复盘", "追问签文", "冒险验签", "随缘接签"],
                "llm_error": "",
            }
        return {"approved": True, "corrected_delta": {}, "judgment_note": "", "llm_error": ""}

    with patch("agens_novel.engine.turn_flow.settle_turn_outcome", return_value=_rule_outcome(rule_delta)):
        with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=runner):
            engine.handle_action("D")

    final_narrative = engine.game_session.turn_history[-1]["narrative"]
    assert final_narrative != repeated
    assert "新签文推进" in final_narrative or "签文落到验真者案前" in final_narrative
