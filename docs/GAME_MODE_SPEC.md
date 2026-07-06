# 游戏模式全流程细则（v5）

## 2026-06-27 Implementation Note

- A/B/C/D remains the only product input contract. `/choice` accepts
  `choice_index` or A/B/C/D letters; arbitrary free-text `choice` requests are
  not part of game-mode v5 and return HTTP 400.
- Breakthrough text inside a choice is not enough to bypass realm rules. If
  breakthrough is ineligible, the selected button resolves as an ordinary
  rule-settled turn so the player is not stuck on HTTP 200 with no progress.
- Model narrative is not authoritative. When narrative claims gains or realm
  changes without matching structured `state_delta`, the narrative/state is
  rejected but the base rule settlement still records a complete turn.
- The latest visible-Chrome local validation after ordinary-turn repair reduction
  passed 20/20 non-fallback turns. Repair fell to 0/20, but live latency
  remains a P1 gameplay-quality risk.

> 状态：**v5 Alpha 本地与当前生产 P0 验收已闭环，下一步进入 P1 游玩质量与模型效率优化**。游戏模式核心规则已切换到 A/B/C/D 四按钮、无 HP/MP、事件判定战斗、寿元寿命表、六维属性、动态流逝年数、PostgreSQL 回合记录和用户级模型配置。
> 文档定位：游戏模式的产品 spec + 技术实现规格，是“游戏模式”的单一事实来源。
>
> **实现状态**（当前状态见文档顶部说明）
>
> | 阶段 | 工作 | 状态 |
> |---|---|---|
> | §2 输入契约 | A/B/C/D 四按钮固定语义，无自由文本 | ✅ 已实现（`engine/choices.py`、`game_engine._resolve_choice_input`） |
> | §3 寿元寿命表 | 各境界寿元区间，UI 显示当前寿元上限与剩余寿元 | ✅ 已实现（`game/constants.py` REALM_LIFESPAN_RANGES、`render.format_status_bar`） |
> | §4 六维属性 | 体魄/神魂/气运/悟性/心性/根骨，无 HP/MP；角色创建 30 点池 | ✅ 已实现（运行时默认属性保留在 `constants.DEFAULT_ATTRIBUTES`；角色创建由 `start_flow.normalize_profile_attributes()` 和 React 表单执行 2-8/30、0-10/30 校验；`GameSession` 已移除 hp/mp/luck/combat 字段） |
> | §3.5 动态开局 | 难度、天赋、灵根、家世、六维和随机/手选模式驱动本局世界观、0-16 岁编年史、16 岁初始局势、外界情报和首次 A/B/C/D | ✅ 后端开局链路已改为统一 opening payload；模型未启用或失败时使用 profile-aware fallback，不再固定青玄宗/东荒云界模板；fallback 不算 live-model 成功 |
> | §4 战斗事件化 | 斗法/禁地/心魔/天劫以事件判定表达 | ✅ 已实现（`handle_combat_action` 为安全 no-op；`apply_delta` 丢弃结构化 combat delta） |
> | §8.3 `game_turns` 表 | JSONB 回合日志 + `game_runs` + `player_progress` | ✅ 已接线（PostgreSQL 单后端（Option C 已移除 SQLite），Alembic `20260622_0003`，Web 回合/终局写入） |
> | §11 稀有度解锁门 | 白/绿/蓝/紫/橙/红 六档 + runs/ascension 门径 | ✅ 已接线（`constants.rarity_unlocked_for`、`/api/catalog/rarities`，终局写入 `player_progress`） |
> | §11 死亡分类 | finale > karma > event > lifespan > player | ✅ 已实现（`death_rewards.categorize_death`） |
> | 验证 | compileall + pytest + React build + 密钥审计 | ⏳ 以当前分支最新测试结果为准，不在文档中固化旧计数 |
> | 待办 | 继续降低本地 live 响应耗时、repair/judge 依赖，并改善 20 回合内容体验 | ⏳ 当前生产批次 start+choice 已 non-fallback；后续生产部署或模型配置变更仍需复跑。当前本地 `local-visible-p1-final-20260706` 已完成动态开局 live start gate、20/20 choice non-fallback 和存读档；repair 0/20、judge 3 次，但平均约 25.9s、最大约 57.1s，live 响应慢仍需治理 |

