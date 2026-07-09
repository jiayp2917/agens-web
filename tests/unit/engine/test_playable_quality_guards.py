"""Focused gameplay-quality guards for the playable vertical slice."""

from __future__ import annotations

from unittest.mock import patch

from agens_novel.engine.game_engine import GameEngine
from agens_novel.engine.action_delta_policy import merge_rule_delta, validate_narrative_delta_consistency
from agens_novel.engine.choices import CHOICE_FALLBACK_NOTICE, clean_visible_text, fallback_choices
from agens_novel.engine.event_catalog import select_chronicle_event
from agens_novel.engine.model_fallback_policy import public_model_failure_notice
from agens_novel.engine.turn_flow import _has_visible_authoritative_delta
from agens_novel.engine.turn_rules import classify_choice, settle_turn
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


def test_model_contract_failure_notice_is_public_text() -> None:
    for reason in (
        "模型已返回叙事，但状态更新格式不完整。",
        "模型输出缺少叙事正文。",
        "模型已返回叙事，但未返回可用 A/B/C/D 选项。",
        "模型已返回叙事，但未返回恰好 4 个 A/B/C/D 选项。",
    ):
        text = public_model_failure_notice(reason)
        assert text == CHOICE_FALLBACK_NOTICE
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


def test_json_only_narrator_output_uses_rule_chronicle_without_local_story(monkeypatch) -> None:
    monkeypatch.setenv("AGNES_API_KEY", "test-model-key")
    engine = GameEngine()
    engine.game_session.game_started = True
    engine.game_session.last_choices = ["稳妥修行", "拜访同门", "探查禁地", "随缘而行"]

    def runner(agent_name, user_input, session, **kw):
        if agent_name == "narrator":
            return {
                "narrative": "",
                "state_delta": {"character": {}, "world": {"lore_add": ["模型只给结构化见闻"]}, "meta": {}},
                "choices": ["继续稳修", "打听消息", "探查边缘", "随缘行事"],
                "llm_error": "",
            }
        return {"approved": True, "corrected_delta": {}, "judgment_note": "", "llm_error": ""}

    with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=runner):
        engine.handle_action("A")

    assert engine.game_session.local_story_active is False
    assert engine.game_session.turn_count == 1
    assert engine.game_session.turn_history[-1]["narrative"]
    assert engine.game_session.last_choices == ["继续稳修", "打听消息", "探查边缘", "随缘行事"]


def test_local_story_fallback_turn_does_not_claim_unapplied_rule_event(monkeypatch) -> None:
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

    with patch("agens_novel.engine.turn_flow.settle_turn", return_value=rule_delta):
        with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=runner):
            engine.handle_action("A")

    last_turn = engine.game_session.turn_history[-1]
    assert last_turn["delta"]["meta"]["local_story_fallback"] is True
    assert last_turn["delta"]["meta"]["elapsed_years"] == 0
    assert "药圃账册" not in last_turn["narrative"]
    assert "3年间" not in last_turn["narrative"]


def test_duplicate_model_narrative_is_replaced_by_rule_chronicle(monkeypatch) -> None:
    monkeypatch.setenv("AGNES_API_KEY", "test-model-key")
    engine = GameEngine()
    engine.game_session.game_started = True
    engine.game_session.turn_count = 1
    duplicate = "青岚谷重定名册，验真者按册修行，外界暗流仍在山门之外。"
    engine.game_session.turn_history.append({
        "turn": 1,
        "input": "A",
        "narrative": duplicate,
        "delta": {"character": {}, "world": {}, "meta": {}},
        "choices": [],
    })
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

    with patch("agens_novel.engine.turn_flow.settle_turn", return_value=rule_delta):
        with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=runner):
            engine.handle_action("A")

    assert engine.game_session.turn_history[-1]["narrative"] != duplicate
    assert "新讲席" in engine.game_session.turn_history[-1]["narrative"]


def test_duplicate_narrative_with_visible_delta_is_not_replaced_by_unrelated_rule_text(monkeypatch) -> None:
    monkeypatch.setenv("AGNES_API_KEY", "test-model-key")
    engine = GameEngine()
    engine.game_session.game_started = True
    engine.game_session.turn_count = 1
    duplicate = "青岚谷重定名册，验真者按册修行，外界暗流仍在山门之外。"
    engine.game_session.turn_history.append({
        "turn": 1,
        "input": "A",
        "narrative": duplicate,
        "delta": {"character": {}, "world": {}, "meta": {}},
        "choices": [],
    })
    engine.game_session.last_choices = ["稳住课业", "打听消息", "探查边缘", "随缘行事"]
    rule_delta = {
        "character": {"age": "+1"},
        "world": {"lore_add": ["青岚谷讲师重排低阶课表，验真者被分入新讲席。"]},
        "meta": {"elapsed_years": 1, "choice_category": "稳妥", "event_lore": "青岚谷讲师重排低阶课表。"},
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

    with patch("agens_novel.engine.turn_flow.settle_turn", return_value=rule_delta):
        with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=runner):
            engine.handle_action("A")

    last_turn = engine.game_session.turn_history[-1]
    assert last_turn["narrative"] == duplicate
    assert "旧伤复发" in engine.game_session.status_effects


