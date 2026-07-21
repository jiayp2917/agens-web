"""Versioned long-form story arcs for chronicle gameplay."""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, replace
from typing import Any

from .world_catalog import world_key_for_name

STORY_RESOLUTION_TURN = 60
STORY_V2_RESOLUTION_TURN = 90
STORY_V3_RESOLUTION_TURN = 90
DEFAULT_STORY_CONTENT_VERSION = 2


@dataclass(frozen=True)
class StoryPhase:
    key: str
    title: str
    min_turn: int
    max_turn: int
    goal: str
    thread: str
    beats: dict[str, str]
    events: tuple[StoryEvent, ...] = ()
    route_consequences: tuple[tuple[str, tuple[str, str]], ...] = ()


@dataclass(frozen=True)
class StoryEvent:
    """One catalog-owned v3 event with a stable anti-repetition motif."""

    id: str
    motif: str
    summary: str


@dataclass(frozen=True)
class StoryArc:
    key: str
    version: int
    title: str
    worlds: tuple[str, ...]
    fate_tags: tuple[str, ...]
    opening: str
    unresolved_thread: str
    ally_faction: str
    rival_faction: str
    neutral_faction: str
    phases: tuple[StoryPhase, ...]
    commitments: dict[str, str]
    failure_branch: str
    endings: dict[str, str]


def _phases(subject: str, rival: str, neutral: str) -> tuple[StoryPhase, ...]:
    return (
        StoryPhase(
            "opening",
            "入局",
            1,
            12,
            f"查清{subject}为何异动，并确认谁在散布最早的消息",
            f"{subject}的第一份记录来源不明",
            {
                "稳妥": f"其从名册和旧档核对{subject}，先排除了最浅的一层误传。",
                "机遇": f"其沿{neutral}的消息网追问，找到一名曾亲见{subject}异状的人。",
                "风险": f"其越过告诫逼近{subject}，也因此被{rival}的人记住。",
                "气运": f"其暂不追逐明面线索，却在偶然征兆中记下{subject}的另一种解释。",
            },
        ),
        StoryPhase(
            "spread",
            "扩散",
            13,
            24,
            f"判断{subject}的影响范围，并选择可信的同行者",
            f"{rival}开始借{subject}扩大影响",
            {
                "稳妥": f"其把已知线索交给可信执事，{subject}第一次进入正式议程。",
                "机遇": f"其借一次交换取得新证词，发现{neutral}内部也有人隐瞒旧账。",
                "风险": f"其与{rival}的外围人手正面碰撞，换来一条带伤的真线索。",
                "气运": f"其顺着反常征兆改道，恰好避开假消息并触及{subject}的旧因。",
            },
        ),
        StoryPhase(
            "turning",
            "转折",
            25,
            36,
            f"确认{subject}背后的真正受益者，并处理此前留下的人情与敌意",
            f"最初的盟友与{rival}之间出现身份倒置",
            {
                "稳妥": "其逐项复核旧约，发现一名看似可靠的中间人曾改动关键日期。",
                "机遇": "其以一份新线索换得旧证物，主线矛盾由传闻转为可以查证的事实。",
                "风险": f"其逼迫{rival}的知情者开口，却让自己背上一笔必须偿还的因果。",
                "气运": "其在一次无意相逢中认出旧证物的真正主人，先前判断因此反转。",
            },
        ),
        StoryPhase(
            "choice",
            "抉择",
            37,
            48,
            f"决定公开、利用、封存或改写{subject}的真相",
            "各方开始要求其兑现此前的承诺",
            {
                "稳妥": "其选择先稳住受波及之人，再把证据交给能够承担后果的势力。",
                "机遇": "其借真相换取进入核心地点的资格，也把自己推到更显眼的位置。",
                "风险": f"其主动向{rival}设局，准备以一次高风险行动结束长期试探。",
                "气运": "其保留最后一份证据，等待命数最有利的时点迫使各方表态。",
            },
        ),
        StoryPhase(
            "resolution",
            "收束",
            49,
            STORY_RESOLUTION_TURN,
            f"承担选择的长期后果，使{subject}之争形成明确结局",
            "主线进入不可回避的收束阶段",
            {
                "稳妥": "其以可复核的证据结束争端，所得不多，却保住了最多人的退路。",
                "机遇": "其把握最后一次交换，让真相与自身前路同时得到兑现。",
                "风险": "其亲自承担决战代价，以伤势和声名换来主线的强行收束。",
                "气运": "其没有控制所有结果，却让多年积累的因果在同一日相互抵消。",
            },
        ),
    )