## 0. TL;DR

“文字修仙模拟器 - 游戏模式” = **修真世界观下的人生模拟器**。

- **回合**：1 回合 = 一次关键抉择；每回合推进一段修行岁月。
- **时间**：低境界可能推进 1-3 年；高境界可能推进十年、百年、千年，由境界、行动、事件和规则引擎决定。
- **玩家输入**：4 选 1（A 稳妥 / B 机遇 / C 风险 / D 气运），**无自由文本**。
- **D 选项**：固定为气运/天命路线，结果强绑定 `luck` 气运属性。
- **模型输出**：每回合叙述建议不超过 200 字；模型只负责润色和选项文案，不做数值权威结算；玩家可见文本不得包含 JSON、结构化标签、英文状态词或内部仲裁文案。
- **寿元**：按境界区间生成当前角色寿元上限，UI 固定显示当前年龄、境界、剩余寿元、本回合流逝时间和外界大事摘要。
- **战斗**：无 HP/MP 概念；斗法、禁地、心魔、突破等都以事件判定和概率结算表达。
- **托管**：默认随机选择 A/B/C/D；后续可扩展固定策略或偏好策略。
- **首页**：游戏模式高亮可点；引导模式、小说模式保留入口但暂不开放。

游戏模式的核心是：**规则引擎推进人生，玩家做关键抉择，大模型只做短文本表现**。这与引导/小说模式的自由输入和长叙事不同。

---

## 1. 三模式定位

### 1.1 模式状态

| 模式 | 状态 | 入口可见性 |
|---|---|---|
| 游戏模式 | 主推 | 入口高亮可点 |
| 引导模式 | 暂搁置 | 入口灰色 disabled + tooltip “暂不开放” |
| 小说模式 | 暂不开发 | 入口灰色 disabled + tooltip “暂不开放” |

### 1.2 首页呈现

```text
[ 新游戏 ]    <- 游戏模式（高亮）
[ 引导模式 ]  <- 灰，aria-disabled
[ 小说模式 ]  <- 灰，aria-disabled

[ 读档 ]  [ 教程 ]  [ 设置 ]  [ 结束 ]
```

- 引导/小说模式保留入口，用于未来切换和产品路线图展示。
- 禁用入口应使用 `disabled` 或 `aria-disabled="true"`，并给出“暂不开放”的简短提示。
- 新游戏进入游戏模式；游客可直接游玩，邀请码账号提供云存档。

### 1.3 与现有项目约束的关系

- 原“当前只开放引导模式”需在实施游戏模式时更新为“当前只开放游戏模式”。
- 原文本行动入口在游戏模式下不适用；D 固定为气运/天命选项。
- 9 阶境界、API key 脱敏、前端不得保存真实 key、Web 前端不得直接修改游戏状态等约束仍然适用。
- 本文是 v5 规格；当前代码应优先让 React 主入口和 Web API 对齐本规格。旧 `web/frontend` 已删除，不再作为产品入口或 fallback。

---

## 2. 玩家输入：4 选 1

### 2.1 选项语义与风险收益

| 选项 | 固定语义 | 常见行动 | 风险档位 | 结算倾向 |
|---|---|---|---|---|
| A 稳妥 | 闭关、修炼、整顿、低调 | 闭关、温养法宝、稳固境界、打理洞府 | 低 | 小收益、少事故、耗时可控 |
| B 机遇 | 外出、结交、寻访、探索 | 拜访前辈、参加法会、寻访遗迹、结交同道 | 中 | 中收益、中风险、可能触发支线 |
| C 风险 | 突破、斗法、禁地、豪赌 | 强行破境、闯禁地、夺机缘、迎战仇敌 | 高 | 高收益、高死亡或重创风险 |
| D 气运 | 随缘、天命、未知机缘 | 顺心而行、听天由命、追随预感、赌因果 | 浮动 | 强吃气运，可逆天改命，也可命运反噬 |

A/B/C 的风险档位必须稳定，具体按钮文案可随当前场景变化。D 的按钮文案也可变化，但语义必须固定为气运/天命路径，不允许重新变成自由输入。

### 2.2 D 气运计算原则

D 不是“高风险高收益”的普通选项，而是“气运判定”：

