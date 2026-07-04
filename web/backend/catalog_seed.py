"""Catalog seed data for the xianxia cultivation simulator.

All content is abstract xianxia tropes — no specific copyrighted characters,
sect names, or storylines. Used to populate catalog tables on first run.
"""

from __future__ import annotations

import uuid
from typing import Any

from .database_common import decode_json_fields

# ── catalog_talents ──────────────────────────────────────────────────────────
# rarity: 白 / 绿 / 蓝 / 紫 / 橙 / 红 (6-tier per GAME_MODE_SPEC §11)
# attribute_mods: small flat adjustments on the v5 0-10 attribute scale
# tags: labels for story/event matching

SEED_TALENTS: list[dict[str, Any]] = [
    {
        "id": str(uuid.uuid4()),
        "name": "平平无奇",
        "rarity": "白",
        "description": "无特别天赋，但胜在没有明显短板，适应力强。",
        "attribute_mods": {},
        "tags": ["均衡"],
    },
    {
        "id": str(uuid.uuid4()),
        "name": "草木亲和",
        "rarity": "白",
        "description": "天生与草木灵气亲近，炼丹采药事半功倍。",
        "attribute_mods": {"soul": 1, "comprehension": 1},
        "tags": ["炼丹", "灵植", "治愈"],
    },
    {
        "id": str(uuid.uuid4()),
        "name": "剑心微明",
        "rarity": "蓝",
        "description": "心中自有一缕剑意，修炼剑道功法更快，斗法时剑招更利。",
        "attribute_mods": {"physique": 1, "willpower": 1},
        "tags": ["剑道", "杀伐", "斗法"],
    },
    {
        "id": str(uuid.uuid4()),
        "name": "惊雷骨",
        "rarity": "蓝",
        "description": "骨骼天生蕴藏雷属性，引雷淬体事半功倍，突破瓶颈时有额外助力。",
        "attribute_mods": {"physique": 2, "root_bone": 1},
        "tags": ["雷法", "淬体", "突破"],
    },
    {
        "id": str(uuid.uuid4()),
        "name": "天命道胎",
        "rarity": "橙",
        "description": "传说中天生近道的体质，悟性远超常人，修炼一日千里。但天道忌满，气运起伏极大。",
        "attribute_mods": {"comprehension": 3, "soul": 2, "luck": -2},
        "tags": ["悟道", "机缘", "天妒"],
    },
    {
        "id": str(uuid.uuid4()),
        "name": "丹心不灭",
        "rarity": "蓝",
        "description": "心脉坚韧异于常人，重伤恢复更快，心魔劫中更易守住本心。",
        "attribute_mods": {"willpower": 2, "physique": 1},
        "tags": ["心性", "恢复", "渡劫"],
    },
    {
        "id": str(uuid.uuid4()),
        "name": "阵法通明",
        "rarity": "蓝",
        "description": "对阵法禁制有天然直觉，破解遗迹禁制、布置洞府阵法均占优势。",
        "attribute_mods": {"comprehension": 2, "soul": 1},
        "tags": ["阵法", "禁制", "探索"],
    },
    {
        "id": str(uuid.uuid4()),
        "name": "魔心潜伏",
        "rarity": "蓝",
        "description": "体内潜藏一丝魔性，战力提升时心魔亦随之壮大。修炼魔道功法无副作用，但正道功法事倍功半。",
        "attribute_mods": {"physique": 2, "willpower": -1, "luck": -1},
        "tags": ["魔道", "杀伐", "心魔"],
    },
    {
        "id": str(uuid.uuid4()),
        "name": "福缘深厚",
        "rarity": "蓝",
        "description": "天生福缘加身，行走在外更容易遇到贵人机缘，但因果纠缠亦多。",
        "attribute_mods": {"luck": 2},
        "tags": ["机缘", "因果", "贵人"],
    },
    {
        "id": str(uuid.uuid4()),
        "name": "万法归宗",
        "rarity": "橙",
        "description": "万法皆可通，不受灵根属性限制，任何属性功法均可修炼至大成。",
        "attribute_mods": {"comprehension": 2, "root_bone": 2},
        "tags": ["万法", "无属性", "悟道"],
    },
]