def _phases_v2(
    subject: str,
    ally: str,
    rival: str,
    neutral: str,
) -> tuple[StoryPhase, ...]:
    specs = (
        (
            "entry",
            "入局",
            1,
            10,
            f"确认{subject}的第一份可信记录，并在{ally}与{neutral}之间建立立足点",
            f"{subject}最早的记录仍缺少见证者",
            "其先核对名册与旧档，使最初传闻有了可复查的边界。",
        ),
        (
            "rooting",
            "扎根",
            11,
            20,
            f"建立稳定修行与情报来源，并辨认{rival}对{subject}的试探",
            f"{rival}开始接触外围见证者",
            f"其在{ally}站稳脚跟，也第一次看清各方围绕{subject}的真实代价。",
        ),
        (
            "spread",
            "扩散",
            21,
            30,
            f"追踪{subject}向外扩散的范围，并决定哪些线索应当公开",
            f"{subject}的影响越过原有边界",
            f"其把旁证串联起来，迫使{neutral}承认局势已经不再局限于一地。",
        ),
        (
            "reversal",
            "反转",
            31,
            40,
            f"查明{subject}中被倒置的因果，并重新判断盟友与敌手",
            f"早期证词显示{rival}并非唯一受益者",
            "其复核旧日承诺，发现最可靠的一份证词恰好隐去了关键年月。",
        ),
        (
            "alignment",
            "分阵",
            41,
            50,
            f"在{ally}、{rival}与{neutral}公开分阵前确定自身立场",
            "各方要求其交出证据并兑现早年的承诺",
            f"其公开一部分证据，使{ally}与{neutral}不得不表明各自底线。",
        ),
        (
            "rupture",
            "决裂",
            51,
            60,
            f"处理{subject}引发的公开冲突，并承担阵营选择的直接后果",
            f"{rival}切断旧有协商渠道",
            f"其不再维持表面均衡，围绕{subject}的旧秩序由此决裂。",
        ),
        (
            "unification",
            "归一",
            61,
            70,
            "把分散证据、修行成果与势力承诺归为一条可执行的解决路径",
            "前期承诺开始逐项兑现或反噬",
            "其逐项清偿人情与旧债，使多年积累第一次指向同一个结论。",
        ),
        (
            "tribulation-preparation",
            "渡劫准备",
            71,
            80,
            f"为{subject}的最终清算准备护持、见证与失败退路",
            "最终行动所需的护持仍缺最后一环",
            f"其让{ally}负责见证、{neutral}保留退路，并迫使{rival}提前暴露底牌。",
        ),
        (
            "ascension-resolution",
            "证道收束",
            81,
            STORY_V2_RESOLUTION_TURN,
            f"完成{subject}的最终清算，使路线选择、修行结果与世界后果同时落定",
            "主线与个人道途已进入不可逆的最后阶段",
            "其把前期承诺、势力代价与自身道途一并摆上最后的因果清算。",
        ),
    )
    phases: list[StoryPhase] = []
    for key, title, min_turn, max_turn, goal, thread, common_beat in specs:
        phases.append(
            StoryPhase(
                key,
                title,
                min_turn,
                max_turn,
                goal,
                thread,
                {
                    "稳妥": f"{common_beat}其以可复核的次序降低无谓损耗。",
                    "机遇": f"{common_beat}其借新交换把个人前路与主线推进相连。",
                    "风险": f"{common_beat}其主动承担冲突代价，以伤势与声名换取突破口。",
                    "气运": f"{common_beat}其保留最后一手，让命数回响决定证据出现的时机。",
                },
            )
        )
    return tuple(phases)