- 高气运：更容易遇到贵人、遗宝、临危救援、破局灵感。
- 中气运：接近普通随机事件，收益和风险都不极端。
- 低气运：更容易被因果反噬、机缘变劫数、临门一脚失败。
- 气运不能保证绝对安全；只改变概率分布和事件倾向。

建议规则：

```python
def apply_luck_bias(base_risk: float, base_reward: int, luck: int) -> tuple[float, int]:
    """
    luck: 0-10. Runtime attributes use the v5 public scale; 5 is neutral.
    返回: (调整后风险, 调整后收益)。
    只用于 D 气运路线或带有 luck_tag 的事件。
    """
    luck_factor = (luck - 5) / 5.0
    adjusted_risk = base_risk * (1 - luck_factor * 0.8)
    adjusted_reward = int(base_reward * (1 + luck_factor * 0.6))
    return max(0.0, min(adjusted_risk, 0.6)), adjusted_reward
```

### 2.3 输入与提示

- UI 移除原行动文本入口。
- 选择区渲染 4 个稳定按钮：A、B、C、D。
- D 应有明确“看气运/赌天命/随缘而行”的提示，不能让玩家误以为它是自由行动。
- 托管游玩可以默认随机选择，也可以后续扩展“偏稳妥”“偏机遇”“偏风险”“偏气运”。

---

## 3. 日历与寿元机制

### 3.1 回合不是固定一年

游戏模式中，1 回合代表一次关键抉择后的结果展示。时间流逝由规则引擎根据境界、行动和事件决定：

| 境界段 | 常见时间跨度 | 示例 |
|---|---:|---|
| 练气/筑基 | 1-3 年 | 一次闭关、一趟历练、一场小劫 |
| 金丹/元婴 | 3-10 年 | 温养金丹、远游访道、宗门变局 |
| 化神/合体 | 10-100 年 | 长期闭关、神游外域、宗门兴衰 |
| 大乘/渡劫 | 50-1000 年 | 秘境探索、飞升机缘、天劫准备 |

示例表达：

```text
近十年你都在闭关，寿元剩余 382 年。外界传来东荒魔修南下的消息，但你并未亲见。
```

```text
近百年你都在散仙秘境中追寻飞升机缘，收获颇多，却仍未见破界之门。寿元剩余 202 年。
```

### 3.2 第一版日历字段

第一版只做“年龄 + 剩余寿元”，不做完整纪年、年号、王朝历。

核心字段：

```json
{
  "elapsed_years": 10,
  "age_before": 214,
  "age_after": 224,
  "lifespan": 600,
  "remaining_lifespan": 376,
  "calendar_summary": "近十年闭关，外界宗门更替一代弟子。"
}
```

### 3.3 寿终规则

- 每次结算后由后端计算 `remaining_lifespan = lifespan - age_after`。
- 若 `remaining_lifespan <= 0` 且本回合未突破、未飞升、未获得延寿结果，则进入寿终/坐化结局。
- 境界提升会提高寿元上限；延寿丹、洞天机缘、功法副作用等可影响寿元。
- 寿元判定由规则引擎负责，不由模型自由决定。

### 3.4 寿元表

寿元采用区间上限，而不是固定常数。`session.lifespan` 表示当前角色本局寿元上限，来源为境界区间 + 体魄/根骨/天赋/难度/事件修正。突破成功会按目标境界区间重新提升寿元；重伤、禁术、走火入魔、毒伤、失败突破等可以扣减寿元；延寿丹、洞天机缘、养生功法等可以增加寿元。

| 境界 | 寿元区间 |
|---|---:|
| 练气 | 80-120 |
| 筑基 | 160-240 |
| 金丹 | 400-600 |
| 元婴 | 800-1200 |
| 化神 | 1600-2400 |
| 合体 | 3200-4800 |
| 大乘 | 4200-5800 |
| 渡劫 | 5200-6800 |
| 飞升 | 终局 |

具体数值允许后续平衡，但前端和模型不得绕过后端寿元规则。

### 3.4.1 境界显示与突破结算

