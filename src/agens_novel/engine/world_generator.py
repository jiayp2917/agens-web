"""World profile generation for character-creation phase.

Generates a structured world profile from the character's profile selections
and catalog references. The model returns JSON; on failure a local template
fallback keeps the game running.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from ..game.constants import DEFAULT_ATTRIBUTES

log = logging.getLogger(__name__)

# ── Prompt template ─────────────────────────────────────────────────────────

WORLD_BUILDER_SYSTEM = """你是一个修仙世界构建器。
你的任务是根据角色信息生成一个完整的修仙世界观。

你只能输出 JSON，不能输出聊天、解释或散文。
JSON 必须严格符合以下结构：

{
  "world_name": "世界名称，2-8个字",
  "regions": [
    {"name": "地域名", "description": "1-2句描述该地域的特点"}
  ],
  "sects": [
    {"name": "宗门/势力名", "alignment": "正道/魔道/中立", "description": "1-2句描述"}
  ],
  "cultivation_system": "修炼体系的1-2句描述",
  "current_conflicts": ["当前修真界的矛盾1", "矛盾2"],
  "initial_situation": "角色当前处境的一句话描述，50字以内",
  "world_rules": {
    "special_rule": "本局特殊规则的一句话描述，不暴露给前端"
  }
}

约束：
- 地域不超过4个，宗门/势力不超过4个，矛盾不超过3个。
- 所有名称和描述必须是修仙题材的共性设定，不复制任何已知作品的具体门派名、人物名或剧情原文。
- 修炼体系以常见修仙设定（练气/筑基/金丹/元婴/化神/合体/大乘/渡劫/飞升）为基础。
- 如果输入信息不足以构造完整世界观，用通用修仙设定补充。
- 用中文输出。"""


def build_world_prompt(profile: dict[str, Any]) -> str:
    """Build a World Builder prompt from a character creation profile."""
    game_name = str(profile.get("game_name") or "").strip()
    char_name = str(profile.get("char_name") or "无名")
    talent = str(profile.get("talent") or "平平无奇")
    spirit_root = str(profile.get("spirit_root") or "未明")
    family_background = str(profile.get("family_background") or "凡俗")
    difficulty = str(profile.get("difficulty") or "普通")

    parts = [
        f"世界种子名称：{game_name}" if game_name else "世界种子名称：随机",
        f"角色名：{char_name}",
        f"天赋：{talent}",
        f"灵根：{spirit_root}",
        f"家世：{family_background}",
        f"难度：{difficulty}",
    ]
    return "；".join(parts) + "。请根据以上信息生成该角色的修仙世界观。"


def build_world_fallback(profile: dict[str, Any]) -> dict[str, Any]:
    """Generate a default world profile without calling the model."""
    game_name = str(profile.get("game_name") or "").strip()
    char_name = str(profile.get("char_name") or "无名")
    family_background = str(profile.get("family_background") or "凡俗")
    talent = str(profile.get("talent") or "平平无奇")

    world_name = game_name[:8] + "界" if game_name else "东荒云界"
    sect_name = game_name[:6] + "宗" if game_name else "青玄宗"

    return {
        "world_name": world_name,
        "regions": [
            {"name": "东荒", "description": "灵气充沛的东域大地，修仙宗门林立，是正道势力的核心区域。"},
            {"name": "北域冰原", "description": "极北苦寒之地，冰属性灵材丰富，但环境恶劣，适合苦修之士。"},
            {"name": "南疆密林", "description": "十万大山的南疆，妖兽横行，灵药遍地，是冒险者的天堂。"},
        ],
        "sects": [
            {"name": sect_name, "alignment": "正道", "description": f"东荒第一正道宗门，以剑道和丹道闻名。"},
            {"name": "天魔殿", "alignment": "魔道", "description": "北域魔道魁首，信奉弱肉强食的魔道法则。"},
            {"name": "万宝商会", "alignment": "中立", "description": "横跨正魔两道的商业势力，只认灵石不认人。"},
        ],
        "cultivation_system": f"{world_name}的修炼体系沿用经典九境：练气、筑基、金丹、元婴、化神、合体、大乘、渡劫、飞升。灵根决定修炼速度和功法属性，天赋影响突破概率和机缘质量。",
        "current_conflicts": [
            f"{sect_name}与天魔殿在边境灵脉归属上摩擦不断。",
            "南疆秘境即将开启，各方势力蠢蠢欲动。",
        ],
        "initial_situation": f"{char_name}出身{family_background}，身怀{talent}，在{sect_name}山门前准备踏上修仙之路。",
        "world_rules": {
            "special_rule": f"本局世界种子为「{world_name}」，角色运势受难度「{profile.get('difficulty', '普通')}」影响。"
        },
    }


def parse_world_response(result: dict[str, Any]) -> dict[str, Any]:
    """Extract world profile from a model response dict.

    The model response may nest the actual world data inside 'generated_data'
    or 'world_profile'. This function finds and validates the structured
    world profile.
    """
    # Try common nesting patterns
    generated = result.get("generated_data")
    if isinstance(generated, dict) and generated:
        data = generated
    elif isinstance(result.get("world_profile"), dict) and result["world_profile"]:
        data = result["world_profile"]
    else:
        log.warning("World builder returned no usable data")
        return {}

    # Validate required keys
    required = ["world_name", "regions", "sects", "initial_situation"]
    missing = [k for k in required if k not in data]
    if missing:
        log.warning("World builder response missing keys: %s", missing)
        # Don't reject the whole result — use what we got
        for k in missing:
            data[k] = _default_for_key(k)

    # Ensure lists for list fields
    for field in ("regions", "sects", "current_conflicts"):
        if field in data and not isinstance(data[field], list):
            data[field] = [data[field]] if data[field] else []

    # Ensure dict for world_rules
    if "world_rules" not in data or not isinstance(data["world_rules"], dict):
        data["world_rules"] = {}

    # Strip any model error/internal fields that must not reach the frontend
    for key in ("llm_error", "_error", "llm_calls"):
        data.pop(key, None)

    return data


def _default_for_key(key: str) -> Any:
    defaults = {
        "world_name": "未知世界",
        "regions": [{"name": "东荒", "description": "一片灵气充沛的大地。"}],
        "sects": [{"name": "无名宗", "alignment": "正道", "description": "一个普通的修仙宗门。"}],
        "cultivation_system": "以经典九境为基础的修炼体系。",
        "current_conflicts": [],
        "initial_situation": "你站在山门前，准备踏上修仙之路。",
        "world_rules": {},
    }
    return defaults.get(key, "")