_STORY_ARCS_V1: tuple[StoryArc, ...] = (
    StoryArc(
        key="border-vein-crisis",
        version=1,
        title="裂脉边关",
        worlds=("frontier",),
        fate_tags=("苦修", "灾厄", "边地劫数", "散修"),
        opening="西陲灵脉的衰败并非天灾，最早失踪的商队带走了能够证明人为截脉的账册。",
        unresolved_thread="失踪商队与边境截脉者的关系",
        ally_faction="砺锋院",
        rival_faction="黑潮妖寨",
        neutral_faction="驼铃商栈",
        phases=_phases("边境裂脉", "黑潮妖寨", "驼铃商栈"),
        commitments={
            "稳妥": "护住边营名册中的低阶弟子",
            "机遇": "找到失踪商队留下的账册",
            "风险": "亲自查明裂脉源头",
            "气运": "追索反复出现的黑潮征兆",
        },
        failure_branch="裂脉真相被争夺者掩埋，边营以更多低阶修士填补代价。",
        endings={
            "稳妥": "账册归档，边营重划灵材道路，裂脉之乱被压回可控范围。",
            "机遇": "账册成为其进入更高层议事的凭证，边境格局也因此改写。",
            "风险": "截脉据点被毁，其以重伤换来边关数十年的喘息。",
            "气运": "黑潮征兆与旧账彼此印证，幕后者在自认得势时暴露。",
        },
    ),
    StoryArc(
        key="alliance-old-oath",
        version=1,
        title="盟境旧契",
        worlds=("clan",),
        fate_tags=("宗门", "贵胄", "天命"),
        opening="玄都盟新一轮评席前，一份被删去姓名的旧契重新出现，寒门与世家都声称自己才是受害者。",
        unresolved_thread="旧契被删去的签押者是谁",
        ally_faction="玄都盟外院",
        rival_faction="离火旁宗",
        neutral_faction="司契楼",
        phases=_phases("玄都旧契", "离火旁宗", "司契楼"),
        commitments={
            "稳妥": "保证旧契查验不牵连无辜名册",
            "机遇": "找到旧王城中的原始契印",
            "风险": "公开挑战篡改旧契之人",
            "气运": "保留无名签押的最后线索",
        },
        failure_branch="评席在互相揭短中失控，旧契成为下一轮清算的借口。",
        endings={
            "稳妥": "旧契被重新核验，盟境保住秩序，也为寒门留下可复用的申诉先例。",
            "机遇": "原始契印换来新的评席资格，其成为盟境规则的直接参与者。",
            "风险": "篡契者败露，但公开对抗留下了长期政敌。",
            "气运": "无名签押指向被遗忘的第三方，世家与寒门的旧叙事同时被改写。",
        },
    ),
    StoryArc(
        key="sunken-star-tide",
        version=1,
        title="沉星潮契",
        worlds=("ocean",),
        fate_tags=("天命", "神魂异兆", "散修"),
        opening="沉星礁提前退潮，旧府将现的消息传遍海市，但真正异常的是所有潮图都少了一夜记录。",
        unresolved_thread="潮图缺失之夜发生了什么",
        ally_faction="潮音阁",
        rival_faction="沉星盗盟",
        neutral_faction="听潮船行",
        phases=_phases("沉星异潮", "沉星盗盟", "听潮船行"),
        commitments={
            "稳妥": "护住同行者并补全潮图",
            "机遇": "找到旧府出现的真实潮窗",
            "风险": "抢在盗盟前进入沉星礁",
            "气运": "追随神魂中反复出现的潮声",
        },
        failure_branch="各方误判潮窗，大批灵舟困在退潮后的死礁之间。",
        endings={
            "稳妥": "补全的潮图成为群岛公用航册，旧府之争不再以船队性命下注。",
            "机遇": "其在正确潮窗进入旧府，所得线索足以开启下一段远海生涯。",
            "风险": "其先一步截断盗盟退路，以灵舟尽毁的代价结束争夺。",
            "气运": "缺失之夜的潮声重现，旧府主动避开贪求者而向其开启。",
        },
    ),
    StoryArc(
        key="herb-boundary-blight",
        version=1,
        title="药境早凋",
        worlds=("forest",),
        fate_tags=("苦修", "宗门", "散修"),
        opening="青岚药境的灵草提前开放，却有一批药苗在登记后无声枯萎，药圃边界与旧残阵同时受到怀疑。",
        unresolved_thread="早开灵草与无声枯萎是否出自同一原因",
        ally_faction="青岚谷",
        rival_faction="枯藤社",
        neutral_faction="百草坊",
        phases=_phases("药境早凋", "枯藤社", "百草坊"),
        commitments={
            "稳妥": "保住受影响药圃的低阶苗种",
            "机遇": "找到雾萝山径残阵的药性记录",
            "风险": "查清枯藤社是否越界动手",
            "气运": "追踪只在夜间出现的药香",
        },
        failure_branch="药圃互相封锁，早凋蔓延到主谷，低阶弟子失去最稳定的修行来源。",
        endings={
            "稳妥": "苗种被分区保全，药境以新规度过早凋，损失止于外圃。",
            "机遇": "残阵药性被重新利用，其获得进入内谷研习的资格。",
            "风险": "越界者被揭出，但其也因亲入毒圃留下难消旧伤。",
            "气运": "夜间药香引出地下旧脉，早开与枯萎终于得到同一解释。",
        },
    ),
)


_V2_SUBJECTS = {
    "border-vein-crisis": "边境裂脉",
    "alliance-old-oath": "玄都旧契",
    "sunken-star-tide": "沉星异潮",
    "herb-boundary-blight": "药境早凋",
}