- 只有练气使用小层显示：`练气1层` 到 `练气9层`。
- 筑基及以上统一使用四阶段显示：`初期 / 中期 / 后期 / 圆满`，不得显示 `筑基2层`、`金丹3层` 等文本。
- 所有状态栏、回合日志、存档摘要、终局页和前端侧栏必须复用同一格式化口径。
- 突破流程必须由规则先判定：成功、失败、重伤、死亡、跌境、寿元折损只来自规则引擎；模型只按规则结果写叙事和下一步选项。
- 突破成功时，模型叙事不得出现“修为尽废、修为未复、突破失败、功亏一篑”等失败词；若出现，后端必须改写为成功叙事。
- 突破失败时，后端不得提升境界；失败等级可以落账为轻伤、根基受损、跌落小境界、寿元折损或死亡。“修为尽废”只允许在系统确实执行严重跌境或终局时出现。
- 存在“根基重创 / 修为未复”等状态时，禁止继续突破或自动升层，直到后续事件结构化清除。

### 3.4.2 老年低境界风险

- 练气 50 岁后若仍未到后期，开始出现瓶颈、衰相、病痛等压力事件。
- 练气 70 岁后若仍未筑基，突破成功率下降，失败惩罚上升；无筑基丹、护道者、重大机缘时不应稳定突破。
- 练气 90 岁后仍停留低层会触发病衰/坐化等终局风险。
- 高龄突破可以作为少数机缘剧情存在，但必须有规则依据；低资质不能只是“慢一点但总能突破”。

### 3.5 局长结构与开局节奏

- **标准局长 90 回合**，允许 **60-120 回合**浮动；事件、路线、死亡、寿尽和飞升可以提前或延后结束一局。
- **20 回合垂直切片**是可玩性验收目标，不等于完整局长度。20 回合默认达到练气后期或筑基门槛；强天赋、高悟性、高风险路线可提前筑基，稳妥路线可延后。
- **开场编年史**：角色创建后先生成 **0-16 岁短编年史**，说明出身、早年异象、家族/宗门关系和第一次接触修仙的契机，再从 16 岁开始第一次抉择。
- **阶段反馈节奏**：每 **3-5 回合**出现阶段性反馈，包括年龄变化、修为推进、外界大事、关系变化、风险伏笔或奖励。
- **动态开局输入**：开局生成必须使用难度、天赋、灵根、家世、六维属性和随机/手选模式推导命数倾向；模型输出与本地 fallback 都必须体现这些输入，不能只替换角色名。
- **动态开局输出**：后端写入 `world_profile`、`world.lore_facts`、`world.current_scene` 和首次 choices；`world_profile` 至少应包含 `world_name`、`current_conflicts`、`fate_hooks`、`chronicle_0_16` 和 `initial_situation_16`。
- **境界节奏**：小境界进展多为隐式，不频繁作为选项；大境界突破作为阶段事件呈现，尤其筑基、金丹、元婴、化神和飞升。练气期不得长期滞留早期小层；规则引擎需要用年龄/回合推进提供小境界下限，避免 13 年仍停留练气三层这类编年史失真。
- 第一版不做显式资源栏，只保留状态型记录，例如境界、年龄、寿元、称号、关系、关键机缘、伤势、因果和传承。
- UI 侧栏可展示“外界情报”，来源限于 `world.current_scene`、`world.lore_facts` 和 `world_profile.current_conflicts` 等只读世界摘要；它不是玩家资源栏，也不授权前端修改权威状态。

---

## 4. 角色属性体系

### 4.1 六维属性

游戏模式统一使用六维：

| 字段 | 中文 | 主要影响 |
|---|---|---|
| `physique` | 体魄 | 受伤、禁地、长期闭关、部分斗法事件的承受力 |
| `soul` | 神魂 | 心魔、夺舍、幻境、魂魄类机缘 |
| `luck` | 气运 | D 气运选项、奇遇质量、命运反噬概率 |
| `comprehension` | 悟性 | 功法理解、突破效率、闭关收益 |
| `willpower` | 心性 | 心魔、苦修、长闭关、失败后的恢复 |
| `root_bone` | 根骨 | 修炼速度、肉身根基、境界稳定度 |

每项属性只影响 1-2 类核心判定，避免复杂派生数值。角色创建采用**六属性 30 点池**：

| 模式 | 单项范围 | 总池 |
|---|---:|---:|
| 手动分配 | 2-8 | 30 |
| 随机 | 0-10 | 30 |