# ── catalog_family_backgrounds ───────────────────────────────────────────────

SEED_FAMILY_BACKGROUNDS: list[dict[str, Any]] = [
    {
        "id": str(uuid.uuid4()),
        "name": "凡人孤儿",
        "rarity": "白",
        "description": "出身平凡，无父无母，在乡野间靠自身努力长大。没有家族支持，但也没有家族恩怨的牵绊。",
        "initial_resources": {"items": ["粗布衣衫"]},
        "initial_risks": ["无依无靠"],
        "story_tags": ["散修", "草根", "逆境"],
    },
    {
        "id": str(uuid.uuid4()),
        "name": "寒门子弟",
        "rarity": "白",
        "description": "出身普通农家或小商贩家庭，家人省吃俭用送你踏上仙途。虽无显赫背景，却有家人殷切期盼。",
        "initial_resources": {"items": ["家传护身符"]},
        "initial_risks": ["家中有牵挂"],
        "story_tags": ["孝道", "凡尘", "责任"],
    },
    {
        "id": str(uuid.uuid4()),
        "name": "修仙小族",
        "rarity": "蓝",
        "description": "出身于一个没落的小修仙家族，族中尚存几部残缺功法和几件低阶法器。",
        "initial_resources": {"items": ["残缺功法残卷", "低阶储物袋"]},
        "initial_risks": ["族中期望过高", "旧日仇怨"],
        "story_tags": ["家族", "传承", "复兴"],
    },
    {
        "id": str(uuid.uuid4()),
        "name": "宗门旁支",
        "rarity": "蓝",
        "description": "出身于大宗门的旁支或杂役弟子家庭，虽在主宗门内生长，却非核心弟子。",
        "initial_resources": {"items": ["宗门基础功法", "杂役令牌"]},
        "initial_risks": ["宗门内部排挤", "被寄予厚望"],
        "story_tags": ["宗门", "身份", "进阶"],
    },
    {
        "id": str(uuid.uuid4()),
        "name": "隐世仙族",
        "rarity": "橙",
        "description": "出身于避世多年的修仙世家，血脉中有远古大能的传承。族中底蕴深厚，但亦有避世戒律。",
        "initial_resources": {"items": ["仙族玉佩", "上古功法入门"]},
        "initial_risks": ["世仇追杀", "戒律约束", "血脉诅咒"],
        "story_tags": ["世家", "传承", "因果", "复仇"],
    },
    {
        "id": str(uuid.uuid4()),
        "name": "散修之后",
        "rarity": "蓝",
        "description": "父母是云游四方的散修，自幼随父母走南闯北，见多识广但居无定所。",
        "initial_resources": {"items": ["散修手札", "破旧地图"]},
        "initial_risks": ["仇家可能寻来"],
        "story_tags": ["散修", "云游", "阅历"],
    },
    {
        "id": str(uuid.uuid4()),
        "name": "魔道遗孤",
        "rarity": "蓝",
        "description": "父母是魔道修士，在正道围剿中陨落。你被秘密送出，隐姓埋名长大。体内有封印的魔功传承。",
        "initial_resources": {"items": ["封印魔简", "易容面具"]},
        "initial_risks": ["正道追杀令", "魔功反噬风险"],
        "story_tags": ["魔道", "复仇", "双面"],
    },
]


# ── catalog_spirit_roots ─────────────────────────────────────────────────────