def _story_arc_v2(arc: StoryArc) -> StoryArc:
    subject = _V2_SUBJECTS[arc.key]
    return StoryArc(
        key=arc.key,
        version=2,
        title=f"{arc.title}九章",
        worlds=arc.worlds,
        fate_tags=arc.fate_tags,
        opening=f"{arc.opening} 本局将以九个阶段追踪此事直至证道收束。",
        unresolved_thread=arc.unresolved_thread,
        ally_faction=arc.ally_faction,
        rival_faction=arc.rival_faction,
        neutral_faction=arc.neutral_faction,
        phases=_phases_v2(
            subject,
            arc.ally_faction,
            arc.rival_faction,
            arc.neutral_faction,
        ),
        commitments=arc.commitments,
        failure_branch=f"{arc.failure_branch} 九阶段承诺未能兑现，本局以失败结局收束。",
        endings={
            category: f"{ending} 早年承诺与最终道途在九阶段后得到兑现。"
            for category, ending in arc.endings.items()
        },
    )


_V3_ROUTE_CONSEQUENCES: tuple[tuple[str, tuple[str, str]], ...] = (
    ("稳妥", ("势力", "压力")),
    ("机遇", ("势力", "线索")),
    ("风险", ("压力", "结局条件")),
    ("气运", ("事件权重", "承诺")),
)


def _phases_v3(arc: StoryArc) -> tuple[StoryPhase, ...]:
    """Build a two-event v3 catalog from each of the nine v2 phases."""
    source = _phases_v2(
        _V2_SUBJECTS[arc.key],
        arc.ally_faction,
        arc.rival_faction,
        arc.neutral_faction,
    )
    phases: list[StoryPhase] = []
    for index, phase in enumerate(source, start=1):
        events = (
            StoryEvent(
                id=f"{arc.key}-v3-{index}-record",
                motif=f"{arc.key}-record-{index}",
                summary=f"{phase.title}中，一份可复核的旧录迫使各方重新核对此前说法。",
            ),
            StoryEvent(
                id=f"{arc.key}-v3-{index}-pressure",
                motif=f"{arc.key}-pressure-{index}",
                summary=f"{phase.title}中，外界压力沿着既有矛盾逼近，先前选择开始显出代价。",
            ),
        )
        phases.append(
            replace(
                phase,
                events=events,
                route_consequences=_V3_ROUTE_CONSEQUENCES,
            )
        )
    return tuple(phases)


def _story_arc_v3(arc: StoryArc) -> StoryArc:
    return StoryArc(
        key=arc.key,
        version=3,
        title=f"{arc.title}命数九章",
        worlds=arc.worlds,
        fate_tags=arc.fate_tags,
        opening=f"{arc.opening} 本局以命数承诺和九阶段因果推进，主线收束后仍可进入余波篇章。",
        unresolved_thread=arc.unresolved_thread,
        ally_faction=arc.ally_faction,
        rival_faction=arc.rival_faction,
        neutral_faction=arc.neutral_faction,
        phases=_phases_v3(arc),
        commitments=arc.commitments,
        failure_branch=f"{arc.failure_branch} 两条命数承诺未能同时兑现。",
        endings={
            category: f"{ending} 两条命数承诺在主线收束时得到明确回应。"
            for category, ending in arc.endings.items()
        },
    )


STORY_ARCS: tuple[StoryArc, ...] = (
    *_STORY_ARCS_V1,
    *(_story_arc_v2(arc) for arc in _STORY_ARCS_V1),
    *(_story_arc_v3(arc) for arc in _STORY_ARCS_V1),
)


_ARCS_BY_BINDING = {(arc.key, arc.version): arc for arc in STORY_ARCS}


def story_arc_for_world(
    world_key: str,
    fate_tags: list[str] | tuple[str, ...],
    *,
    content_version: int | None = None,
) -> StoryArc:
    """Select the latest compatible arc without depending on model output."""
    tags = {str(tag).strip() for tag in fate_tags if str(tag).strip()}
    selected_version = story_content_version() if content_version is None else content_version
    candidates = [
        arc for arc in STORY_ARCS if world_key in arc.worlds and arc.version == selected_version
    ]
    if not candidates:
        candidates = [
            arc for arc in STORY_ARCS if "forest" in arc.worlds and arc.version == selected_version
        ]
    return max(candidates, key=lambda arc: (len(tags.intersection(arc.fate_tags)), arc.version))


def story_arc_for_binding(story_key: str, story_version: int) -> StoryArc | None:
    """Resolve an exact version; never silently upgrade an existing save."""
    return _ARCS_BY_BINDING.get((story_key, story_version))