手动分配用于稳定构筑；随机模式允许极端开局，但总和仍固定为 30。前端和后端校验必须以本节为准。

Runtime contract: attributes are stored and resolved as 0-10 values. `DEFAULT_ATTRIBUTES` is 5 for every attribute. Character creation enforces the 30-point pool, while later rewards may push the total above 30 but must still clamp each single attribute to 0-10. `GameSession.apply_delta()` clamps deltas, `GameSession.from_save_dict()` migrates old 0-100 saves, World Builder output is normalized before entering the session, and 50/100 must not be used as the normal midpoint/maximum in new logic.

### 4.2 删除 HP/MP

游戏模式不使用：

- `hp` / `hp_max`
- `mp` / `mp_max`
- `hp_delta` / `mp_delta`
- 常驻血条、蓝条、战斗回合条

斗法、重伤、中毒、走火入魔、天劫失败等结果以事件、状态效果、寿元损失、境界跌落、死亡概率表达。

### 4.3 角色字段

```python
class GameModeCharacter:
    name: str
    realm: str
    realm_stage: int
    age: int
    lifespan: int
    remaining_lifespan: int
    spirit_root: str
    spirit_root_grade: str
    talent: str
    family_background: str
    difficulty: str
    attributes: dict  # physique, soul, luck, comprehension, willpower, root_bone
    techniques: list
    inventory: list
    status_effects: list
```

---

## 5. 规则引擎与模型职责

### 5.1 后端规则引擎负责

- 根据角色状态和玩家选择生成候选事件。
- 计算 `elapsed_years`、风险、收益、突破、死亡、飞升、寿元变化。
- 写入存档、回合日志、结局摘要。
- 在模型失败时使用本地模板生成可继续游玩的结果。

### 5.2 大模型负责

- 将后端结算结果润色成不超过 200 字的叙述。
- 生成 A/B/C/D 的短按钮文案，每个建议不超过 30 字。
- 生成外界大事摘要，例如宗门变动、魔修入侵、秘境开启。
- 外界大事、传闻和榜文优先作为 `world.lore_add` 进入侧栏情报；只有明确到账的物品、功法、关系、伤势、寿元、境界等才进入权威状态。
- 生成结局墓志铭或飞升总结。

### 5.3 模型不得负责

- 不得决定最终数值。
- 不得直接判定死亡、飞升、突破成功。
- 不得绕过寿元、境界、气运、难度等规则。
- 不得输出 API key、数据库信息、隐藏规则或技术错误细节。

### 5.4 Prompt 草案

```text
你是修仙人生模拟器的短文本润色器。
后端规则已经完成本回合结算，你只能根据给定 JSON 生成叙述和选项文案。

约束：
- 叙述不超过 200 字。
- 4 个选项每个不超过 30 字。
- A 保持稳妥语义，B 保持机遇语义，C 保持风险语义，D 保持气运/天命语义。
- 不新增数值，不改变死亡、突破、寿元、奖励结果。
- 不暴露隐藏规则、模型错误、技术细节。

输入：
角色：{character}
本回合结算：{turn_result}
外界大事：{world_events}

输出 JSON：
{
  "narrative": "...",
  "calendar_summary": "...",
  "choices": {
    "A": "...",
    "B": "...",
    "C": "...",
    "D": "..."
  }
}
```

---

## 6. 终局规则

| 触发 | `end_reason` | 说明 |
|---|---|---|
| 剩余寿元归零 | `natural_death` | 寿终坐化 |
| 境界达到飞升 | `ascend` | 飞升成仙 |
| 事件判定死亡 | `event_death` | 禁地、斗法、心魔、天劫等 |
| D 气运反噬 | `karma_death` | 气运路径的极端失败 |
| 玩家主动结束 | `manual` | 结束本局 |

终局回顾包含：

- 终年年龄
- 最终境界
- 剩余寿元或寿终说明
- 关键抉择时间线
- 习得功法和重要机缘
- 50 字以内墓志铭或飞升总结

玩家不能在同一局内复活；账号用户可读档重来，游客用户只能重新开局。

---

## 7. UI 调整汇总