SEED_SPIRIT_ROOTS: list[dict[str, Any]] = [
    # 五行灵根 (地灵根)
    {
        "id": str(uuid.uuid4()),
        "name": "金灵根",
        "element": "金",
        "grade": "地",
        "cultivation_bonus": 1.2,
        "breakthrough_bonus": 0.05,
        "cultivation_tendency": "杀伐之道",
        "event_tags": ["剑意", "兵戈", "锋芒"],
    },
    {
        "id": str(uuid.uuid4()),
        "name": "木灵根",
        "element": "木",
        "grade": "地",
        "cultivation_bonus": 1.2,
        "breakthrough_bonus": 0.05,
        "cultivation_tendency": "生生之道",
        "event_tags": ["灵植", "生机", "丹道"],
    },
    {
        "id": str(uuid.uuid4()),
        "name": "水灵根",
        "element": "水",
        "grade": "地",
        "cultivation_bonus": 1.2,
        "breakthrough_bonus": 0.05,
        "cultivation_tendency": "柔韧之道",
        "event_tags": ["幻术", "变化", "治愈"],
    },
    {
        "id": str(uuid.uuid4()),
        "name": "火灵根",
        "element": "火",
        "grade": "地",
        "cultivation_bonus": 1.2,
        "breakthrough_bonus": 0.05,
        "cultivation_tendency": "焚天之道",
        "event_tags": ["丹火", "炼器", "焚灭"],
    },
    {
        "id": str(uuid.uuid4()),
        "name": "土灵根",
        "element": "土",
        "grade": "地",
        "cultivation_bonus": 1.2,
        "breakthrough_bonus": 0.05,
        "cultivation_tendency": "厚德之道",
        "event_tags": ["防御", "地脉", "稳固"],
    },
    # 异灵根 (天灵根)
    {
        "id": str(uuid.uuid4()),
        "name": "冰灵根",
        "element": "冰",
        "grade": "天",
        "cultivation_bonus": 1.5,
        "breakthrough_bonus": 0.10,
        "cultivation_tendency": "极寒之道",
        "event_tags": ["极寒", "封印", "静心"],
    },
    {
        "id": str(uuid.uuid4()),
        "name": "雷灵根",
        "element": "雷",
        "grade": "天",
        "cultivation_bonus": 1.5,
        "breakthrough_bonus": 0.10,
        "cultivation_tendency": "天威之道",
        "event_tags": ["天劫", "破邪", "极速"],
    },
    {
        "id": str(uuid.uuid4()),
        "name": "风灵根",
        "element": "风",
        "grade": "天",
        "cultivation_bonus": 1.5,
        "breakthrough_bonus": 0.10,
        "cultivation_tendency": "逍遥之道",
        "event_tags": ["逍遥", "疾行", "无形"],
    },
    # 稀有灵根 (天灵根)
    {
        "id": str(uuid.uuid4()),
        "name": "阴阳灵根",
        "element": "阴阳",
        "grade": "天",
        "cultivation_bonus": 1.8,
        "breakthrough_bonus": 0.12,
        "cultivation_tendency": "太极之道",
        "event_tags": ["阴阳", "轮回", "天道"],
    },
    {
        "id": str(uuid.uuid4()),
        "name": "混沌灵根",
        "element": "混沌",
        "grade": "天",
        "cultivation_bonus": 2.0,
        "breakthrough_bonus": 0.15,
        "cultivation_tendency": "混元之道",
        "event_tags": ["混沌", "起源", "无上"],
    },
]


# ── catalog_difficulties ─────────────────────────────────────────────────────

SEED_DIFFICULTIES: list[dict[str, Any]] = [
    {
        "id": str(uuid.uuid4()),
        "name": "简单",
        "risk_multiplier": 0.6,
        "reward_multiplier": 1.0,
        "lifespan_modifier": 1.3,
        "luck_modifier": 1,
        "description": "适合体验剧情。风险事件概率降低，寿元更充裕。",
    },
    {
        "id": str(uuid.uuid4()),
        "name": "普通",
        "risk_multiplier": 1.0,
        "reward_multiplier": 1.0,
        "lifespan_modifier": 1.0,
        "luck_modifier": 0,
        "description": "标准修仙人生体验，风险和收益均衡。",
    },
    {
        "id": str(uuid.uuid4()),
        "name": "困难",
        "risk_multiplier": 1.5,
        "reward_multiplier": 1.3,
        "lifespan_modifier": 0.8,
        "luck_modifier": -1,
        "description": "天道无情。风险事件更多更凶险，但渡过劫难后的收益也更丰厚。",
    },
]


