"""Data-driven chronicle events for ordinary turns."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..game.constants import format_realm_name
from .world_catalog import world_key_for_name, world_pack_for_key


@dataclass(frozen=True)
class ChronicleEvent:
    id: str
    category: str
    event_type: str
    worlds: tuple[str, ...]
    fate_tags: tuple[str, ...]
    min_turn: int
    max_turn: int
    weight: int
    stage_goal: str
    lore_template: str
    allowed_delta_types: tuple[str, ...]
    choice_hints: tuple[str, str, str, str]


def select_chronicle_event(session: Any, category: str, new_age: int) -> dict[str, Any]:
    """Select one deterministic event context for this turn."""
    world_key = _session_world_key(session)
    fate_scores = _session_fate_scores(session)
    turn = max(1, int(getattr(session, "turn_count", 1) or 1))
    candidates = [
        event for event in CHRONICLE_EVENTS
        if event.category == category
        and (not event.worlds or world_key in event.worlds)
        and event.min_turn <= turn <= event.max_turn
    ]
    if not candidates:
        candidates = [
            event for event in CHRONICLE_EVENTS
            if event.category == category
            and (not event.worlds or world_key in event.worlds)
        ]
    if not candidates:
        candidates = [event for event in CHRONICLE_EVENTS if event.category == category]
    if not candidates:
        candidates = [CHRONICLE_EVENTS[0]]

    weights = _world_event_weights(session, world_key)
    scored: list[tuple[int, str, ChronicleEvent]] = []
    for event in candidates:
        score = event.weight + int(weights.get(category, 0))
        score += sum(fate_scores.get(tag, 0) for tag in event.fate_tags)
        scored.append((score, event.id, event))
    scored.sort(key=lambda item: (-item[0], item[1]))
    recent_ids = _recent_event_ids(session)
    selectable = [item for item in scored if item[2].id not in recent_ids] or scored
    window = selectable[: min(4, len(selectable))]
    phase_index = max(0, (turn // 4) - 1)
    _, _, selected = window[phase_index % len(window)]
    lore = _format_event_lore(selected, session, new_age, world_key)
    return {
        "id": selected.id,
        "category": selected.category,
        "event_type": selected.event_type,
        "world_key": world_key,
        "stage_goal": selected.stage_goal,
        "lore": lore,
        "allowed_delta_types": list(selected.allowed_delta_types),
        "choice_hints": list(selected.choice_hints),
        "matched_fates": [tag for tag in selected.fate_tags if tag in fate_scores],
    }


def stage_feedback_due(session: Any) -> bool:
    """Return whether this turn should persist a stage-feedback lore fact."""
    turn = int(getattr(session, "turn_count", 0) or 0)
    return turn > 0 and turn % 4 == 0


def event_summary(event: dict[str, Any]) -> str:
    """Return compact event context for narrator prompts."""
    if not event:
        return ""
    allowed = "、".join(str(item) for item in event.get("allowed_delta_types") or [])
    hints = "；".join(str(item) for item in event.get("choice_hints") or [])
    return (
        f"编年史事件：{event.get('lore', '')}"
        f" 阶段目标：{event.get('stage_goal', '')}"
        f" 可承接状态：{allowed or '仅外界情报'}。"
        f" 下一步选项提示：{hints}"
    )


def _format_event_lore(event: ChronicleEvent, session: Any, new_age: int, world_key: str) -> str:
    pack = world_pack_for_key(world_key)
    world_profile = getattr(session, "world_profile", None)
    current_conflicts = []
    if isinstance(world_profile, dict) and isinstance(world_profile.get("current_conflicts"), list):
        current_conflicts = [str(item) for item in world_profile["current_conflicts"] if str(item).strip()]
    conflict = current_conflicts[0] if current_conflicts else str(pack.get("secondary_conflict") or "")
    stage = int(getattr(session, "realm_stage", 1) or 1)
    realm = getattr(session, "realm", "练气") or "练气"
    lore = event.lore_template.format(
        age=new_age,
        location=getattr(session, "location", "") or pack["location"],
        region=getattr(session, "region", "") or pack["world_name"],
        sect=pack["sect"],
        rival=pack["rival"],
        neutral=pack["neutral"],
        outer_region=pack["outer_region"],
        conflict=conflict,
        realm=realm,
        realm_label=format_realm_name(realm, stage),
    )
    return f"{lore} {_turn_texture(session)}"


def _recent_event_ids(session: Any, *, limit: int = 3) -> set[str]:
    out: set[str] = set()
    history = getattr(session, "turn_history", []) or []
    if not isinstance(history, list):
        return out
    for entry in reversed(history[-limit:]):
        if not isinstance(entry, dict):
            continue
        delta = entry.get("delta")
        meta = delta.get("meta") if isinstance(delta, dict) else {}
        event_id = str(meta.get("event_id") or "").strip() if isinstance(meta, dict) else ""
        if event_id:
            out.add(event_id)
    return out


def _turn_texture(session: Any) -> str:
    turn = max(1, int(getattr(session, "turn_count", 1) or 1))
    textures = (
        "\u672c\u6b21\u8bb0\u4e3a\u6668\u8bfe\u4fa7\u7b14\uff0c\u53ea\u4f5c\u9636\u6bb5\u65c1\u8bc1\u3002",
        "\u672c\u6b21\u8bb0\u4e3a\u5348\u8bb2\u5f55\uff0c\u4fa7\u91cd\u5916\u95e8\u79e9\u5e8f\u3002",
        "\u672c\u6b21\u8bb0\u4e3a\u66ae\u7701\u6863\uff0c\u4fa7\u91cd\u4eba\u4e8b\u98ce\u5411\u3002",
        "\u672c\u6b21\u8bb0\u4e3a\u6708\u8003\u7b7e\uff0c\u4fa7\u91cd\u4fee\u884c\u538b\u529b\u3002",
        "\u672c\u6b21\u8bb0\u4e3a\u5de1\u518c\u7b14\uff0c\u4fa7\u91cd\u5730\u65b9\u53d8\u5316\u3002",
        "\u672c\u6b21\u8bb0\u4e3a\u95ee\u9053\u6761\uff0c\u4fa7\u91cd\u540e\u7eed\u9009\u62e9\u3002",
        "\u672c\u6b21\u8bb0\u4e3a\u8bd5\u827a\u5f55\uff0c\u4fa7\u91cd\u540c\u8f88\u6bd4\u7167\u3002",
        "\u672c\u6b21\u8bb0\u4e3a\u5b88\u6212\u7b3a\uff0c\u4fa7\u91cd\u98ce\u9669\u8fb9\u754c\u3002",
        "\u672c\u6b21\u8bb0\u4e3a\u89c2\u6f6e\u95fb\uff0c\u4fa7\u91cd\u52bf\u529b\u6d41\u5411\u3002",
        "\u672c\u6b21\u8bb0\u4e3a\u542c\u949f\u5fd7\uff0c\u4fa7\u91cd\u56e0\u679c\u53d8\u5316\u3002",
        "\u672c\u6b21\u8bb0\u4e3a\u6821\u7c4d\u9875\uff0c\u4fa7\u91cd\u8eab\u4efd\u4f4d\u7f6e\u3002",
        "\u672c\u6b21\u8bb0\u4e3a\u590d\u76d8\u672d\uff0c\u4fa7\u91cd\u77ed\u677f\u8865\u8db3\u3002",
    )
    return textures[(turn - 1) % len(textures)]


def _session_world_key(session: Any) -> str:
    world_profile = getattr(session, "world_profile", None)
    if isinstance(world_profile, dict):
        key = str(world_profile.get("world_key") or "").strip()
        if key:
            return key
        return world_key_for_name(str(world_profile.get("world_name") or getattr(session, "region", "")))
    return world_key_for_name(str(getattr(session, "region", "") or ""))


def _session_fate_scores(session: Any) -> dict[str, int]:
    world_profile = getattr(session, "world_profile", None)
    out: dict[str, int] = {}
    if isinstance(world_profile, dict):
        fate_profile = world_profile.get("fate_profile")
        if isinstance(fate_profile, list):
            for item in fate_profile:
                if isinstance(item, dict):
                    label = str(item.get("label") or item.get("id") or "").strip()
                    if label:
                        try:
                            out[label] = max(1, int(item.get("score") or 1))
                        except (TypeError, ValueError):
                            out[label] = 1
        if not out and isinstance(world_profile.get("fate_hooks"), list):
            for label in world_profile["fate_hooks"]:
                text = str(label or "").strip()
                if text:
                    out[text] = 1
    return out


def _world_event_weights(session: Any, world_key: str) -> dict[str, int]:
    world_profile = getattr(session, "world_profile", None)
    if isinstance(world_profile, dict) and isinstance(world_profile.get("event_weights"), dict):
        return {
            str(key): int(value)
            for key, value in world_profile["event_weights"].items()
            if isinstance(value, int) and not isinstance(value, bool)
        }
    pack = world_pack_for_key(world_key)
    return dict(pack.get("event_weights") or {})


CHRONICLE_EVENTS: tuple[ChronicleEvent, ...] = (
    ChronicleEvent(
        id="steady-root-ledger",
        category="稳妥",
        event_type="stage",
        worlds=(),
        fate_tags=("苦修", "宗门"),
        min_turn=1,
        max_turn=120,
        weight=5,
        stage_goal="稳住根基，积累下一次小境界推进的依据",
        lore_template="{sect}重修低阶课业簿，{location}弟子开始按月比对吐纳进度，{realm_label}根基有了可见标尺。",
        allowed_delta_types=("attributes", "lore_add"),
        choice_hints=("继续温养根基", "请教师门课业", "接取低阶差事", "随缘旁听讲法"),
    ),
    ChronicleEvent(
        id="steady-world-ledger",
        category="稳妥",
        event_type="ordinary",
        worlds=("clan", "forest"),
        fate_tags=("宗门", "贵胄"),
        min_turn=1,
        max_turn=120,
        weight=4,
        stage_goal="通过宗门秩序获得稳定反馈，而非反复闭关",
        lore_template="{neutral}更新名册，{sect}与{rival}的暗中试探被写进外门告示。",
        allowed_delta_types=("lore_add", "npcs_present_add"),
        choice_hints=("整理名册关系", "拜访司录执事", "查阅旧告示", "随缘留意签押"),
    ),
    ChronicleEvent(
        id="steady-teaching-round",
        category="稳妥",
        event_type="ordinary",
        worlds=(),
        fate_tags=("苦修", "宗门"),
        min_turn=1,
        max_turn=120,
        weight=4,
        stage_goal="把稳妥路线写成可见的课业、同门与反馈，而不是反复闭关",
        lore_template="{sect}轮值讲师重排低阶课表，{location}弟子被分入不同讲席，{realm_label}修行从独自吐纳转为按册核验。",
        allowed_delta_types=("lore_add", "npcs_present_add", "attributes"),
        choice_hints=("按课表补足短板", "请教师兄课业", "整理同门讲义", "随缘旁听新讲席"),
    ),
    ChronicleEvent(
        id="steady-duty-ledger",
        category="稳妥",
        event_type="stage",
        worlds=(),
        fate_tags=("苦修", "贵胄"),
        min_turn=1,
        max_turn=120,
        weight=3,
        stage_goal="用稳定差事提供阶段反馈和外界变化",
        lore_template="{neutral}将{outer_region}近月收支抄送{sect}，{location}低阶弟子开始以差事换取讲评名额。",
        allowed_delta_types=("lore_add", "npcs_present_add", "breakthrough_flags_add"),
        choice_hints=("接一桩稳妥差事", "核对外界账册", "护送同门交割", "随缘观察差事流向"),
    ),
    ChronicleEvent(
        id="opportunity-market-rumor",
        category="机遇",
        event_type="ordinary",
        worlds=(),
        fate_tags=("散修", "天命", "贵胄"),
        min_turn=1,
        max_turn=120,
        weight=5,
        stage_goal="从外界情报中选择下一段修行方向",
        lore_template="{neutral}传出新消息：{conflict}，同门与散修都在打听可入局的门路。",
        allowed_delta_types=("lore_add", "discovered_add", "npcs_present_add"),
        choice_hints=("打听消息来源", "拜访知情修士", "追查传闻地点", "随缘听一则旧签"),
    ),
    ChronicleEvent(
        id="opportunity-fate-hook",
        category="机遇",
        event_type="stage",
        worlds=("ocean", "clan"),
        fate_tags=("天命", "神魂异兆"),
        min_turn=1,
        max_turn=120,
        weight=4,
        stage_goal="把命数线索转化为可选择的中风险机缘",
        lore_template="{age}岁这一年，{region}星潮有异，{outer_region}的旧闻重新被{neutral}提起。",
        allowed_delta_types=("lore_add", "discovered_add"),
        choice_hints=("核对旧闻", "寻访见证者", "前往边缘查探", "随星潮而行"),
    ),
    ChronicleEvent(
        id="opportunity-mentor-route",
        category="机遇",
        event_type="ordinary",
        worlds=(),
        fate_tags=("宗门", "苦修"),
        min_turn=1,
        max_turn=120,
        weight=4,
        stage_goal="通过人物关系获得下一阶段线索",
        lore_template="{sect}有执事讲评近年低阶弟子的得失，{location}不少人开始寻找可请教的前辈。",
        allowed_delta_types=("lore_add", "npcs_present_add"),
        choice_hints=("请教执事", "结交同门", "接下引荐差事", "随缘旁听"),
    ),
    ChronicleEvent(
        id="opportunity-outer-place",
        category="机遇",
        event_type="stage",
        worlds=(),
        fate_tags=("散修", "贵胄"),
        min_turn=1,
        max_turn=120,
        weight=3,
        stage_goal="把外界地点转化为可追踪的阶段线索",
        lore_template="{outer_region}的旧路重新有人通行，{neutral}称那里或许能补足低阶修士的短板。",
        allowed_delta_types=("lore_add", "discovered_add"),
        choice_hints=("核对路引", "寻找同行者", "前往旧路边缘", "随缘等风声"),
    ),
    ChronicleEvent(
        id="risk-border-pressure",
        category="风险",
        event_type="risk",
        worlds=("frontier",),
        fate_tags=("灾厄", "边地劫数", "苦修"),
        min_turn=1,
        max_turn=120,
        weight=6,
        stage_goal="让风险路线带来真实压力，而不是重复突破按钮",
        lore_template="{rival}逼近{outer_region}，{sect}临时调派低阶弟子补巡，{location}的风险被写上明榜。",
        allowed_delta_types=("lore_add", "status_effects_add", "breakthrough_flags_add"),
        choice_hints=("领取补巡差事", "寻找护持同伴", "深入边缘查探", "随战报改道"),
    ),
    ChronicleEvent(
        id="risk-forbidden-edge",
        category="风险",
        event_type="risk",
        worlds=(),
        fate_tags=("灾厄", "散修"),
        min_turn=1,
        max_turn=120,
        weight=4,
        stage_goal="提供禁地/斗法/伤势压力，避免无代价冒险",
        lore_template="{outer_region}近年异动加重，{neutral}开始高价收购护身符与疗伤药。",
        allowed_delta_types=("lore_add", "status_effects_add", "inventory_add"),
        choice_hints=("准备护身物", "寻找同伴同行", "冒险探查异动", "随缘避开锋芒"),
    ),
    ChronicleEvent(
        id="risk-duel-summons",
        category="风险",
        event_type="risk",
        worlds=(),
        fate_tags=("灾厄", "散修", "边地劫数"),
        min_turn=1,
        max_turn=120,
        weight=4,
        stage_goal="让斗法压力以可选择的风险出现，并由规则承接伤势或因果",
        lore_template="{rival}门下有人在{outer_region}设下约斗榜，{sect}执事提醒低阶修士不得把一时意气当作破境捷径。",
        allowed_delta_types=("lore_add", "status_effects_add", "npcs_present_add"),
        choice_hints=("避开约斗稳住气息", "打听约斗来历", "冒险赴榜试探", "随缘观望胜负"),
    ),
    ChronicleEvent(
        id="risk-old-wound-sign",
        category="风险",
        event_type="stage",
        worlds=(),
        fate_tags=("灾厄", "苦修"),
        min_turn=1,
        max_turn=120,
        weight=3,
        stage_goal="把伤势、寿元和高龄压力写入路线风险",
        lore_template="{location}近日多有低阶弟子旧伤复发，{neutral}的医修把{conflict}列为近期外出禁忌。",
        allowed_delta_types=("lore_add", "status_effects_add", "lifespan"),
        choice_hints=("调养旧伤", "寻医问药", "强行外出查探", "随缘听从医嘱"),
    ),
    ChronicleEvent(
        id="luck-sign-turns",
        category="气运",
        event_type="fate",
        worlds=(),
        fate_tags=("天命", "神魂异兆", "灾厄"),
        min_turn=1,
        max_turn=120,
        weight=5,
        stage_goal="让气运路线产生可感知的命数摇摆",
        lore_template="{age}岁这一年，{region}流传一则无名签文，有人因它得机缘，也有人因它遭反噬。",
        allowed_delta_types=("lore_add", "attributes", "status_effects_add"),
        choice_hints=("按签文低调行事", "寻找解签之人", "赌一次未知机缘", "顺其自然"),
    ),
    ChronicleEvent(
        id="luck-world-echo",
        category="气运",
        event_type="stage",
        worlds=("ocean", "frontier"),
        fate_tags=("天命", "边地劫数"),
        min_turn=1,
        max_turn=120,
        weight=4,
        stage_goal="把命数变化写入外界，而非只给随机奖励",
        lore_template="{conflict}的传闻被重新解读，{neutral}称近期因果易变，低阶修士最好早做取舍。",
        allowed_delta_types=("lore_add", "breakthrough_flags_add"),
        choice_hints=("记录传闻", "结交消息灵通者", "趁乱试探", "随缘等下一次征兆"),
    ),
    ChronicleEvent(
        id="luck-small-omen",
        category="气运",
        event_type="fate",
        worlds=(),
        fate_tags=("天命", "神魂异兆"),
        min_turn=1,
        max_turn=120,
        weight=4,
        stage_goal="让气运路线出现小兆头和后续钩子，而非固定随机奖惩",
        lore_template="{location}夜半有短暂灵光掠过，{neutral}只把它记为小兆，不许低阶弟子据此自称得道。",
        allowed_delta_types=("lore_add", "discovered_add", "attributes"),
        choice_hints=("低调记录小兆", "询问懂星象者", "追随灵光方向", "随缘等待回响"),
    ),
    ChronicleEvent(
        id="luck-debt-ledger",
        category="气运",
        event_type="ordinary",
        worlds=(),
        fate_tags=("灾厄", "贵胄", "边地劫数"),
        min_turn=1,
        max_turn=120,
        weight=3,
        stage_goal="把气运写成因果账和取舍压力",
        lore_template="{sect}外门新贴因果账，称{outer_region}近来得失相抵，受益者日后多半也要偿一笔人情。",
        allowed_delta_types=("lore_add", "npcs_present_add", "status_effects_add"),
        choice_hints=("记下因果账", "拜访账册执事", "冒险接下人情", "随缘不问来处"),
    ),
)