def test_duplicate_narrative_with_lifespan_delta_is_not_replaced(monkeypatch) -> None:
    monkeypatch.setenv("AGNES_API_KEY", "test-model-key")
    engine = GameEngine()
    engine.game_session.game_started = True
    engine.game_session.turn_count = 1
    engine.game_session.lifespan = 100
    duplicate = "验真者服下延寿灵露，寿元增加一年。"
    engine.game_session.turn_history.append({
        "turn": 1,
        "input": "B",
        "narrative": duplicate,
        "delta": {"character": {}, "world": {}, "meta": {}},
        "choices": [],
    })
    engine.game_session.last_choices = ["稳住课业", "打听消息", "探查边缘", "随缘行事"]
    rule_delta = {
        "character": {"age": "+1", "lifespan": "+1"},
        "world": {"lore_add": ["青岚药圃封存旧灵露记录，另起新册。"]},
        "meta": {"elapsed_years": 1, "choice_category": "机缘", "event_lore": "青岚药圃封存旧灵露记录。"},
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

    with patch("agens_novel.engine.turn_flow.settle_turn", return_value=rule_delta):
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
    engine.game_session.turn_history.append({
        "turn": 1,
        "input": "B",
        "narrative": duplicate,
        "delta": {"character": {}, "world": {}, "meta": {}},
        "choices": [],
    })
    engine.game_session.last_choices = ["稳住课业", "打听消息", "探查边缘", "随缘行事"]
    rule_delta = {
        "character": {"age": "+1", "attributes": {"comprehension": 1}},
        "world": {"lore_add": ["青岚讲席记下新一轮经义评议。"]},
        "meta": {"elapsed_years": 1, "choice_category": "机缘", "event_lore": "青岚讲席记下新一轮经义评议。"},
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

    with patch("agens_novel.engine.turn_flow.settle_turn", return_value=rule_delta):
        with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=runner):
            engine.handle_action("参悟经义")

    assert engine.game_session.turn_history[-1]["narrative"] == duplicate
    assert engine.game_session.attributes["comprehension"] == 6


def test_realm_stage_delta_blocks_duplicate_replacement_only_when_visible() -> None:
    delta = {"character": {"realm_stage": 2}, "world": {}, "meta": {}}

    assert _has_visible_authoritative_delta(delta, "数年苦修后，其修为提升至练气二层。")
    assert not _has_visible_authoritative_delta(delta, "青岚谷重定名册，验真者按册修行。")


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
    engine.game_session.turn_history.append({
        "turn": 32,
        "input": "B",
        "narrative": previous,
        "delta": {"character": {}, "world": {}, "meta": {}},
        "choices": [],
    })
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

    with patch("agens_novel.engine.turn_flow.settle_turn", return_value=rule_delta):
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
    engine.game_session.turn_history.append({
        "turn": 11,
        "input": "D",
        "narrative": previous,
        "delta": {"character": {}, "world": {}, "meta": {}},
        "choices": [],
    })
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

    with patch("agens_novel.engine.turn_flow.settle_turn", return_value=rule_delta):
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
    engine.game_session.turn_history.append({
        "turn": 3,
        "input": "D",
        "narrative": previous,
        "delta": {"character": {}, "world": {}, "meta": {}},
        "choices": [],
    })
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

    with patch("agens_novel.engine.turn_flow.settle_turn", return_value=rule_delta):
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
    engine.game_session.turn_history.append({
        "turn": 13,
        "input": "D",
        "narrative": previous,
        "delta": {"character": {}, "world": {}, "meta": {}},
        "choices": [],
    })
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

    with patch("agens_novel.engine.turn_flow.settle_turn", return_value=rule_delta):
        with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=runner):
            engine.handle_action("D")

    final_narrative = engine.game_session.turn_history[-1]["narrative"]
    assert final_narrative != repeated
    assert "新签文推进" in final_narrative or "签文落到验真者案前" in final_narrative