def opening_story_binding(
    world_key: str,
    fate_tags: list[str] | tuple[str, ...],
    *,
    content_version: int | None = None,
    run_seed: str = "",
    character_name: str = "",
) -> dict[str, Any]:
    arc = story_arc_for_world(world_key, fate_tags, content_version=content_version)
    first = arc.phases[0]
    state: dict[str, Any] = {
        "status": "active",
        "phase_key": first.key,
        "phase_title": first.title,
        "stage_goal": first.goal,
        "progress_turns": 0,
        "route_counts": {category: 0 for category in ("稳妥", "机遇", "风险", "气运")},
        "pressure": 0,
        "unresolved_threads": [arc.unresolved_thread, first.thread],
        "faction_attitudes": {
            arc.ally_faction: 0,
            arc.rival_faction: 0,
            arc.neutral_faction: 0,
        },
        "key_promises": [],
        "recent_beats": [],
        "ending": "",
    }
    if arc.version == 3:
        state.update(
            {
                "commitments": _v3_commitments(arc, run_seed, character_name),
                "run_seed": run_seed,
                "recent_motifs": [],
                "consequence_log": [],
                "clue_count": 0,
                "event_weight_modifiers": {"稳妥": 0, "机遇": 0, "风险": 0, "气运": 0},
                "arc_resolution": "",
                "post_arc_turns": 0,
            }
        )
    return {
        "story_key": arc.key,
        "story_version": arc.version,
        "story_title": arc.title,
        "story_opening": arc.opening,
        "story_state": state,
    }


def ensure_story_binding(session: Any, *, content_version: int | None = None) -> None:
    """Bind an unversioned session once; preserve every existing exact binding."""
    if str(getattr(session, "story_key", "") or ""):
        return
    profile = getattr(session, "world_profile", None)
    world_profile = profile if isinstance(profile, dict) else {}
    world_key = str(world_profile.get("world_key") or "").strip()
    if not world_key:
        world_key = world_key_for_name(
            str(world_profile.get("world_name") or getattr(session, "region", ""))
        )
    fate_tags = _fate_tags(world_profile)
    binding = opening_story_binding(
        world_key,
        fate_tags,
        content_version=content_version,
        run_seed=str(getattr(session, "run_seed", "") or ""),
        character_name=str(getattr(session, "char_name", "") or ""),
    )
    session.story_key = binding["story_key"]
    session.story_version = binding["story_version"]
    session.story_state = binding["story_state"]


def story_turn_delta(
    session: Any,
    category: str,
    event: dict[str, Any],
    new_age: int,
    game_over_reason: str = "",
) -> dict[str, Any]:
    """Return the next rule-owned story state without mutating the session."""
    binding = _session_story_binding(session)
    if binding is None:
        return {}
    arc, state = binding
    if state.get("status") == "post_arc":
        return _post_arc_turn_delta(arc, state, category, event, new_age)
    if state.get("status") != "active":
        return {}
    turn = max(1, int(getattr(session, "turn_count", 1) or 1))
    phase = _phase_for_turn(arc, turn)
    route_counts = _route_counts(state)
    route_counts[category] = route_counts.get(category, 0) + 1
    due = turn % 4 == 0
    pressure_change = _pressure_change(category) if due else 0
    v3_effect = _v3_route_effect(state, phase, category, turn) if arc.version == 3 else {}
    pressure_change += int(v3_effect.get("pressure_delta") or 0)
    pressure = max(0, int(state.get("pressure") or 0) + pressure_change)
    v3_resolution = _v3_resolution_context(state, v3_effect)
    attitudes = _faction_attitudes(state, arc)
    _adjust_attitudes(attitudes, arc, category)
    story_event = _v3_story_event(arc, state, phase, category, turn) if arc.version == 3 else None
    status, ending, beat = _story_outcome(
        arc,
        phase,
        category,
        route_counts,
        pressure,
        turn,
        due,
        session,
        event,
        new_age,
        game_over_reason,
        v3_resolution,
    )
    if story_event is not None and due:
        beat = _format_v3_beat(phase, story_event, category, session, event, new_age)
    next_state = _next_story_state(
        state,
        arc,
        phase,
        category,
        route_counts,
        attitudes,
        pressure,
        turn,
        due,
        status,
        ending,
        beat,
    )
    reported_status = status
    if arc.version == 3:
        _apply_v3_turn_state(
            next_state,
            state,
            phase,
            category,
            turn,
            status,
            story_event,
            v3_effect,
        )
        if status in {"resolved", "failed"} and not game_over_reason:
            next_state["status"] = "post_arc"
            next_state["arc_resolution"] = status
            next_state["post_arc_turns"] = 0
            reported_status = "post_arc"
    return {
        "story_update": next_state,
        "story_phase": phase.title,
        "story_goal": phase.goal,
        "story_beat": beat,
        "story_status": reported_status,
    }