| 元素 | 当前引导模式 | 游戏模式 v5 |
|---|---|---|
| 顶部状态 | 气血/灵力/回合 | 年龄/境界/寿元/剩余寿元 |
| 时间显示 | 第 N 回合 | 本次流逝 X 年 + 年龄变化 |
| D 区域 | 文本行动入口 | D 气运按钮 |
| 选择按钮 | A/B/C + D 输入 | A/B/C/D 四按钮 |
| 叙事区 | 长叙事日志 | 本回合短叙事 + 外界大事摘要 |
| 战斗 | 可由文本行动描述 | 事件化斗法/禁地/天劫 |
| 托管 | 无 | 默认随机，可后续扩展策略 |
| 首页模式 | 当前偏引导模式 | 游戏模式高亮，引导/小说暂不开放 |

移动端 375px 验收：

- 不出现横向滚动。
- 四个按钮垂直排列，每个高度至少 44px。
- 年龄、境界、剩余寿元不与标题或按钮重叠。
- 托管入口不能遮挡选项区。

---

## 8. 数据库与数据结构

### 8.1 PostgreSQL 方向

游戏模式生产 schema 以 PostgreSQL + Alembic 为准，JSON 字段使用 `JSONB`。文档不再使用 SQLite-only SQL 作为最终 schema。

### 8.2 核心表

建议表：

- `game_runs`：一局游戏的总状态。
- `game_turns`：每次关键抉择和结算结果。
- `catalog_talents`：天赋库。
- `catalog_family_backgrounds`：家世库。
- `catalog_spirit_roots`：灵根库。
- `catalog_difficulties`：难度配置。
- `catalog_events`：事件模板。
- `catalog_opportunities`：机缘模板。
- `catalog_endings`：结局模板。

### 8.3 `game_turns` 关键字段

```sql
CREATE TABLE game_turns (
  id UUID PRIMARY KEY,
  run_id UUID NOT NULL,
  turn_no INTEGER NOT NULL,
  start_age INTEGER NOT NULL,
  elapsed_years INTEGER NOT NULL,
  end_age INTEGER NOT NULL,
  lifespan INTEGER NOT NULL,
  remaining_lifespan INTEGER NOT NULL,
  choice_taken TEXT,
  choices JSONB NOT NULL,
  state_delta JSONB NOT NULL,
  state_after JSONB NOT NULL,
  calendar_summary TEXT NOT NULL,
  narrative TEXT NOT NULL,
  event_kind TEXT NOT NULL,
  end_reason TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(run_id, turn_no)
);
```

`choices` 存 A/B/C/D 的展示文案和语义标签；`state_delta` 存本回合变化；`state_after` 存规则结算后的权威状态快照。

### 8.4 内容库来源

天赋、家世、事件、机缘、结局按主流修仙小说的共性套路生成，例如：

- 凡人出身、宗门弟子、世家旁支、散修遗孤。
- 五行灵根、异灵根、天灵根、杂灵根。
- 山门收徒、秘境开启、魔修作乱、宗门大比、心魔劫、天劫、洞府传承。
- 贵人相助、遗宝出世、丹药延寿、道侣因果、宗门兴衰。

不得直接复制具体作品的人物名、门派名、剧情原文或专有设定。实现时应生成抽象词条，保留修仙题材共性，不复刻受版权保护表达。

---

## 9. 落地分阶段

| 阶段 | 工作 | 验证 | 状态 |
|---|---|---|---|
| 1 | 固化 v5 文档和实现边界 | 搜索确认无旧硬规则残留 | ✅ |
| 2 | 新增游戏模式规则引擎骨架 | 单测覆盖 A/B/C/D 和时间推进 | ✅ |
| 3 | 新增 PostgreSQL catalog 与 `game_turns` 迁移 | Alembic 空库升级成功 | ✅ catalog/reward bridge 已在 `20260621_0002`；v5 run/turn/progress 已在 `20260622_0003` |
| 4 | 接入角色创建六维属性和内容库读取 | API 返回可选天赋/家世/灵根/难度 | ✅ |
| 5 | 实现一次关键抉择结算 | 低境界推进 1-3 年，高境界推进十年级以上 | ✅ |
| 6 | 接入模型润色和本地模板兜底 | 模型失败仍可继续下一回合 | ✅ |
| 7 | React UI 切到游戏模式入口 | 375px/768px/1440px 无横向滚动 | ⏳ 已切到 A/B/C/D 固定语义，三档断点待终验 |
| 8 | 游客与账号存档验收 | 游客可玩无云存档，账号可存读档 | ✅ 本地 API 与 Chrome 覆盖；2026-07-02 当前生产批次账号流与 production start+choice non-fallback 已通过。后续生产部署或模型配置变更仍需复跑同一门禁 |