def test_choice_category_accepts_visible_route_semantics() -> None:
    cases = [
        ("A\u3010\u7a33\u59a5\u3011\u95ed\u5173\u7a33\u56fa", "\u7a33\u59a5"),
        ("\u3010\u7a33\u59a5\u3011\u95ed\u5173\u7a33\u56fa", "\u7a33\u59a5"),
        ("\u673a\u9047\uff1a\u62dc\u8bbf\u540c\u95e8", "\u673a\u9047"),
        ("\u3010\u98ce\u9669\u3011\u63a2\u67e5\u7981\u5730", "\u98ce\u9669"),
        ("\u6c14\u8fd0:\u968f\u7f18\u800c\u884c", "\u6c14\u8fd0"),
    ]

    for text, expected in cases:
        assert classify_choice(text) == expected


def test_judge_not_triggered_for_plain_risk_word_without_authoritative_delta(monkeypatch) -> None:
    monkeypatch.setenv("AGNES_API_KEY", "test-model-key")
    engine = GameEngine()
    engine.game_session.game_started = True
    engine.game_session.last_choices = ["稳妥修行", "拜访同门", "探查禁地边缘", "随缘而行"]
    calls: list[str] = []

    def runner(agent_name, user_input, session, **kw):
        calls.append(agent_name)
        if agent_name == "narrator":
            return {
                "narrative": "他只在禁地边缘听闻旧事，并未真正涉险。",
                "state_delta": {"character": {}, "world": {"lore_add": ["禁地边缘近日有人巡查"]}, "meta": {}},
                "choices": ["返回山门", "询问同门", "继续观察", "随缘而行"],
                "llm_error": "",
            }
        raise AssertionError("judge should not run for non-authoritative risk color text")

    with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=runner):
        engine.handle_action("探查禁地边缘")

    assert calls == ["narrator"]


def test_judge_retryable_provider_failure_retries_once(monkeypatch) -> None:
    monkeypatch.setenv("AGNES_API_KEY", "test-model-key")
    engine = GameEngine()
    engine.game_session.game_started = True
    engine.game_session.last_choices = ["稳妥修行", "拜访同门", "探查禁地边缘", "随缘而行"]
    calls: list[str] = []
    model_statuses: list[tuple[str, str]] = []
    engine.on_model_result = (
        lambda agent, source, status, model_set, base_url_set, key_set, config_source, diagnostics:
        model_statuses.append((agent, status))
    )

    def runner(agent_name, user_input, session, **kw):
        calls.append(agent_name)
        if agent_name == "narrator":
            return {
                "narrative": "验真者服下延寿丹，寿元增加一年。",
                "state_delta": {"character": {"lifespan": "+1"}, "world": {}, "meta": {}},
                "choices": ["继续温养", "打听丹方", "试探禁地", "随缘行事"],
                "llm_error": "",
            }
        if agent_name == "judge" and calls.count("judge") == 1:
            return {
                "approved": False,
                "corrected_delta": {},
                "judgment_note": "",
                "llm_error": 'HTTP 404: {"error":{"type":"upstream_error","code":"404"}}',
            }
        if agent_name == "judge":
            return {"approved": True, "corrected_delta": {}, "judgment_note": "", "llm_error": ""}
        return {}

    with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=runner):
        engine.handle_action("服下延寿丹")

    assert calls.count("judge") == 2
    assert ("judge", "ok") in model_statuses
    assert ("judge", "judge_failed") not in model_statuses
    assert engine.game_session.turn_count == 1


def test_judge_triggers_for_authoritative_world_delta(monkeypatch) -> None:
    monkeypatch.setenv("AGNES_API_KEY", "test-model-key")
    engine = GameEngine()

    assert engine.should_run_judge(
        "拜访同门",
        {"world": {"npcs_present_add": [{"name": "陈师兄", "relation": "盟友"}]}},
        {"meta": {"choice_category": "机遇"}},
    )
    assert engine.should_run_judge(
        "接下任务",
        {"world": {"active_quests_add": [{"name": "采药任务"}]}},
        {"meta": {"choice_category": "机遇"}},
    )
    assert engine.should_run_judge(
        "深入山径",
        {"world": {"discovered_add": ["后山药谷"]}},
        {"meta": {"choice_category": "机遇"}},
    )
    assert not engine.should_run_judge(
        "听闻传说",
        {"world": {"lore_add": ["坊间只是传闻，并未入册"]}},
        {"meta": {"choice_category": "机遇"}},
    )


def test_judge_triggers_for_techniques_and_sensitive_inventory_only(monkeypatch) -> None:
    monkeypatch.setenv("AGNES_API_KEY", "test-model-key")
    engine = GameEngine()

    assert engine.should_run_judge(
        "参悟玉简",
        {"character": {"techniques_add": [{"name": "青木长生诀"}]}},
        {"meta": {"choice_category": "机遇"}},
    )
    assert engine.should_run_judge(
        "收下筑基丹",
        {"character": {"inventory_add": [{"name": "筑基丹", "type": "丹药"}]}},
        {"meta": {"choice_category": "机遇"}},
    )
    assert engine.should_run_judge(
        "收下宗门信物",
        {"character": {"inventory_add": [{"name": "青岚令", "key_item": True}]}},
        {"meta": {"choice_category": "机遇"}},
    )
    assert not engine.should_run_judge(
        "收下普通药草",
        {"character": {"inventory_add": [{"name": "止血草", "type": "草药", "rarity": "白"}]}},
        {"meta": {"choice_category": "机遇"}},
    )


