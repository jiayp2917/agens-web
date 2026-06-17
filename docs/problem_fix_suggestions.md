# problem.md 修复建议

生成日期：2026-06-17  
来源：`docs/problem.md` 与当前代码只读分析。本文只给修复建议，不修改业务代码。

## 总体判断

当前问题集中在三类：

1. 叙事文本与结构化状态不同步：模型可以写“练气九层”“获得功法”，但只有 `<state_update>` 中的字段被 `GameSession.apply_delta()` 接收后，状态、背包、功法、地图、任务才会变化。
2. 开局随机度不足：角色创建页仍以固定词条和固定默认地点为主，`game_name` 没有充分参与 World Builder 开局生成。
3. 移动端交互反馈不足：模型异常、设置/输入/键盘遮挡等状态没有给玩家足够明确的可见反馈。

建议按 P1 到 P3 分批修复。

## P1：状态与叙事一致性

### 1. “叙事为练气9层，但状态仍是练气1层”

现象：叙事文本显示境界或层数提升，但顶部状态栏始终没有变化，导致玩家认为无法突破。

当前代码事实：

- 权威状态来自 `GameSession.realm`、`GameSession.realm_stage`、`experience`、`insight`、`breakthrough_flags`。
- 状态只会通过 `GameSession.apply_delta()` 和 `RealmSystem.try_advance_stage()` 改变。
- 叙事文本本身不会改变状态。

建议修复：

1. 明确“状态是唯一真相”：Narrator 不允许在叙事中宣称层数变化，除非 `<state_update>` 同步给出 `character.experience` 或合法的 `realm_stage`。
2. 在 `GameEngine.handle_action()` 中记录本回合结构化变化摘要，例如“修为 +15，当前练气二层，经验 30/100”。
3. 对 Narrator 输出增加一致性检查：如果叙事出现“练气九层/筑基/突破成功”等关键词，但 `state_delta` 没有对应状态变化，则给 Judge 标记为不通过，或丢弃这段不一致叙事并提示“天道记录以状态栏为准”。
4. 增加回归测试：模型叙事声称升到练气九层，但 delta 为空时，状态不得变化，并必须出现可见提示；模型给出经验增量时，`try_advance_stage()` 能正常推进小层。

涉及文件：

- `src/agens_novel/engine/game_engine.py`
- `src/agens_novel/session/game_session.py`
- `src/agens_novel/game/realm.py`
- `config/prompts/system/narrator.md`
- `config/prompts/system/judge.md`

### 2. “更多”中的背包、功法、地图、装备、任务不随模型内容变化

现象：模型叙事里写获得物品、学会功法、发现地点或接到任务，但“更多”面板仍不变。

当前代码事实：

- `apply_delta()` 已支持 `inventory_add`、`techniques_add`、`equipment_slots`、`active_quests_add`、`discovered_add`。
- “更多”面板读取的是 Session 当前状态，所以只要 delta 正确写入，UI 理论上会变化。

主要原因判断：模型叙事没有稳定输出对应结构化字段，或 Judge 拒绝/修正后字段丢失。

建议修复：

1. 强化 Narrator prompt：凡叙事中出现“获得/拾取/购买/奖励”，必须输出 `character.inventory_add`；出现“习得/传授/领悟功法”，必须输出 `character.techniques_add`；出现“发现地点”，必须输出 `world.discovered_add`；出现“接取任务”，必须输出 `world.active_quests_add`。
2. 强化 Judge prompt：叙事中声明获得资源但 delta 缺失时，判定为不一致，要求补正 `corrected_delta`。
3. 增加引擎侧轻量校验日志：记录每回合 `state_delta` 是否包含背包/功法/地图/任务变化，方便 USB 真机 logcat 定位。
4. 增加测试：模拟 Narrator 返回 `inventory_add`、`techniques_add`、`active_quests_add`、`discovered_add`，验证 `adapter.get_inventory()`、`get_skills()`、`get_quests()`、`get_map()` 立即可见。

## P1：模型异常与“天道紊乱”

### 3. “出现天道紊乱，但模型实际继续返回输出”

现象：玩家看到模型后台有返回，界面却弹出“天道紊乱”，点击本地兜底后又看到模型内容继续出现。

当前代码事实：

- Narrator 支持流式输出，UI 会先显示 streaming chunk。
- 最终如果解析失败、缺少 choices、返回 `llm_error` 或 Judge 失败，GameEngine 可能进入本地兜底。
- 因此“有文本输出”不等于“本回合模型结果可被游戏接受”。

建议修复：

1. 把模型异常拆成明确类型：
   - 请求失败：无 key、超时、认证失败、网络错误。
   - 输出不完整：有叙事，但缺 `<choices>` 或 `<state_update>` 格式错误。
   - 审核失败：Narrator 成功，但 Judge 拒绝状态变化。
2. UI 文案区分以上类型。不要所有情况都叫“天道紊乱”，例如“模型已返回叙事，但选项格式不完整，是否本地补全 A/B/C？”。
3. 流式输出改为事务式：先显示为“推演中”，最终解析成功后再固化到叙事区；若解析失败，则清理未确认流式文本或标记为“未采纳的残影”。
4. 记录脱敏诊断信息：provider、model、base_url、是否有 key、请求耗时、错误类型、是否解析到 narrative/state_delta/choices，不记录 key 明文。

涉及文件：