# ── catalog_story_seeds ──────────────────────────────────────────────────────
# category: 宗门 / 地域 / 秘境 / 势力 / 机缘 / 劫数

SEED_STORY_SEEDS: list[dict[str, Any]] = [
    # 宗门
    {
        "id": str(uuid.uuid4()),
        "name": "青玄宗",
        "category": "宗门",
        "description": "东荒第一正道宗门，坐拥云脉灵山九座。以剑道和丹道并称于世，门下弟子数千。",
        "tags": ["正道", "剑道", "丹道", "东荒"],
    },
    {
        "id": str(uuid.uuid4()),
        "name": "碧落仙宫",
        "category": "宗门",
        "description": "上古传承的女性为主的宗门，位于碧落仙山之上，擅长水系功法和阵法。",
        "tags": ["正道", "水系", "阵法", "上古"],
    },
    {
        "id": str(uuid.uuid4()),
        "name": "天魔殿",
        "category": "宗门",
        "description": "魔道第一宗门。功法霸道，以战养战。殿中弟子多为好战之辈，但也讲求弱肉强食的魔道规矩。",
        "tags": ["魔道", "杀伐", "霸道", "北域"],
    },
    {
        "id": str(uuid.uuid4()),
        "name": "万宝商会",
        "category": "宗门",
        "description": "横跨正魔两道的商业势力，以契约、情报和宝物说话，不参与正魔之争。",
        "tags": ["中立", "商业", "情报", "全境"],
    },
    # 地域
    {
        "id": str(uuid.uuid4()),
        "name": "东荒古域",
        "category": "地域",
        "description": "东荒深处未开化的蛮荒之地，妖兽横行，但传说有上古遗宝和失传功法。",
        "tags": ["东荒", "妖兽", "遗迹", "探险"],
    },
    {
        "id": str(uuid.uuid4()),
        "name": "南疆十万大山",
        "category": "地域",
        "description": "南疆密林和群山之中，蛊虫、毒物和蛮族并存，灵药丰富但危机四伏。",
        "tags": ["南疆", "毒物", "灵药", "蛮族"],
    },
    {
        "id": str(uuid.uuid4()),
        "name": "西漠沙海",
        "category": "地域",
        "description": "无尽沙海之下埋藏着上古宗门的遗迹，沙暴之中有沙兽、沙匪和传说中的蜃楼。",
        "tags": ["西漠", "沙海", "遗迹", "冒险"],
    },
    # 秘境
    {
        "id": str(uuid.uuid4()),
        "name": "剑冢秘境",
        "category": "秘境",
        "description": "上古剑修埋剑之所，万剑归宗之处。有机缘者可获名剑认主，无剑心者可能被剑气反噬。",
        "tags": ["剑道", "秘境", "机缘", "危险"],
    },
    {
        "id": str(uuid.uuid4()),
        "name": "丹霞洞天",
        "category": "秘境",
        "description": "上古丹道宗师开辟的小世界，遍地灵药和丹方残卷，但亦有守境丹灵和机关禁制。",
        "tags": ["丹道", "洞天", "灵药", "禁制"],
    },
    {
        "id": str(uuid.uuid4()),
        "name": "碎星海",
        "category": "秘境",
        "description": "天外陨星坠落形成的奇异海域，星光之力充斥其中，对神魂有淬炼之效。",
        "tags": ["星空", "神魂", "淬炼", "海域"],
    },
    # 势力
    {
        "id": str(uuid.uuid4()),
        "name": "散修联盟",
        "category": "势力",
        "description": "无门无派的散修自发结成的松散联盟，互通有无，共同应对宗门压力。",
        "tags": ["散修", "中立", "互助", "情报"],
    },
    {
        "id": str(uuid.uuid4()),
        "name": "天机阁",
        "category": "势力",
        "description": "神秘的推演组织，据说能窥探天道运转，出售情报和预言，从不过问世事。",
        "tags": ["情报", "推演", "神秘", "中立"],
    },
    # 机缘
    {
        "id": str(uuid.uuid4()),
        "name": "前辈遗宝",
        "category": "机缘",
        "description": "某位陨落修士的遗物，可能含有功法、丹药、法器甚至其传承。",
        "tags": ["遗宝", "传承", "机缘"],
    },
    {
        "id": str(uuid.uuid4()),
        "name": "灵兽认主",
        "category": "机缘",
        "description": "与一只灵兽结缘，可成为修行助力和战斗伙伴。",
        "tags": ["灵兽", "伙伴", "机缘"],
    },
    {
        "id": str(uuid.uuid4()),
        "name": "顿悟机缘",
        "category": "机缘",
        "description": "某个瞬间与天道共鸣，获得短暂的大彻大悟状态，修炼效率倍增。",
        "tags": ["悟道", "突破", "机缘"],
    },
    # 劫数
    {
        "id": str(uuid.uuid4()),
        "name": "心魔劫",
        "category": "劫数",
        "description": "突破时遭遇心魔侵扰，需要以本心抗衡。失败则走火入魔，成功则心性大涨。",
        "tags": ["心魔", "突破", "意志"],
    },
    {
        "id": str(uuid.uuid4()),
        "name": "天劫降临",
        "category": "劫数",
        "description": "天道降下的雷劫，修为越高劫数越强。渡劫成功脱胎换骨，失败可能身死道消。",
        "tags": ["天劫", "雷劫", "生死"],
    },
    {
        "id": str(uuid.uuid4()),
        "name": "人劫",
        "category": "劫数",
        "description": "来自他人的劫数——仇家追杀、师门背叛、道侣反目。比天劫更难预料。",
        "tags": ["人祸", "背叛", "因果"],
    },
    {
        "id": str(uuid.uuid4()),
        "name": "道心破碎",
        "category": "劫数",
        "description": "遭遇重大打击后道心不稳，修炼陷入瓶颈甚至倒退。需要机缘或大毅力才能恢复。",
        "tags": ["道心", "瓶颈", "逆境"],
    },
]