def test_stage_feedback_adds_world_lore_every_four_turns() -> None:
    session = GameSession(location="青岚山门", turn_count=4, realm="筑基", realm_stage=2)

    delta = settle_turn("A", session)

    assert delta["world"]["lore_add"]
    assert "青岚山门" in delta["world"]["lore_add"][0]
    assert "筑基中期" in delta["world"]["lore_add"][0]
    assert "筑基2层" not in delta["world"]["lore_add"][0]


def test_stage_feedback_uses_route_event_pools() -> None:
    expected_markers = {
        "A": ("根基", "课表", "差事"),
        "B": ("消息", "旧闻", "讲评"),
        "C": ("异动", "约斗", "旧伤"),
        "D": ("签文", "小兆", "因果账"),
    }
    for choice, markers in expected_markers.items():
        session = GameSession(location="青岚山门", turn_count=4, realm="筑基", realm_stage=2)
        delta = settle_turn(choice, session)
        lore = delta["world"]["lore_add"][0]
        assert any(marker in lore for marker in markers)
        assert "筑基中期" in lore or choice != "A"


def test_stage_feedback_pool_rotates_across_later_phases() -> None:
    session = GameSession(location="青岚山门", turn_count=4)
    early = settle_turn("B", session)["world"]["lore_add"][0]

    session.turn_count = 8
    middle = settle_turn("B", session)["world"]["lore_add"][0]

    session.turn_count = 12
    later = settle_turn("B", session)["world"]["lore_add"][0]

    assert len({early, middle, later}) == 3


def test_chronicle_event_context_is_selected_every_turn() -> None:
    session = GameSession(location="潮音渡口", region="沧澜群岛", turn_count=1)
    session.world_profile = {
        "world_name": "沧澜群岛",
        "world_key": "ocean",
        "fate_profile": [{"label": "天命", "score": 4}],
        "event_weights": {"气运": 3},
    }

    event = select_chronicle_event(session, "气运", 18)

    assert event["id"]
    assert event["category"] == "气运"
    assert event["stage_goal"]
    assert event["allowed_delta_types"]
    assert event["choice_hints"] and len(event["choice_hints"]) == 4
    assert "天命" in event["matched_fates"]


def test_fixed_route_chronicle_event_avoids_recent_reuse() -> None:
    session = GameSession(location="青岚山门", turn_count=1)
    seen: list[str] = []

    for turn in range(1, 9):
        session.turn_count = turn
        event = select_chronicle_event(session, "稳妥", 18 + turn)
        assert event["id"] not in seen[-3:]
        seen.append(event["id"])
        session.turn_history.append({"delta": {"meta": {"event_id": event["id"]}}})

    assert len(set(seen[:4])) == 4


def test_settle_turn_records_event_meta_without_forcing_authoritative_rewards() -> None:
    session = GameSession(location="青岚山门", turn_count=1)
    delta = settle_turn("B", session)

    assert delta["meta"]["event_id"]
    assert delta["meta"]["event_type"]
    assert delta["meta"]["event_lore"]
    assert delta["meta"]["stage_goal"]
    assert delta["meta"]["allowed_delta_types"]
    assert "inventory_add" not in delta["character"]


def test_rule_world_delta_survives_model_merge() -> None:
    merged = merge_rule_delta(
        {"character": {}, "world": {"lore_add": ["模型见闻"]}, "meta": {}},
        {"world": {"lore_add": ["规则阶段反馈"]}, "meta": {"elapsed_years": 2}},
    )

    assert merged["world"]["lore_add"] == ["模型见闻", "规则阶段反馈"]
    assert merged["meta"]["elapsed_years"] == 2


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
    engine.game_session.chat_history = [{"role": "assistant", "content": "开局设定：青岚界山门初开。"}]
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
    assert not any(entry["content"] == "第1回合，他按部就班修行。" for entry in engine.game_session.chat_history[1:])


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

    with patch("agens_novel.engine.turn_flow.settle_turn", return_value=rule_delta):
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

    with patch("agens_novel.engine.turn_flow.settle_turn", return_value=rule_delta):
        with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=runner):
            engine.handle_action("参悟经义")

    assert narratives[-1][0] == "数年参悟后，他的悟性大涨。"
    assert engine.game_session.attributes["comprehension"] == 6
    assert engine.game_session.turn_history[-1]["narrative"] == "数年参悟后，他的悟性大涨。"
