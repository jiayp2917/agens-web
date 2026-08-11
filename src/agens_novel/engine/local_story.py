"""Local preset story fallback for model-unavailable runs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..game.realm import breakthrough_blocking_effects
from ..session.game_session import GameSession
from .choices import normalize_choices

DEFAULT_STORY_ID = "misty_gate"
DEFAULT_NODE_ID = "start"
NO_MATCH_NOTICE = "这次行动未能对应当前局面，请从当前 A/B/C/D 选项中继续。"
_RECOVERY_MARKERS = ("\u7597\u4f24", "\u8c03\u606f", "\u6062\u590d", "\u7a33\u4f4f\u6839\u57fa")


@dataclass(frozen=True)
class LocalStoryOption:
    text: str
    next_node: str
    delta: dict[str, Any]
    result: str
    keywords: tuple[str, ...] = ()
    breakthrough: bool = False


@dataclass(frozen=True)
class LocalStoryNode:
    narrative: str
    options: tuple[LocalStoryOption, ...]


@dataclass(frozen=True)
class LocalStoryResult:
    narrative: str
    choices: list[str]
    delta: dict[str, Any]
    matched: bool = True
    ended: bool = False
    breakthrough: bool = False


_STORIES: dict[str, dict[str, LocalStoryNode]] = {
    DEFAULT_STORY_ID: {
        "start": LocalStoryNode(
            narrative=(
                "玄历元年，你立在雾隐山门前。"
                "石阶尽头钟声低回，接引弟子正登记新入门的散修。"
            ),
            options=(
                LocalStoryOption(
                    text="按山门规矩登记入门，先求一个稳妥落脚处",
                    next_node="outer_gate",
                    delta={
                        "world": {
                            "location": "雾隐山门",
                            "current_scene": "外门接引台",
                            "npcs_present_add": [{"name": "接引弟子", "role": "外门执事"}],
                            "active_quests_add": [{"name": "外门入门试炼", "status": "进行中"}],
                            "lore_add": ["雾隐山门每三年开一次外门试炼。"],
                        },
                        "character": {"attributes": {"willpower": 1}},
                    },
                    result="玄历元年，你递上名册，接引弟子将一枚临时木牌交到你手中。",
                    keywords=("登记", "入门", "稳妥", "接引"),
                ),
                LocalStoryOption(
                    text="询问外门近况，寻找第一桩可做的机遇",
                    next_node="outer_gate",
                    delta={
                        "world": {
                            "current_scene": "外门接引台",
                            "lore_add": ["外门近来缺人巡查山后药径。"],
                        },
                        "character": {"attributes": {"comprehension": 1}},
                    },
                    result="玄历元年，你从排队弟子口中听见山后药径将开，心里记下一条线索。",
                    keywords=("询问", "机遇", "近况"),
                ),
                LocalStoryOption(
                    text="绕到山门侧径探查雾气来源，冒一次险",
                    next_node="herb_path",
                    delta={
                        "world": {"discovered_add": ["雾隐药径"], "current_scene": "雾隐药径入口"},
                        "character": {"attributes": {"physique": 1, "willpower": 1}},
                    },
                    result="玄历元年，你踏入侧径，湿冷雾气浸过衣摆，前方隐约有残阵微亮。",
                    keywords=("探查", "侧径", "冒险", "风险"),
                ),
                LocalStoryOption(
                    text="随缘听钟声指向，不刻意争抢当前名额",
                    next_node="herb_path",
                    delta={
                        "world": {"discovered_add": ["雾隐药径"]},
                        "character": {"attributes": {"luck": 2}},
                    },
                    result="玄历元年，钟声忽远忽近，你没有争抢，却被雾气引向一条少有人走的小径。",
                    keywords=("随缘", "天命", "气运", "钟声"),
                ),
            ),
        ),
        "outer_gate": LocalStoryNode(
            narrative="玄历二年，外门试炼在接引台前展开。执事说，想留下来，须证明心性、根骨与应变。",
            options=(
                LocalStoryOption(
                    text="按执事吩咐完成杂务，熟悉宗门规矩",
                    next_node="cultivation",
                    delta={"character": {"attributes": {"willpower": 1, "root_bone": 1}}},
                    result="玄历二年，你扫净石阶、搬完灵谷，虽是杂务，却摸清了外门的秩序。",
                    keywords=("杂务", "规矩", "稳妥"),
                ),
                LocalStoryOption(
                    text="请教师兄如何准备筑基，争取提前布置",
                    next_node="preparation",
                    delta={
                        "character": {
                            "breakthrough_flags_add": ["foundation_aid"],
                            "inventory_add": [{"name": "残页筑基心得", "quantity": 1, "type": "心得"}],
                        }
                    },
                    result="玄历二年，师兄见你态度诚恳，递来一页残旧心得，提醒你莫只闭门苦修。",
                    keywords=("请教", "师兄", "筑基", "机遇"),
                ),
                LocalStoryOption(
                    text="接取采药试炼，去山后辨认灵草",
                    next_node="herb_path",
                    delta={
                        "world": {"discovered_add": ["山后药圃"]},
                        "character": {"attributes": {"physique": 1}},
                    },
                    result="玄历二年，你领到采药竹牌，沿着山后小径进入薄雾。",
                    keywords=("采药", "试炼", "风险", "灵草"),
                ),
                LocalStoryOption(
                    text="随缘抽取一枚任务竹牌，任由气运安排",
                    next_node="herb_path",
                    delta={
                        "world": {"discovered_add": ["山后药圃"]},
                        "character": {"attributes": {"luck": 1}},
                    },
                    result="玄历二年，你随手抽中一枚旧竹牌，背面残留的药香指向山后薄雾。",
                    keywords=("随缘", "竹牌", "气运", "天命"),
                ),
            ),
        ),
        "cultivation": LocalStoryNode(
            narrative="玄历三年，外门静室灯火渐少。你能继续稳固根基，也能外出寻找进阶所需的护持。",
            options=(
                LocalStoryOption(
                    text="继续吐纳一夜，稳固根骨与心性",
                    next_node="cultivation",
                    delta={"character": {"attributes": {"root_bone": 1, "willpower": 1}}},
                    result="玄历三年，灵气循环一周天，你的气息更稳，根基也沉了几分。",
                    keywords=("吐纳", "修炼", "稳妥", "根骨"),
                ),
                LocalStoryOption(
                    text="外出历练，寻找筑基所需的护持",
                    next_node="herb_path",
                    delta={"world": {"discovered_add": ["雾隐山后径"]}},
                    result="玄历三年，你离开静室，山风一吹，远处药香像是在招引。",
                    keywords=("历练", "外出", "机遇", "护持"),
                ),
                LocalStoryOption(
                    text="整理所得，检查是否已具备筑基底蕴",
                    next_node="preparation",
                    delta={"character": {"attributes": {"comprehension": 1}}},
                    result="玄历三年，你摊开木牌、心得和行囊，逐项确认进阶所缺。",
                    keywords=("整理", "检查", "准备"),
                ),
                LocalStoryOption(
                    text="顺心而行，跟随一缕突来的灵机",
                    next_node="herb_path",
                    delta={
                        "world": {"discovered_add": ["雾隐山后径"]},
                        "character": {"attributes": {"luck": 2}},
                    },
                    result="玄历三年，你忽然想起山风中的药香，循着灵机走向后山。",
                    keywords=("顺心", "灵机", "随缘", "气运"),
                ),
            ),
        ),
        "herb_path": LocalStoryNode(
            narrative="玄历四年，雾隐药径潮湿幽深，草叶上凝着淡金露珠。远处有兽影，也有一株灵草将开。",
            options=(
                LocalStoryOption(
                    text="谨慎采摘灵草，炼成简易筑基药引",
                    next_node="preparation",
                    delta={
                        "character": {
                            "inventory_add": [{"name": "筑基药引", "quantity": 1, "type": "丹药"}],
                            "breakthrough_flags_add": ["foundation_aid"],
                        }
                    },
                    result="玄历四年，你避开兽影，采得灵草根须，按心得炼成一份粗浅药引。",
                    keywords=("采摘", "灵草", "药引", "稳妥"),
                ),
                LocalStoryOption(
                    text="追踪兽影磨炼胆魄",
                    next_node="preparation",
                    delta={"character": {"attributes": {"physique": 1, "willpower": 1}, "status_effects_add": ["轻伤"]}},
                    result="玄历四年，你与山兽周旋半夜，受了轻伤，却也明白了临危不乱的要义。",
                    keywords=("兽影", "追踪", "磨炼", "风险"),
                ),
                LocalStoryOption(
                    text="回到外门，请师兄辨认这处药径来历",
                    next_node="outer_gate",
                    delta={"world": {"lore_add": ["雾隐药径疑似旧阵残留。"]}},
                    result="玄历四年，师兄听完你的描述，神色凝重，提醒你暂勿深入旧阵。",
                    keywords=("师兄", "辨认", "来历", "机遇"),
                ),
                LocalStoryOption(
                    text="赌一线天命，沿露珠最亮处继续前行",
                    next_node="preparation",
                    delta={
                        "character": {"attributes": {"luck": -1}, "breakthrough_flags_add": ["foundation_aid"]},
                        "world": {"lore_add": ["雾隐药径深处残留一线旧阵机缘。"]},
                    },
                    result="玄历四年，你顺着最亮的露珠前行，险些踏入旧阵，却也看清一处筑基药引的生机。",
                    keywords=("天命", "露珠", "气运", "赌"),
                ),
            ),
        ),
        "preparation": LocalStoryNode(
            narrative="玄历五年，你已摸到练气瓶颈。此时强行冲关并非不可，但最好带着药引、心得或护持。",
            options=(
                LocalStoryOption(
                    text="稳固心境后尝试冲击筑基",
                    next_node="foundation_result",
                    delta={"character": {"breakthrough_flags_add": ["foundation_aid"], "attributes": {"willpower": 1}}},
                    result="玄历五年，你点燃药引，按心得守住灵台，开始冲击筑基关隘。",
                    keywords=("突破", "筑基", "冲击", "稳妥"),
                    breakthrough=True,
                ),
                LocalStoryOption(
                    text="暂缓筑基，继续做外门任务积累底蕴",
                    next_node="outer_gate",
                    delta={"character": {"attributes": {"root_bone": 1, "comprehension": 1}}},
                    result="玄历五年，你压下急躁，转身接取新的外门任务。",
                    keywords=("暂缓", "任务", "积累", "机遇"),
                ),
                LocalStoryOption(
                    text="检查行囊与心得，再确认筑基底蕴",
                    next_node="preparation",
                    delta={"character": {"attributes": {"comprehension": 1}}},
                    result="玄历五年，你反复核对药引、心得与气息，心中把握更清晰了些。",
                    keywords=("检查", "行囊", "心得", "准备"),
                ),
                LocalStoryOption(
                    text="听从心血来潮，冒险冲击筑基",
                    next_node="foundation_result",
                    delta={"character": {"attributes": {"luck": -1}, "breakthrough_flags_add": ["foundation_aid"]}},
                    result="玄历五年，你感到心血来潮，虽仍有风险，却捕捉到一线筑基契机。",
                    keywords=("心血来潮", "天命", "气运", "随缘"),
                    breakthrough=True,
                ),
            ),
        ),
        "foundation_result": LocalStoryNode(
            narrative="玄历六年，药引化开，灵气如潮。你没有一步登天，但已真正站在筑基门槛前。",
            options=(
                LocalStoryOption(
                    text="调用正式突破判定，尝试筑基",
                    next_node="foundation_result",
                    delta={"character": {"breakthrough_flags_add": ["foundation_aid"]}},
                    result="玄历六年，你开始调息，准备由天道正式判定破境成败。",
                    keywords=("正式", "突破", "筑基", "判定"),
                    breakthrough=True,
                ),
                LocalStoryOption(
                    text="继续稳固药力，避免根基虚浮",
                    next_node="preparation",
                    delta={"character": {"attributes": {"root_bone": 1}}},
                    result="玄历六年，你暂不冒进，让药力在经脉中缓缓沉淀。",
                    keywords=("稳固", "药力", "根基"),
                ),
                LocalStoryOption(
                    text="整理本次山门进展并封存玉简",
                    next_node="foundation_result",
                    delta={"world": {"lore_add": ["雾隐山门已记录筑基准备节点。"]}},
                    result="玄历六年，你将这段因果记入玉简，方便之后继续。",
                    keywords=("记录", "保存", "玉简", "封存"),
                ),
                LocalStoryOption(
                    text="随缘静候下一缕进阶机缘",
                    next_node="preparation",
                    delta={"character": {"attributes": {"luck": 1}}},
                    result="玄历六年，你没有强求进阶，只在静候中让气息更贴近天时。",
                    keywords=("随缘", "静候", "进阶", "气运"),
                ),
            ),
        ),
    }
}


def start_local_story(session: GameSession, story_id: str | None = None) -> LocalStoryResult:
    """Enter the local story fallback and return its opening result."""
    story_key = story_id or DEFAULT_STORY_ID
    if story_key not in _STORIES:
        story_key = DEFAULT_STORY_ID
    session.local_story_active = True
    session.local_story_id = story_key
    session.local_story_node_id = DEFAULT_NODE_ID
    node = _node(story_key, DEFAULT_NODE_ID)
    session.last_choices = [option.text for option in node.options]
    return LocalStoryResult(
        narrative=node.narrative,
        choices=list(session.last_choices),
        delta={},
    )


def advance_local_story(session: GameSession, action_text: str) -> LocalStoryResult:
    """Advance the current local story by one fixed option text."""
    story_key = session.local_story_id or DEFAULT_STORY_ID
    node_key = session.local_story_node_id or DEFAULT_NODE_ID
    node = _node(story_key, node_key)
    option = _match_option(node, action_text, session)
    if option is None:
        session.last_choices = [choice.text for choice in node.options]
        return LocalStoryResult(
            narrative=NO_MATCH_NOTICE,
            choices=list(session.last_choices),
            delta={},
            matched=False,
        )

    session.local_story_node_id = option.next_node
    next_node = _node(story_key, option.next_node)
    choices = [choice.text for choice in next_node.options]
    result_text = _local_story_result_text(session, story_key, node_key, option)
    return LocalStoryResult(
        narrative=result_text + "\n\n" + next_node.narrative,
        choices=choices,
        delta=option.delta,
        breakthrough=option.breakthrough,
    )


def current_local_story_choices(session: GameSession) -> list[str]:
    """Return current node choices for save/load recovery."""
    if not session.local_story_active:
        return []
    story_key = session.local_story_id or DEFAULT_STORY_ID
    node_key = session.local_story_node_id or DEFAULT_NODE_ID
    return [option.text for option in _node(story_key, node_key).options]


def available_local_story_choices(
    session: GameSession,
    *,
    breakthrough_allowed: bool,
) -> list[str]:
    """Return visible local-story choices without exposing blocked breakthroughs.

    A local story must remain playable when the realm rules disallow a
    breakthrough.  Generic fallback text cannot be matched back to an authored
    local-story branch, so blocked slots use deterministic local safe actions.
    """
    story_key = session.local_story_id or DEFAULT_STORY_ID
    node_key = session.local_story_node_id or DEFAULT_NODE_ID
    node = _node(story_key, node_key)
    return [
        _visible_option(
            session,
            node_key,
            node,
            index,
            option,
            breakthrough_allowed,
        ).text
        for index, option in enumerate(node.options)
    ]


def _node(story_id: str, node_id: str) -> LocalStoryNode:
    story = _STORIES.get(story_id) or _STORIES[DEFAULT_STORY_ID]
    return story.get(node_id) or story[DEFAULT_NODE_ID]


def _match_option(
    node: LocalStoryNode,
    action_text: str,
    session: GameSession,
) -> LocalStoryOption | None:
    raw = _normalized_action(action_text)
    if not raw:
        return None
    normalized_choices = normalize_choices([option.text for option in node.options])
    displayed_match = _match_displayed_option(node, raw, session, normalized_choices)
    if displayed_match is not None:
        return displayed_match
    authored_match = _match_authored_option(node, raw, normalized_choices)
    if authored_match is not None:
        return authored_match
    return _match_recovery_or_keyword(node, raw, session)


def _normalized_action(action_text: str) -> str:
    raw = (action_text or "").strip()
    normalized_action = normalize_choices([raw])
    return normalized_action[0] if normalized_action else raw


def _match_displayed_option(
    node: LocalStoryNode,
    raw: str,
    session: GameSession,
    normalized_choices: list[str],
) -> LocalStoryOption | None:
    displayed_choices = normalize_choices(session.last_choices)
    if len(displayed_choices) != len(node.options):
        return None
    for index, displayed in enumerate(displayed_choices):
        if raw == displayed:
            return _displayed_option(node, session, normalized_choices, index, displayed)
    return None


def _displayed_option(
    node: LocalStoryNode,
    session: GameSession,
    normalized_choices: list[str],
    index: int,
    displayed: str,
) -> LocalStoryOption:
    option = node.options[index]
    if index >= len(normalized_choices) or displayed == normalized_choices[index]:
        return option
    if index == 2 and any(item.breakthrough for item in node.options):
        return _required_breakthrough_option(session.local_story_node_id, node)
    if option.breakthrough:
        return _blocked_breakthrough_option(session, session.local_story_node_id, index)
    return option


def _match_authored_option(
    node: LocalStoryNode,
    raw: str,
    normalized_choices: list[str],
) -> LocalStoryOption | None:
    for index, option in enumerate(node.options):
        if index < len(normalized_choices) and raw == normalized_choices[index]:
            return option
        if raw == option.text:
            return option
    return None


def _match_recovery_or_keyword(
    node: LocalStoryNode,
    raw: str,
    session: GameSession,
) -> LocalStoryOption | None:
    compact = raw.lower().replace(" ", "")
    if breakthrough_blocking_effects(session.status_effects) and any(
        marker in compact for marker in _RECOVERY_MARKERS
    ):
        return next((option for option in node.options if not option.breakthrough), None)
    for option in node.options:
        if any(keyword.lower().replace(" ", "") in compact for keyword in option.keywords):
            return option
    return None


def _visible_option(
    session: GameSession,
    node_key: str,
    node: LocalStoryNode,
    index: int,
    option: LocalStoryOption,
    breakthrough_allowed: bool,
) -> LocalStoryOption:
    if breakthrough_allowed and index == 2 and not option.breakthrough:
        return _required_breakthrough_option(node_key, node)
    if not option.breakthrough:
        return option
    return _blocked_breakthrough_option(session, node_key, index)


def _required_breakthrough_option(
    node_key: str,
    node: LocalStoryNode,
) -> LocalStoryOption:
    """Place the available local breakthrough on the fixed C route."""
    source = next(option for option in node.options if option.breakthrough)
    return LocalStoryOption(
        text="正式冲击筑基，承担破境失败风险",
        next_node=source.next_node,
        delta=source.delta,
        result=source.result,
        keywords=("正式", "冲击", "破境", "风险"),
        breakthrough=True,
    )


def _blocked_breakthrough_option(
    session: GameSession,
    node_key: str,
    index: int,
) -> LocalStoryOption:
    """Build a slot-preserving authored action for a blocked breakthrough."""
    safe_actions = (
        (
            "静心调息，先把根基稳住",
            {"character": {"attributes": {"willpower": 1}}},
            "你收束躁动气息，先让根基重新平稳下来。",
            ("调息", "根基", "稳住"),
        ),
        (
            "向同门请教，补足眼前修行准备",
            {"character": {"attributes": {"comprehension": 1}}},
            "你向同门请教细处，把眼前的修行准备补得更扎实。",
            ("请教", "准备", "修行"),
        ),
        (
            "整理药引与心得，补足修行准备",
            {"character": {"attributes": {"comprehension": 1}}},
            "你整理药引与心得，把缺漏逐项记下，准备从容补足。",
            ("整理", "药引", "心得"),
        ),
        (
            "顺应天时，静候气机自然成熟",
            {"character": {"attributes": {"luck": 1}}},
            "你顺应天时静候气机，未强求结果，心境反而清明了些。",
            ("顺应", "天时", "静候"),
        ),
    )
    text, delta, result, initial_keywords = safe_actions[
        min(max(index, 0), len(safe_actions) - 1)
    ]
    keywords: tuple[str, ...] = tuple(initial_keywords)
    blockers = breakthrough_blocking_effects(session.status_effects)
    if index == 0 and blockers:
        joined = "、".join(blockers)
        text = f"疗伤调息，先化解{joined}并稳住根基"
        result = f"你先以药力调息，逐步化解{joined}，不再勉强前行。"
        keywords = ("疗伤", "调息", "化解", "根基")
    return LocalStoryOption(
        text=text,
        next_node=node_key or DEFAULT_NODE_ID,
        delta=delta,
        result=result,
        keywords=keywords,
    )


def _local_story_result_text(
    session: GameSession,
    story_key: str,
    node_key: str,
    option: LocalStoryOption,
) -> str:
    if option.next_node != node_key:
        return option.result

    repeat_counts = getattr(session, "_local_story_repeat_counts", {})
    if not isinstance(repeat_counts, dict):
        repeat_counts = {}
    count_key = f"{story_key}:{node_key}:{option.text}"
    repeat_count = int(repeat_counts.get(count_key) or 0) + 1
    repeat_counts[count_key] = repeat_count
    session._local_story_repeat_counts = repeat_counts

    if repeat_count <= 1:
        return option.result
    return f"{option.result}（第{repeat_count}次复盘此路，你把前一夜的散乱处又收束了一分。）"