def _v3_commitments(arc: StoryArc, run_seed: str, character_name: str) -> list[dict[str, str]]:
    """Generate exactly two catalog-owned commitments for one v3 run."""
    seed = run_seed or f"catalog:{arc.key}:{character_name}"
    categories = ("稳妥", "机遇", "风险", "气运")
    ranked = sorted(
        categories,
        key=lambda category: hashlib.sha256(f"{seed}|{arc.key}|{category}".encode()).hexdigest(),
    )
    commitments: list[dict[str, str]] = []
    for index, category in enumerate(ranked[:2], start=1):
        commitments.append(
            {
                "commitment_id": f"{arc.key}:v3:{index}:{category}",
                "category": category,
                "description": arc.commitments[category],
                "trigger_condition": "前三阶段留下可复核钩子",
                "failure_condition": "第九阶段前未能承受对应代价或压力失控",
                "status": "pending",
            }
        )
    return commitments


def _v3_route_effect(
    state: dict[str, Any], phase: StoryPhase, category: str, turn: int
) -> dict[str, Any]:
    dimensions = dict(phase.route_consequences).get(category, ())
    if category == "稳妥":
        return {"dimensions": dimensions, "pressure_delta": -1}
    if category == "机遇":
        return {"dimensions": dimensions, "clue_delta": 1}
    if category == "风险":
        return {"dimensions": dimensions, "pressure_delta": 1, "risk_mark_delta": 1}
    if category == "气运":
        return {
            "dimensions": dimensions,
            "weight_adjustment": 1 if turn % 2 else -1,
            "commitment_focus_delta": 1,
        }
    return {"dimensions": dimensions}


def _v3_story_event(
    arc: StoryArc,
    state: dict[str, Any],
    phase: StoryPhase,
    category: str,
    turn: int,
) -> StoryEvent | None:
    if not phase.events:
        return None
    recent = _string_list(state.get("recent_motifs"))[-5:]
    candidates = [event for event in phase.events if event.motif not in recent]
    seed = str(state.get("run_seed") or getattr(arc, "key", ""))
    digest = hashlib.sha256(f"{seed}|{arc.key}|{turn}|{category}".encode()).digest()
    if not candidates:
        selected = phase.events[int.from_bytes(digest[:2], "big") % len(phase.events)]
        return replace(selected, motif=f"{selected.motif}:turn-{turn}")
    return candidates[int.from_bytes(digest[:2], "big") % len(candidates)]


def _format_v3_beat(
    phase: StoryPhase,
    story_event: StoryEvent,
    category: str,
    session: Any,
    event: dict[str, Any],
    new_age: int,
) -> str:
    route_beat = phase.beats.get(category) or phase.beats["机遇"]
    return _format_beat(f"{story_event.summary} {route_beat}", session, event, new_age)


def _apply_v3_turn_state(
    next_state: dict[str, Any],
    previous_state: dict[str, Any],
    phase: StoryPhase,
    category: str,
    turn: int,
    status: str,
    story_event: StoryEvent | None,
    effect: dict[str, Any],
) -> None:
    """Record rule-owned v3 commitments, motifs, and route consequences."""
    motifs = _string_list(previous_state.get("recent_motifs"))
    if story_event is not None and turn % 4 == 0:
        motifs.append(story_event.motif)
    next_state["recent_motifs"] = motifs[-5:]
    clues = max(0, int(previous_state.get("clue_count") or 0) + int(effect.get("clue_delta") or 0))
    next_state["clue_count"] = clues
    weights = dict(previous_state.get("event_weight_modifiers") or {})
    weights.setdefault("稳妥", 0)
    weights.setdefault("机遇", 0)
    weights.setdefault("风险", 0)
    weights.setdefault("气运", 0)
    if "weight_adjustment" in effect:
        weights[category] = max(-3, min(3, int(weights[category]) + int(effect["weight_adjustment"])))
    next_state["event_weight_modifiers"] = weights
    next_state["risk_marks"] = max(
        0,
        int(previous_state.get("risk_marks") or 0) + int(effect.get("risk_mark_delta") or 0),
    )
    commitment_focus = max(
        0,
        int(previous_state.get("commitment_focus") or 0)
        + int(effect.get("commitment_focus_delta") or 0),
    )
    next_state["commitment_focus"] = commitment_focus
    next_state["commitments"] = _advance_v3_commitments(
        previous_state.get("commitments"),
        turn,
        status,
        category,
        commitment_focus,
    )
    log_entries = list(previous_state.get("consequence_log") or [])
    dimensions = list(effect.get("dimensions") or ())
    log_entries.append(
        {
            "turn": turn,
            "phase": phase.key,
            "route": category,
            "dimensions": dimensions,
        }
    )
    next_state["consequence_log"] = log_entries[-30:]


