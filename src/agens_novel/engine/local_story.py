"""Local preset story fallback for model-unavailable runs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..session.game_session import GameSession
from .choices import normalize_choices


DEFAULT_STORY_ID = "misty_gate"
DEFAULT_NODE_ID = "start"
NO_MATCH_NOTICE = "因果残影未能理解这次自由行动，请选择 A/B/C，或输入与当前处境相关的行动。"


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
                "天道紊乱后，因果残影接住了这一局。你站在雾隐山门前，石阶尽头钟声低回，"
                "接引弟子正在登记新入门的散修。"
            ),
            options=(
                LocalStoryOption(
                    text="上前拜见接引弟子，按规矩登记入门",
                    next_node="outer_gate",
                    delta={
                        "world": {
                            "location": "雾隐山门",
                            "current_scene": "外门接引台",
                            "npcs_present_add": [{"name": "接引弟子", "role": "外门执事"}],
                            "active_quests_add": [{"name": "外门入门试炼", "status": "进行中"}],
                            "lore_add": ["雾隐山门每三年开一次外门试炼。"],
                        },
                        "character": {"insight": "+6"},
                    },
                    result="你递上名册，接引弟子点头，将一枚临时木牌交到你手中。",
                    keywords=("拜见", "登记", "入门", "接引"),
                ),
                LocalStoryOption(
                    text="留在山门石阶吐纳，先稳住丹田气息",
                    next_node="cultivation",
                    delta={"character": {"experience": "+35", "mp": "+5"}},
                    result="你在石阶旁静坐，山雾化作细流入体，丹田渐稳。",
                    keywords=("吐纳", "修炼", "打坐", "丹田"),
                ),
                LocalStoryOption(
                    text="沿灵雾流向观察地势，寻找异常机缘",
                    next_node="herb_path",
                    delta={
                        "world": {"discovered_add": ["雾隐药径"]},
                        "character": {"insight": "+10", "breakthrough_flags_add": ["foundation_aid"]},
                    },
                    result="你发现灵雾总在一条偏僻药径前回旋，似有阵纹残留。",
                    keywords=("观察", "灵雾", "机缘", "地势", "药径"),
                ),
            ),
        ),
        "outer_gate": LocalStoryNode(
            narrative="外门接引台前，弟子们排成三列。执事说，想留下来，须先证明心性和根基。",
            options=(
                LocalStoryOption(
                    text="按执事吩咐完成入门杂役，熟悉宗门规矩",
                    next_node="cultivation",
                    delta={"character": {"experience": "+25", "insight": "+8", "gold": "+3"}},
                    result="你扫净石阶、搬完灵谷，虽是杂役，却摸清了外门的门路。",
                    keywords=("杂役", "规矩", "任务", "执事"),
                ),
                LocalStoryOption(
                    text="请教师兄如何准备筑基",
                    next_node="preparation",
                    delta={
                        "character": {
                            "insight": "+12",
                            "breakthrough_flags_add": ["foundation_aid"],
                            "inventory_add": [{"name": "残页筑基心得", "quantity": 1, "type": "心得"}],
                        },
                    },
                    result="师兄见你态度诚恳，递来一页残旧心得，提醒你莫只闭门苦修。",
                    keywords=("请教", "师兄", "筑基", "心得"),
                ),
                LocalStoryOption(
                    text="接取采药试炼，去山后辨认灵草",
                    next_node="herb_path",
                    delta={
                        "world": {"discovered_add": ["山后药圃"]},
                        "character": {"insight": "+8"},
                    },
                    result="你领到采药竹牌，沿着山后小径进入薄雾。",
                    keywords=("采药", "试炼", "灵草", "山后"),
                ),
            ),
        ),
        "cultivation": LocalStoryNode(
            narrative="夜色落下，外门静室只剩灯火。你能继续积累修为，但瓶颈隐约已在前方。",
            options=(
                LocalStoryOption(
                    text="继续吐纳一夜，稳步提升修为",
                    next_node="cultivation",
                    delta={"character": {"experience": "+45", "mp": "+8"}},
                    result="灵气循环一周天，你的修为稳稳增长。",
                    keywords=("吐纳", "修炼", "闭关", "周天"),
                ),
                LocalStoryOption(
                    text="外出历练，寻找突破所需的心境感悟",
                    next_node="herb_path",
                    delta={"character": {"insight": "+14"}, "world": {"discovered_add": ["雾隐山后径"]}},
                    result="你离开静室，山风一吹，胸中执念反而松动几分。",
                    keywords=("历练", "外出", "感悟", "心境"),
                ),
                LocalStoryOption(
                    text="整理所得，检查是否已具备筑基准备",
                    next_node="preparation",
                    delta={"character": {"insight": "+6"}},
                    result="你摊开木牌、心得和行囊，逐项确认破境所缺。",
                    keywords=("整理", "检查", "筑基", "准备"),
                ),
            ),
        ),
        "herb_path": LocalStoryNode(
            narrative="雾隐药径潮湿幽深，草叶上凝着淡金露珠。远处有兽影，也有一株灵草将开。",
            options=(
                LocalStoryOption(
                    text="谨慎采摘灵草，炼成简易筑基药引",
                    next_node="preparation",
                    delta={
                        "character": {
                            "inventory_add": [{"name": "筑基药引", "quantity": 1, "type": "丹药"}],
                            "breakthrough_flags_add": ["foundation_aid"],
                            "insight": "+10",
                        }
                    },
                    result="你避开兽影，采得灵草根须，按心得炼成一份粗浅药引。",
                    keywords=("采摘", "灵草", "药引", "炼丹"),
                ),
                LocalStoryOption(
                    text="追踪兽影磨炼胆魄",
                    next_node="preparation",
                    delta={"character": {"experience": "+30", "insight": "+12", "hp": "-8"}},
                    result="你与山兽周旋半夜，受了轻伤，却也明白了临危不乱的要义。",
                    keywords=("兽影", "追踪", "战斗", "磨炼"),
                ),
                LocalStoryOption(
                    text="回到外门，请师兄辨认这处药径来历",
                    next_node="outer_gate",
                    delta={"character": {"insight": "+8"}, "world": {"lore_add": ["雾隐药径疑似旧阵残留。"]}},
                    result="师兄听完你的描述，神色凝重，提醒你暂勿深入旧阵。",
                    keywords=("回去", "师兄", "辨认", "来历"),
                ),
            ),
        ),
        "preparation": LocalStoryNode(
            narrative="你已摸到练气瓶颈。此时强行冲关并非不可，但若缺少感悟和护持，极易根基受损。",
            options=(
                LocalStoryOption(
                    text="稳固心境后尝试冲击筑基",
                    next_node="foundation_result",
                    delta={
                        "character": {
                            "experience": "+900",
                            "insight": "+30",
                            "breakthrough_flags_add": ["foundation_aid"],
                        }
                    },
                    result="你点燃药引，按心得守住灵台，开始冲击筑基关隘。",
                    keywords=("突破", "筑基", "冲击", "破境"),
                    breakthrough=True,
                ),
                LocalStoryOption(
                    text="暂缓突破，继续做外门任务积累底蕴",
                    next_node="outer_gate",
                    delta={"character": {"experience": "+35", "insight": "+8", "gold": "+5"}},
                    result="你压下急躁，转身接取新的外门任务。",
                    keywords=("暂缓", "任务", "积累", "底蕴"),
                ),
                LocalStoryOption(
                    text="检查行囊与心得，再确认破境准备",
                    next_node="preparation",
                    delta={"character": {"insight": "+5"}},
                    result="你反复核对药引、心得与气息，心中把握更清晰了些。",
                    keywords=("检查", "行囊", "心得", "准备"),
                ),
            ),
        ),
        "foundation_result": LocalStoryNode(
            narrative="药引化开，灵气如潮。你没有一步登天，但已真正站在筑基门槛前，后续可用“尝试突破”走正式破境判定。",
            options=(
                LocalStoryOption(
                    text="调用正式突破判定，尝试筑基",
                    next_node="foundation_result",
                    delta={
                        "character": {
                            "experience": "+900",
                            "insight": "+30",
                            "breakthrough_flags_add": ["foundation_aid"],
                        }
                    },
                    result="你开始调息，准备由天道正式判定破境成败。",
                    keywords=("正式", "突破", "筑基", "判定"),
                    breakthrough=True,
                ),
                LocalStoryOption(
                    text="继续稳固药力，避免根基虚浮",
                    next_node="preparation",
                    delta={"character": {"experience": "+20", "insight": "+6"}},
                    result="你暂不冒进，让药力在经脉中缓缓沉淀。",
                    keywords=("稳固", "药力", "根基"),
                ),
                LocalStoryOption(
                    text="记录本次本地故事进展并保存",
                    next_node="foundation_result",
                    delta={"world": {"lore_add": ["因果残影已推进至筑基准备节点。"]}},
                    result="你将这段因果记入玉简，方便之后继续。",
                    keywords=("记录", "保存", "玉简"),
                ),
            ),
        ),
    }
}


def local_story_available(story_id: str | None = None) -> bool:
    """Return whether a local story id is registered."""
    return (story_id or DEFAULT_STORY_ID) in _STORIES


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
    """Advance the current local story by A/B/C text or D keyword input."""
    story_key = session.local_story_id or DEFAULT_STORY_ID
    node_key = session.local_story_node_id or DEFAULT_NODE_ID
    node = _node(story_key, node_key)
    option = _match_option(node, action_text)
    if option is None:
        return LocalStoryResult(
            narrative=NO_MATCH_NOTICE,
            choices=[choice.text for choice in node.options],
            delta={},
            matched=False,
        )

    session.local_story_node_id = option.next_node
    next_node = _node(story_key, option.next_node)
    choices = [choice.text for choice in next_node.options]
    return LocalStoryResult(
        narrative=option.result + "\n\n" + next_node.narrative,
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


def _node(story_id: str, node_id: str) -> LocalStoryNode:
    story = _STORIES.get(story_id) or _STORIES[DEFAULT_STORY_ID]
    return story.get(node_id) or story[DEFAULT_NODE_ID]


def _match_option(node: LocalStoryNode, action_text: str) -> LocalStoryOption | None:
    raw = (action_text or "").strip()
    if not raw:
        return None
    normalized_choices = normalize_choices([option.text for option in node.options])
    normalized_action = normalize_choices([raw])
    if normalized_action:
        raw = normalized_action[0]

    for index, option in enumerate(node.options):
        if index < len(normalized_choices) and raw == normalized_choices[index]:
            return option
        if raw == option.text:
            return option

    compact = raw.lower().replace(" ", "")
    for option in node.options:
        if any(keyword.lower().replace(" ", "") in compact for keyword in option.keywords):
            return option
    return None