# ── Seeding helpers ──────────────────────────────────────────────────────────

def seed_catalogs(db: Any) -> int:
    """Insert seed data into catalog tables if they're empty. Returns count of inserted rows."""
    count = 0
    count += _seed_table(db, "catalog_talents", SEED_TALENTS)
    count += _seed_table(db, "catalog_family_backgrounds", SEED_FAMILY_BACKGROUNDS)
    count += _seed_table(db, "catalog_spirit_roots", SEED_SPIRIT_ROOTS)
    count += _seed_table(db, "catalog_difficulties", SEED_DIFFICULTIES)
    count += _seed_table(db, "catalog_story_seeds", SEED_STORY_SEEDS)
    return count


def _seed_table(db: Any, table: str, rows: list[dict[str, Any]]) -> int:
    """Insert rows if table is empty. Returns number inserted."""
    existing = db.list_catalog(table)
    if existing:
        return 0
    for row in rows:
        db.insert_catalog(table, row)
    return len(rows)


def catalog_as_json(row: dict[str, Any]) -> dict[str, Any]:
    """Convert a catalog row to a JSON-safe dict, parsing JSON fields.

    Delegates to :func:`database_common.decode_json_fields`, which decodes the
    same catalog JSON fields and is a no-op for values already parsed
    (dict/list) — the common case for PostgreSQL JSONB columns.
    """
    return decode_json_fields(row)
