"""Versioned fate content shared by character creation and v3 story hooks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import NAMESPACE_URL, uuid5


@dataclass(frozen=True)
class FateEntry:
    key: str
    kind: str
    name: str
    rarity: str
    description: str
    tags: tuple[str, ...]
    worlds: tuple[str, ...]
    advantage: str
    pressure: str
    early_hook: str
    middle_pressure: str
    late_outcome: str
    attribute_mods: tuple[tuple[str, int], ...] = ()
    element: str = ""
    grade: str = ""
    cultivation_bonus: float = 1.0
    breakthrough_bonus: float = 0.0

    @property
    def stable_id(self) -> str:
        return str(uuid5(NAMESPACE_URL, f"agens-web:fate:{self.key}"))


FATE_ENTRIES: tuple[FateEntry, ...] = (
    FateEntry("talent-herb-sense", "talent", "百草通灵", "蓝", "能辨药性细微变化，却常被药圃旧事牵住脚步。", ("苦修", "宗门", "灵植"), ("forest",), "药材与医修线索更易辨明", "药性反噬与药圃旧约", "药圃失窃的灵种向你求证", "旧药方牵出坊市与宗门争执", "你决定把灵种交给谁，决定药境日后的归属", (("soul", 1), ("comprehension", 1))),
    FateEntry("talent-tide-hearing", "talent", "听潮灵觉", "蓝", "能听出灵潮涨落中的异音，却也会被海上旧梦惊醒。", ("天命", "神魂异兆", "潮汐"), ("ocean",), "更早发现潮汐与航路异变", "潮声幻听会带来误判", "一段失真的潮音指向沉星礁", "船行要求你为潮图缺页作证", "你选择公开或封存潮音的来处", (("soul", 1), ("luck", 1))),
    FateEntry("talent-contract-eye", "talent", "司契慧眼", "蓝", "擅看契书与人情的缝隙，每次看穿都意味着要承担一份旧债。", ("贵胄", "宗门", "契约"), ("clan",), "能辨认盟约和人情中的漏洞", "旧契会反过来索取回应", "一份未署名的旧契落到你手中", "司契楼要求你证明契书真伪", "你让一段家族债务得到清偿或延续", (("comprehension", 1), ("willpower", 1))),
    FateEntry("talent-border-blood", "talent", "守边遗脉", "蓝", "熟悉边地守备法门，却逃不开前辈留下的失守传闻。", ("边地劫数", "苦修", "守备"), ("frontier",), "边地巡防与护送更有把握", "旧军功与失守名声并存", "边营旧符认出你的血脉", "失踪商队牵出前辈失守真相", "你重立守边名声，或让旧案沉入风沙", (("physique", 1), ("willpower", 1))),
    FateEntry("talent-array-bone", "talent", "阵骨初成", "紫", "对阵纹有天生直觉，但每次强行推演都会耗伤神魂。", ("苦修", "神魂异兆", "阵法"), ("forest", "frontier"), "阵法、遗迹与护持线索更清晰", "过度推演会引发神魂压力", "一角残阵在静室外自行复苏", "阵图指向被势力掩埋的旧路", "你选择修复、拆解或交出阵图", (("comprehension", 2), ("soul", 1))),
    FateEntry("talent-sword-soul", "talent", "剑魄未醒", "紫", "剑意偶尔替你挡灾，也会在退让时留下刺骨反噬。", ("苦修", "灾厄", "剑道"), ("frontier", "clan"), "斗法与护送时更易守住心神", "畏战或强行出剑都有代价", "一柄无主断剑在你面前鸣响", "旁宗以断剑来历逼你站队", "你为断剑择主，也为自身择路", (("physique", 1), ("willpower", 2))),
    FateEntry("talent-moon-mark", "talent", "残月劫印", "橙", "能预感灾厄将近，却常成为最先被灾厄注意的人。", ("灾厄", "天命", "边地劫数"), ("frontier", "ocean"), "风险前有额外征兆", "征兆会吸引追索者和劫数", "残月印在异潮前发烫", "各方争夺能解读劫印的人", "你把劫印化为警示，或让它成为新的灾因", (("luck", -1), ("soul", 2))),
    FateEntry("talent-dream-memory", "talent", "梦游前尘", "橙", "梦中常见陌生旧景，醒来后必须分辨记忆与妄念。", ("神魂异兆", "天命", "因果"), ("ocean", "clan"), "旧地与人物关系更易产生线索", "记忆错位会造成判断压力", "梦里出现一名从未见过的旧人", "旧人身份与主线证词彼此冲突", "你确认梦中旧景的真伪并承担其后果", (("soul", 2), ("comprehension", 1))),
    FateEntry("family-border-kin", "family", "边营遗属", "蓝", "故人留下一枚边营旧牌，既是门路，也是未尽的守备责任。", ("边地劫数", "宗门", "家族"), ("frontier",), "边营人物与旧档更容易接触", "旧牌会牵出失守责任", "旧牌在入营时被执事认出", "边营要求你回应前辈遗留的缺口", "你补上守备缺口，或公开旧案", (),),
    FateEntry("family-shipward", "family", "船行养子", "蓝", "在船行抚养下长大，熟悉人情航路，却欠着一笔未写明的救命恩。", ("散修", "天命", "船行"), ("ocean",), "船行消息与同行者更易获得", "恩情会在关键航路兑现", "养父留下的航线突然失效", "船行要求你在潮音阁与商路之间选择", "你决定船行是继续独立还是归附势力", (),),
    FateEntry("family-herbalist", "family", "药农世家", "绿", "家人识药种田，最怕一场早霜毁掉多年心血。", ("宗门", "苦修", "凡尘"), ("forest",), "药圃与坊市关系更稳固", "家中药田会带来现实牵挂", "早霜传讯让你得知药田异变", "药商与外门围绕药种归属争执", "你为家人保住药田，或换得更大的修行机会", (),),
    FateEntry("family-contract-clerk", "family", "盟约书吏", "绿", "家中世代抄录契书，清白名声背后藏着一页被撕去的旧档。", ("贵胄", "宗门", "契约"), ("clan",), "盟约、名册和司契楼线索更清晰", "旧档会牵连家人名誉", "一页旧档被匿名送到外院", "书吏同僚要求你替家中作证", "你选择恢复旧档真相或守住家门声名", (),),
    FateEntry("family-unregistered", "family", "失籍散修", "蓝", "家人早年被逐出籍册，只留下半张路引与不肯提起的故地。", ("散修", "灾厄", "因果"), ("frontier", "ocean"), "散修和边地线索更易接近", "身份暴露会引来盘查", "半张路引指向旧地的接引人", "旧籍争议迫使你选择依附或独行", "你为家人恢复籍册，或彻底断开旧名", (),),
    FateEntry("family-archive-keeper", "family", "旧朝守库人", "紫", "祖辈看守废朝库藏，留下的钥匙从来不是白白开启。", ("贵胄", "神魂异兆", "传承"), ("clan", "ocean"), "旧物、遗迹与史料更易关联", "库钥会引来多方觊觎", "库钥在异潮中自行发热", "势力要求你交出库藏线索", "你决定库藏为谁所用，也承受相应追索", (),),
    FateEntry("family-demon-refugee", "family", "妖患流民", "白", "幼时随流民避开妖患，知道活下来往往比体面更难。", ("边地劫数", "散修", "灾厄"), ("frontier",), "流民、商队与边地情报更可信", "故乡妖患会反复成为压力", "旧村来人带来妖患再起的消息", "救人和守住修行机会发生冲突", "你让旧村获得退路，或承认无力兼顾", (),),
    FateEntry("family-disgraced-branch", "family", "罪籍旁支", "紫", "家族被记在罪籍末尾，门内每一次善意都可能附着条件。", ("贵胄", "灾厄", "宗门"), ("clan",), "能看见宗门内部的隐性规则", "名誉压力会放大每次失误", "旁支旧案被重新提起", "盟会要求你以功劳换取除籍机会", "你洗清家名，或主动放弃这条枷锁", (),),
    FateEntry("root-tide", "root", "潮汐灵根", "蓝", "灵息随潮涨落，适合海上修行，却难在无潮之地静心。", ("天命", "神魂异兆", "潮汐"), ("ocean",), "潮汐与航路事件更有利", "离开潮域时修行压力更大", "潮图缺页与你的灵息同频", "异潮改变了你的修行节奏", "你以自身灵息为潮图补上一笔", (), "水", "地", 1.3, 0.06),
    FateEntry("root-herbal", "root", "药灵根", "蓝", "灵息能温养草木，却会把药性残留在经脉深处。", ("苦修", "宗门", "灵植"), ("forest",), "药圃与疗伤事件更易收获线索", "药毒和人情债更常出现", "一株异草随你的灵息苏醒", "药性争议让你必须选择立场", "你决定异草是救人还是换取前路", (), "木", "地", 1.3, 0.06),
    FateEntry("root-sand-gold", "root", "砂金双灵根", "紫", "金土相生，善守险地，却容易被边地旧矿脉牵动。", ("边地劫数", "苦修", "守备"), ("frontier",), "守备、矿脉与护送更稳定", "旧矿脉会带来势力争夺", "荒岭砂脉对你产生回应", "商栈与妖寨争夺矿脉消息", "你选择封存矿脉或让它重见天日", (), "金土", "天", 1.45, 0.09),
    FateEntry("root-contract", "root", "契印灵根", "紫", "灵息能感应誓约真假，但每次撕开谎言都会留下因果印记。", ("贵胄", "宗门", "契约"), ("clan",), "契约与关系事件更易形成后果", "因果印会增加人情压力", "一纸盟约在你手中显出暗纹", "暗纹牵出主线中被隐去的一方", "你决定是否以真相换取自由", (), "灵", "天", 1.45, 0.09),
    FateEntry("root-star-sand", "root", "星砂灵根", "橙", "夜间灵息如星砂流转，机缘与迷失常在同一条路上出现。", ("天命", "神魂异兆", "因果"), ("ocean", "clan"), "星象、旧地和气运事件更有线索", "虚假征兆更难分辨", "星砂在潮退之夜排成旧路", "各方以星砂征兆争夺解释权", "你让星砂成为航标，或让它湮没于传闻", (), "星", "天", 1.55, 0.11),
    FateEntry("root-ghost-wind", "root", "幽风灵根", "橙", "风息常携来远处残声，逃遁迅捷，却难安于人群与宗门。", ("散修", "灾厄", "边地劫数"), ("frontier", "ocean"), "风险与远行事件更易发现退路", "孤行会削弱稳定关系", "一阵幽风带来失踪者的残声", "残声要求你冒险追入无人地带", "你为残声找到归处，或承认只能继续前行", (), "风", "天", 1.55, 0.11),
)


def entries_for(kind: str) -> tuple[FateEntry, ...]:
    return tuple(entry for entry in FATE_ENTRIES if entry.kind == kind)


def entry_for_name(name: str) -> FateEntry | None:
    return next((entry for entry in FATE_ENTRIES if entry.name == name), None)


def catalog_rows(kind: str) -> list[dict[str, Any]]:
    """Project v3 fate entries into the existing PostgreSQL catalog schema."""
    rows: list[dict[str, Any]] = []
    for entry in entries_for(kind):
        row: dict[str, Any] = {
            "id": entry.stable_id,
            "name": entry.name,
            "rarity": entry.rarity,
            "description": entry.description,
        }
        if kind == "talent":
            row.update({
                "attribute_mods": dict(entry.attribute_mods),
                "tags": list(entry.tags),
            })
        elif kind == "family":
            row.update({
                "initial_resources": {},
                "initial_risks": [entry.pressure],
                "story_tags": list(entry.tags),
            })
        elif kind == "root":
            row.update({
                "element": entry.element,
                "grade": entry.grade,
                "cultivation_bonus": entry.cultivation_bonus,
                "breakthrough_bonus": entry.breakthrough_bonus,
                "cultivation_tendency": entry.advantage,
                "event_tags": list(entry.tags),
            })
        rows.append(row)
    return rows


def spirit_root_rules() -> list[dict[str, Any]]:
    return [
        {
            "name": entry.name,
            "element": entry.element,
            "grade": entry.grade,
            "cultivation_bonus": entry.cultivation_bonus,
            "breakthrough_bonus": entry.breakthrough_bonus,
        }
        for entry in entries_for("root")
    ]
