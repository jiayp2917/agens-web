"""Structured world packs and fate-profile helpers for the chronicle mode."""

from __future__ import annotations

from typing import Any

WORLD_PACKS: dict[str, dict[str, Any]] = {
    "frontier": {
        "world_name": "西陲裂土",
        "region": "赤砂边境",
        "region_desc": "灵脉裂谷、边营和流民村寨交错的西陲地带。",
        "location": "荒岭接引营",
        "sect": "砺锋院",
        "sect_desc": "守边宗院，以磨砺心性和护送灵脉为早课。",
        "rival": "黑潮妖寨",
        "rival_desc": "趁灵脉衰落侵扰边境的妖修势力。",
        "neutral": "驼铃商栈",
        "neutral_desc": "只认契约的边地商栈，掌握大量外界情报。",
        "outer_region": "断云古道",
        "outer_desc": "商队、散修和妖兽踪迹交错的边地道路。",
        "risk_hook": "黑潮妖寨的巡哨痕迹",
        "secondary_conflict": "断云古道近月失踪数支灵材商队。",
        "long_conflict": "边境灵脉持续衰败，守边宗院与妖寨都在争夺低阶修士和灵材道路。",
        "opening_hook": "新弟子入册即要面对边营补缺、商队失踪和妖潮试探。",
        "mentor": "边营执事",
        "quest": "边营入册",
        "matched_fates": ("苦修", "灾厄", "边地劫数", "散修"),
        "event_weights": {"稳妥": 2, "机遇": 1, "风险": 3, "气运": 1},
    },
    "clan": {
        "world_name": "玄都盟境",
        "region": "玄都内环",
        "region_desc": "宗门、世家和盟约共同维持秩序的核心地带。",
        "location": "玄都盟外院",
        "sect": "玄都盟",
        "sect_desc": "由宗门和世家共治的盟会，重视门第、契约与潜力。",
        "rival": "离火旁宗",
        "rival_desc": "与玄都盟争夺席位的旁宗势力。",
        "neutral": "司契楼",
        "neutral_desc": "登记盟约、悬赏和家族债务的中立机构。",
        "outer_region": "旧王城",
        "outer_desc": "遗留古朝禁制和家族旧账的繁华废城。",
        "risk_hook": "旧王城未解的家族旧契",
        "secondary_conflict": "盟会评席将近，世家与寒门弟子的矛盾浮上台面。",
        "long_conflict": "盟境表面安稳，宗门席位、世家旧契和寒门上升通道长期互相牵制。",
        "opening_hook": "外院新名册会决定此人站在世家、宗门还是寒门一侧。",
        "mentor": "盟院司录",
        "quest": "外院评席",
        "matched_fates": ("宗门", "贵胄", "天命"),
        "event_weights": {"稳妥": 2, "机遇": 2, "风险": 1, "气运": 2},
    },
    "ocean": {
        "world_name": "沧澜群岛",
        "region": "潮生海市",
        "region_desc": "灵潮涨落决定机缘与风险的群岛海市。",
        "location": "潮音渡口",
        "sect": "潮音阁",
        "sect_desc": "立于群岛灵潮之上的宗门，善观潮汐与气运。",
        "rival": "沉星盗盟",
        "rival_desc": "游走群岛、劫掠灵舟的散修盗盟。",
        "neutral": "听潮船行",
        "neutral_desc": "往来诸岛的船行，消息最灵通。",
        "outer_region": "沉星礁",
        "outer_desc": "灵潮退去后偶现古物和海兽的礁群。",
        "risk_hook": "沉星礁的异常退潮",
        "secondary_conflict": "本月灵潮提前，沉星礁疑有旧府现世。",
        "long_conflict": "灵潮改道让海市、船行、盗盟和潮音阁都在争夺下一次旧府现世。",
        "opening_hook": "听潮者常因一次潮汐改命，也常因误判潮汐葬身海礁。",
        "mentor": "听潮执事",
        "quest": "渡口听潮",
        "matched_fates": ("天命", "神魂异兆", "散修"),
        "event_weights": {"稳妥": 1, "机遇": 3, "风险": 2, "气运": 3},
    },
    "forest": {
        "world_name": "青岚药境",
        "region": "青岚内谷",
        "region_desc": "药田、木法静室和外门庐舍环绕的山谷内域。",
        "location": "青岚药圃",
        "sect": "青岚谷",
        "sect_desc": "以药圃、木法和温养根基闻名的山谷宗门。",
        "rival": "枯藤社",
        "rival_desc": "觊觎药境灵草的外道小社。",
        "neutral": "百草坊",
        "neutral_desc": "交换药材、消息和杂役委托的坊市。",
        "outer_region": "雾萝山径",
        "outer_desc": "灵草与残阵并存的湿润山径。",
        "risk_hook": "雾萝山径的残阵药香",
        "secondary_conflict": "药境外围灵草早开，百草坊和外门弟子都在争先登记。",
        "long_conflict": "药境灵草早开，外门、坊市和外道小社围绕药圃边界暗中角力。",
        "opening_hook": "低阶弟子的每一次稳修、采药和听闻，都可能改变后续筑基准备。",
        "mentor": "药圃执事",
        "quest": "药圃入册",
        "matched_fates": ("苦修", "宗门", "散修"),
        "event_weights": {"稳妥": 3, "机遇": 2, "风险": 1, "气运": 1},
    },
}

WORLD_NAME_TO_KEY = {
    str(pack["world_name"]): key
    for key, pack in WORLD_PACKS.items()
}


def world_pack_for_key(key: str) -> dict[str, Any]:
    """Return a stable world pack, falling back to the forest baseline."""
    return WORLD_PACKS.get(key) or WORLD_PACKS["forest"]


def world_key_for_name(world_name: str) -> str:
    """Map a public world name back to the internal world-pack key."""
    return WORLD_NAME_TO_KEY.get(str(world_name or "").strip(), "forest")