- `src/agens_novel/engine/game_engine.py`
- `mobile/screens/game_screen.py`
- `src/agens_novel/agents/narrator/nodes.py`
- `src/agens_novel/agents/judge/nodes.py`
- `src/agens_novel/llm/client.py`

## P2：开局与角色创建

### 4. “所有开局默认为青玄宗，建议与游戏名称联动”

现象：玩家修改游戏名称，但开局地点、宗门、世界背景仍偏向固定“青玄宗”。

当前代码事实：

- 角色创建默认 `game_name` 是固定文本。
- `GameEngine.start_from_profile()` 默认 `current_scene/location` 是“青玄宗山门”。
- `_profile_concept()` 当前没有充分把 `game_name` 作为世界种子传给 World Builder。

建议修复：

1. 将 `game_name` 纳入 `_profile_concept()`，明确要求 World Builder 根据游戏名称生成宗门、地域、开局矛盾和初始 A/B/C。
2. 本地兜底也要使用 `game_name`：当模型失败时，根据游戏名称生成简短地点和开场，不再全部回到青玄宗。
3. `game_name` 为空时才使用默认宗门。
4. 增加测试：输入不同游戏名称时，World Builder prompt 中包含该名称；模型失败时 fallback opening 也不同。

涉及文件：

- `mobile/screens/character_create_screen.py`
- `src/agens_novel/engine/game_engine.py`
- `config/prompts/system/world_builder.md`

### 5. “天赋、灵根、家世词条有限且可随意选择，建议随机自动生成”

现象：当前 Spinner 是固定枚举，玩家可以直接选高价值词条，开局不够随机。

建议修复：

1. 角色创建页改成“随机为主”：保留姓名、游戏名称、难度；天赋、灵根、家世、属性由“随机生成”按钮统一生成。
2. 随机结果显示为只读摘要，避免直接挑顶级词条。
3. 随机分两层：
   - 本地随机：无 key 时可用，基于扩展词库和权重。
   - 模型随机：有 key 时由 World Builder 生成更贴合游戏名称的天赋、灵根、家世说明。
4. 顶级词条保留低概率，不在 UI 明示隐藏规则。
5. 增加测试：随机结果满足权重范围，且开始游戏时 profile 使用随机结果。

涉及文件：

- `mobile/screens/character_create_screen.py`
- `src/agens_novel/game/constants.py`
- `src/agens_novel/engine/game_engine.py`
- `config/prompts/system/world_builder.md`

## P2：移动端输入体验

### 6. “手机键盘弹出遮挡游戏画面，无法确认输入内容”

现象：D 输入框聚焦后，软键盘遮挡底部输入和叙事内容。

建议修复：

1. Android 端设置 Kivy 软键盘策略，例如 `Window.softinput_mode = "below_target"` 或 `resize`，以真机效果为准。
2. 输入框聚焦时临时抬高底部 ActionBar，给键盘预留安全区。
3. 在输入框上方显示一行“当前输入预览”，即使键盘遮挡底部，也能确认文本。
4. 发送后在叙事区立即回显 `> 玩家输入`，当前已有类似回显，建议确认软键盘状态下仍可见。
5. USB 真机验证必须截图：聚焦前、键盘弹出、输入中文、发送后四张。

涉及文件：

- `mobile/main.py`
- `mobile/widgets/action_bar.py`
- `mobile/screens/game_screen.py`

## 建议修复顺序

1. P1-模型异常分类与流式输出事务化。
2. P1-叙事与结构化状态一致性。
3. P1-背包/功法/地图/任务 delta 契约和测试。
4. P2-开局 `game_name` 联动。
5. P2-随机角色生成改造。
6. P2-软键盘遮挡优化。

## 最小验收方案

### 自动化

```powershell
cd D:\chat\agens
.\.venv\Scripts\python.exe -m compileall -q src tests mobile\main.py mobile\screens mobile\widgets mobile\service
.\.venv\Scripts\python.exe -m pytest -q tests\unit\engine tests\unit\game tests\mobile
```

新增或更新测试重点：

- Narrator 叙事和 `state_delta` 不一致时不误改状态。
- `inventory_add`、`techniques_add`、`active_quests_add`、`discovered_add` 能反映到“更多”面板读取结果。
- 模型有文本但缺 choices 时，UI 显示“输出不完整”而不是泛化为请求失败。
- 不同 `game_name` 生成不同开局种子。
- 随机角色生成不能直接手选顶级词条。

### USB 真机

只使用 USB 真机验证，建议路径：

1. 安装最新 APK。
2. 清空 logcat。
3. 打开设置，确认当前 provider/model/key 脱敏摘要。
4. 创建两个不同游戏名称的新档，确认开局地点和背景不同。
5. 游玩 5-10 回合，分别触发获得物品、习得功法、发现地点、接取任务。
6. 打开“更多”，确认背包、功法、地图、任务同步变化。
7. 聚焦 D 输入框，截图确认键盘不遮挡关键输入预览。
8. 若出现模型异常，拉取 logcat，确认异常类型清晰可区分。

## 不建议的修复方式

- 不建议让叙事文本直接驱动状态变化，容易被模型幻觉污染存档。
- 不建议因为模型偶尔输出不完整就完全关闭本地兜底；应保留兜底，但要明确说明兜底原因。
- 不建议恢复多自由度模式或旧终端入口。
- 不建议把 API key 写入文档、日志、仓库或普通设置文件。
