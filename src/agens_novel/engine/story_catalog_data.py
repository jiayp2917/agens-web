"""Versioned story-arc data consumed by the story catalog facade."""

from __future__ import annotations

from dataclasses import dataclass, replace

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