def _v3_resolution_context(state: dict[str, Any], effect: dict[str, Any]) -> dict[str, int]:
    return {
        "clue_count": max(
            0,
            int(state.get("clue_count") or 0) + int(effect.get("clue_delta") or 0),
        ),
        "risk_marks": max(
            0,
            int(state.get("risk_marks") or 0) + int(effect.get("risk_mark_delta") or 0),
        ),
    }


def _advance_v3_commitments(
    value: Any,
    turn: int,
    status: str,
    category: str,
    commitment_focus: int,
) -> list[dict[str, str]]:
    items = value if isinstance(value, list) else []
    stage = "hooked" if turn <= 30 else "pressured" if turn <= 60 else "due"
    stage_rank = {"pending": 0, "hooked": 1, "pressured": 2, "due": 3}
    luck_target = commitment_focus % len(items) if items else -1
    out: list[dict[str, str]] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        copied = {str(key): str(raw) for key, raw in item.items() if isinstance(raw, str)}
        if not copied.get("commitment_id"):
            continue
        matches_route = copied.get("category") == category
        if category == "气运" and index == luck_target:
            matches_route = True
        current = copied.get("status") or "pending"
        if matches_route and stage_rank.get(stage, 0) > stage_rank.get(current, 0):
            current = stage
        if status == "resolved":
            current = "fulfilled" if current == "due" else "failed"
        elif status == "failed":
            current = "failed"
        copied["status"] = current
        out.append(copied)
    return out[:2]


def _post_arc_turn_delta(
    arc: StoryArc,
    state: dict[str, Any],
    category: str,
    event: dict[str, Any],
    new_age: int,
) -> dict[str, Any]:
    """Continue v3 after its main arc without replaying the final resolution."""
    turn = max(1, int(state.get("progress_turns") or 0) + 1)
    post_turns = max(1, int(state.get("post_arc_turns") or 0) + 1)
    motifs = _string_list(state.get("recent_motifs"))
    post_events = (
        ("余波整饬", "主线收束后的势力仍在重新分配旧账。"),
        ("远行新讯", "一份不属于旧主线的新讯从远方抵达。"),
        ("旧人回响", "此前同行者带来与旧结局不同的后续选择。"),
    )
    available = [item for item in post_events if item[0] not in motifs] or list(post_events)
    selected = available[(post_turns - 1) % len(available)]
    motifs.append(selected[0])
    next_state = dict(state)
    next_state.update(
        {
            "status": "post_arc",
            "post_arc_turns": post_turns,
            "progress_turns": turn,
            "recent_motifs": motifs[-5:],
            "phase_key": "post_arc",
            "phase_title": "余波",
            "stage_goal": "在主线收束后选择下一段道途，不重演已结算的因果。",
            "recent_beats": [*_string_list(state.get("recent_beats"))[-5:], f"{new_age}岁时，{selected[1]}"],
        }
    )
    beat = f"{new_age}岁时，{selected[1]}"
    return {
        "story_update": next_state,
        "story_phase": "余波",
        "story_goal": next_state["stage_goal"],
        "story_beat": beat,
        "story_status": "post_arc",
    }


def _session_story_binding(session: Any) -> tuple[StoryArc, dict[str, Any]] | None:
    story_key = str(getattr(session, "story_key", "") or "")
    try:
        story_version = int(getattr(session, "story_version", 0) or 0)
    except (TypeError, ValueError):
        story_version = 0
    arc = story_arc_for_binding(story_key, story_version)
    if arc is None:
        return None
    current = getattr(session, "story_state", None)
    state = (
        dict(current)
        if isinstance(current, dict)
        else opening_story_binding(
            arc.worlds[0],
            list(arc.fate_tags),
            content_version=arc.version,
            run_seed=str(getattr(session, "run_seed", "") or ""),
            character_name=str(getattr(session, "char_name", "") or ""),
        )["story_state"]
    )
    return arc, state


def _story_outcome(
    arc: StoryArc,
    phase: StoryPhase,
    category: str,
    route_counts: dict[str, int],
    pressure: int,
    turn: int,
    due: bool,
    session: Any,
    event: dict[str, Any],
    new_age: int,
    game_over_reason: str,
    v3_resolution: dict[str, int],
) -> tuple[str, str, str]:
    beat = (
        _format_beat(phase.beats.get(category) or phase.beats["机遇"], session, event, new_age)
        if due
        else ""
    )
    if game_over_reason:
        return "failed", arc.failure_branch, f"{game_over_reason}{arc.failure_branch}"
    if turn < arc.phases[-1].max_turn:
        return "active", "", beat
    if pressure >= 8:
        return ("failed" if arc.version == 3 else "resolved"), arc.failure_branch, arc.failure_branch
    if arc.version == 3:
        if int(v3_resolution.get("risk_marks") or 0) >= 12:
            return "failed", arc.failure_branch, arc.failure_branch
        if _dominant_route(route_counts) == "机遇" and int(
            v3_resolution.get("clue_count") or 0
        ) < 3:
            return "failed", arc.failure_branch, arc.failure_branch
    ending = arc.endings[_dominant_route(route_counts)]
    return "resolved", ending, ending