---

## 10. 风险与权衡

| 维度 | 风险 | 缓解 |
|---|---|---|
| 时间跨度变大 | 玩家可能不理解“一个回合过去百年” | UI 明确显示本次流逝年数和外界大事 |
| D 气运随机性 | 高气运过强或低气运体验差 | 设概率上下限，避免绝对安全或必死 |
| A/B/C 固定风险档位 | 长期可能套路化 | 选项文案随场景变化，事件库持续扩充 |
| 模型参与叙述 | 模型可能改变数值口径 | 后端结果为权威，模型只读结算 JSON |
| 内容库借鉴修仙套路 | 可能误用具体作品表达 | 只抽象共性，不复制人物、门派、剧情原文 |
| 规格与当前代码差异大 | 实施周期较长 | 保持引导模式现状，游戏模式独立增量实现 |

---

## 11. 决策溯源

| 决策 | 已确认内容 |
|---|---|
| 模式优先级 | 先做游戏模式；小说模式最难暂不开发；引导模式暂时搁置。 |
| D 选项 | D 改为固定选项，跟气运强相关。 |
| 回合时间 | 不固定为一年；根据境界寿元、玩家选项和事件波动。 |
| 日历第一版 | 只做年龄 + 剩余寿元，不做完整纪年。 |
| A/B/C | 风险档位稳定，文案随剧情变化。 |
| 属性 | 统一为体魄、神魂、气运、悟性、心性、根骨。 |
| 内容库 | 按主流修仙小说共性套路生成，不复制具体作品表达。 |
| 局长与开局 | 标准局长 90 回合，允许 60-120 回合浮动；20 回合切片验收；0-16 岁开场编年史；每 3-5 回合阶段反馈；六属性 30 点池。 |

补充说明：
天赋、灵根、家世按照白绿蓝紫橙红，白色概率最高，红色概率最低。角色创建界面自选默认只开放紫色以下（不包括紫色）；随机可以抽到更高稀有度，级别越高概率越低。红色第一次游玩不可随机到，完成一次游玩后才进入随机池。天赋、灵根、家世独立随机。白色不代表最差，红色也不代表一定最好；强力词条可以带副作用，低稀有度词条也可以触发稳定路线。

内容来源统一采用抽象修仙套路库，不直接使用真实小说人物、门派、剧情原文或专有设定。特殊剧情可由天赋、家世、灵根组合触发，但应生成原创抽象模板，例如“凡俗出身 + 普通灵根 + 长寿异质”触发长生观察路线，或“凡体 + 没落古族 + 古老血脉”触发肉身证道路线；不得复刻具体作品角色或剧情。
解锁条件
紫色：游玩一次之后可以自行选择（主动结束也算）
橙色：通关一次之后可以自行选择（飞升才算通关）
红色：通关二次之后可以自行选择（飞升才算通关）

稀有度	单抽基础概率	整数权重（总和 300）	定位说明
白色	45%	90	过渡级，最基础的泛用天赋
绿色	30%	60	新手期主力，易获取易成型
蓝色	15%	30	前中期核心，多数玩家的主力配置
紫色	7%	14	后期毕业核心，常规稀有度上限
橙色	2.5%	5	顶级战力，稀有度高，具备收藏价值
红色	0.5%	1	版本天花板，极稀有，拉开上限差距

## 12. 立项前确认清单

- [√] 同意将产品首要实现目标切为游戏模式。
- [√] 同意引导模式、小说模式暂不开放。
- [√] 同意 D 固定为气运/天命选项，不再提供自由输入。
- [√] 同意回合时间动态推进，不再固定为 1 年。
- [√] 同意第一版日历只显示年龄、流逝年数、剩余寿元。
- [√] 同意六维属性为体魄、神魂、气运、悟性、心性、根骨。
- [√] 同意 HP/MP 不进入游戏模式。
- [√] 同意按第 9 节分阶段实施。

批准后，本节清单可转为实施里程碑验收清单。