def _next_story_state(
    state: dict[str, Any],
    arc: StoryArc,
    phase: StoryPhase,
    category: str,
    route_counts: dict[str, int],
    attitudes: dict[str, int],
    pressure: int,
    turn: int,
    due: bool,
    status: str,
    ending: str,
    beat: str,
) -> dict[str, Any]:
    unresolved = _string_list(state.get("unresolved_threads"))
    if phase.thread not in unresolved:
        unresolved.append(phase.thread)
    promises = _string_list(state.get("key_promises"))
    promise = arc.commitments.get(category, "") if due else ""
    if promise and promise not in promises:
        promises.append(promise)
    recent_beats = _string_list(state.get("recent_beats"))
    if beat:
        recent_beats.append(beat)
    return {
        "status": status,
        "phase_key": phase.key,
        "phase_title": phase.title,
        "stage_goal": phase.goal,
        "progress_turns": turn,
        "route_counts": route_counts,
        "pressure": pressure,
        "unresolved_threads": unresolved[-6:] if status == "active" else [],
        "faction_attitudes": attitudes,
        "key_promises": promises[-6:],
        "recent_beats": recent_beats[-6:],
        "ending": ending,
    }


def _phase_for_turn(arc: StoryArc, turn: int) -> StoryPhase:
    for phase in arc.phases:
        if phase.min_turn <= turn <= phase.max_turn:
            return phase
    return arc.phases[-1]


def story_content_version() -> int:
    raw = os.environ.get("AGENS_STORY_CONTENT_VERSION", str(DEFAULT_STORY_CONTENT_VERSION)).strip()
    try:
        version = int(raw)
    except ValueError as exc:
        raise RuntimeError("AGENS_STORY_CONTENT_VERSION must be 1, 2, or 3.") from exc
    if version not in {1, 2, 3}:
        raise RuntimeError("AGENS_STORY_CONTENT_VERSION must be 1, 2, or 3.")
    return version


def _fate_tags(world_profile: dict[str, Any]) -> list[str]:
    tags = world_profile.get("fate_hooks")
    if isinstance(tags, list):
        return [str(tag) for tag in tags if str(tag).strip()]
    return []


def _route_counts(state: dict[str, Any]) -> dict[str, int]:
    raw = state.get("route_counts")
    out = {category: 0 for category in ("稳妥", "机遇", "风险", "气运")}
    if isinstance(raw, dict):
        for category in out:
            value = raw.get(category)
            if isinstance(value, int) and not isinstance(value, bool):
                out[category] = max(0, value)
    return out


def _pressure_change(category: str) -> int:
    # Pressure is charged only on four-turn story beats. Luck already carries
    # event-level variance, so it does not add unavoidable long-arc pressure.
    return {"稳妥": -1, "机遇": 0, "风险": 2, "气运": 0}.get(category, 0)


def _faction_attitudes(state: dict[str, Any], arc: StoryArc) -> dict[str, int]:
    defaults = {arc.ally_faction: 0, arc.rival_faction: 0, arc.neutral_faction: 0}
    raw = state.get("faction_attitudes")
    if isinstance(raw, dict):
        for key in defaults:
            value = raw.get(key)
            if isinstance(value, int) and not isinstance(value, bool):
                defaults[key] = max(-10, min(10, value))
    return defaults


def _adjust_attitudes(attitudes: dict[str, int], arc: StoryArc, category: str) -> None:
    if category == "稳妥":
        attitudes[arc.ally_faction] = min(10, attitudes[arc.ally_faction] + 1)
    elif category == "机遇":
        attitudes[arc.neutral_faction] = min(10, attitudes[arc.neutral_faction] + 1)
    elif category == "风险":
        attitudes[arc.rival_faction] = max(-10, attitudes[arc.rival_faction] - 1)


def _dominant_route(route_counts: dict[str, int]) -> str:
    order = ("稳妥", "机遇", "风险", "气运")
    return max(order, key=lambda category: (route_counts.get(category, 0), -order.index(category)))


def _format_beat(template: str, session: Any, event: dict[str, Any], new_age: int) -> str:
    event_lore = str(event.get("lore") or "").strip()
    prefix = f"{new_age}岁时，"
    if event_lore:
        return f"{prefix}{template} 同期外界记载：{event_lore}"
    return f"{prefix}{template}"


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]
