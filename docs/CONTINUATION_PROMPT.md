# AI 修仙模拟器 — 后续开发提示词

> **用途**: 将此提示词粘贴到新会话中，AI 即可无缝接续开发工作。
> **项目路径**: `D:\chat\agens`
> **当前版本**: v0.3.0-dev | **测试状态**: 435/435 通过

---

## 一、项目概述

AI 驱动的修仙文字冒险游戏，移动端（Kivy）+ 终端（REPL）双前端，LLM 生成叙事 + 半结构化数值引擎。

**核心架构**: GameEngine(回调驱动) → LangGraph Agent(Narrator/Judge/WorldBuilder) → LLM(httpx + OpenAI 兼容 API)

**已实现功能**:
- ✅ 9 境界体系（练气→飞升，前 5 境界完整逻辑，后 4 预留数据）
- ✅ 8 种灵根（金/木/水/火/土 地灵根 + 冰/雷/风 天灵根）
- ✅ 回合制战斗系统（CombatEngine 状态机：idle→player_turn→enemy_turn→resolve）
- ✅ 流式叙事（SSE → on_stream_chunk → NarrativeView.append_chunk）
- ✅ 内置 Agens API Key（base64 编码，三级优先级：用户自定义 > 环境变量 > 内置默认）
- ✅ Judge 默认拒绝（approved=False on parse failure）
- ✅ HP 归零检测 + Game Over 流程
- ✅ 多存档槽位（5 手动 + 1 自动）
- ✅ NPC 好感度系统（-100~100）
- ✅ 物品/装备系统（6 类型 + 3 装备位 + 品质等级）
- ✅ 任务系统（4 类型：主线/支线/NPC/日常）
- ✅ 移动端 UI（Kivy：GameScreen/CombatScreen/SaveScreen/SettingsScreen/TutorialScreen）

---

## 二、关键文件地图

```
src/agens_novel/
  game/
    constants.py    ← 9境界定义、8灵根、品质/装备位/战斗常量
    realm.py        ← RealmSystem: 突破判定、灵根修正
    combat.py       ← CombatEngine: 战斗状态机(6阶段)、伤害计算
  state/
    game_schema.py  ← TypedDict: CombatState/CombatActor/InventoryItem/NpcInfo/QuestInfo
    reducers.py     ← apply_combat_delta reducer
  engine/
    game_engine.py  ← GameEngine: handle_action/combat/breakthrough/game_over + 流式回调
    render.py       ← format_combat/format_realm/format_equipment
  repl/
    game_session.py ← GameSession dataclass + apply_delta + 序列化（导入用 ..game.constants）
    save_manager.py ← 多槽位存档
    turn_runner.py  ← stream_callback 透传
  llm/
    client.py       ← call_llm/call_llm_stream + 内置 Key(base64) + 三级优先级
  agents/
    narrator/nodes.py  ← 流式回调 + 战斗叙事提示词自动追加
    judge/nodes.py     ← 默认 approved=False

mobile/
  main.py                    ← App 入口 + 内置 Key 注入
  screens/
    game_screen.py           ← 主游戏（集成 CombatBar/LoadingOverlay/流式/Game Over）
    combat_screen.py         ← 独立战斗界面
    save_screen.py           ← 多存档管理
    settings_screen.py       ← 模型切换 + 内置 Key 状态
    tutorial_screen.py       ← 6 页新手引导
  widgets/
    combat_bar.py            ← 5 操作按钮 + 功法/丹药选择弹窗
    loading_overlay.py       ← 半透明加载动画
    realm_card.py            ← 境界信息卡
    narrative_view.py        ← append_chunk 流式追加
    status_bar.py            ← 双行：境界/灵根/HP/MP/战斗/装备
    action_bar.py            ← 战斗模式切换
  service/
    engine_adapter.py        ← on_stream_chunk/on_combat_update 回调
    settings_store.py        ← user_model.json 持久化 + is_using_builtin_key()
    save_manager_compat.py   ← Android 路径

config/
  prompts/system/
    narrator.md          ← 战斗/突破/NPC好感度/装备规则
    combat_narrator.md   ← 战斗场景专用补充
    judge.md             ← 战斗数值审查/境界规则
    world_builder.md     ← 灵根8种/NPC增强/任务类型
  default.yaml           ← 9境界 + 战斗/突破配置
```

---

## 三、已确认的设计约定

| 约定 | 说明 |
|------|------|
| 导入路径 | `repl/` 中用 `from ..game.constants`（双点，非单点） |
| API Key 优先级 | 用户自定义(settings.json) > 环境变量 > 内置默认(base64) |
| Judge 默认 | 解析失败 → approved=False（安全默认） |
| HP 钳位 | apply_delta 后 HP ∈ [0, hp_max] |
| _has_api_key() | 始终返回 True（内置 Key fallback） |
| delta 格式 | 数值: 整数=绝对赋值, "+N"/"-N"=增量; 列表: xxx_add=追加, xxx=替换 |
| 回调签名 | on_stream_chunk(text), on_combat_update(combat_state), on_game_over(reason) |
| 线程桥接 | EngineAdapter 用 threading + Clock.schedule_once 回 Kivy 主线程 |
| 存档格式 | alpha 阶段允许破坏性升级 |

---

## 四、待办事项（按优先级）

### P0 — 端到端可用性（当前阻塞项）

- [ ] **E2E 冒烟测试**: 启动 REPL 模式，完成一轮"新游戏→输入行动→收到叙事→存档→读档"全流程
- [ ] **内置 Key 验证**: 确认内置 Agens Key 是否真实有效（当前 base64 占位符需替换为真实 Key）
- [ ] **流式叙事端到端验证**: 确认 SSE 流从 LLM → narrator → GameEngine → EngineAdapter → NarrativeView 完整贯通
- [ ] **战斗端到端验证**: 触发战斗 → 选择操作 → AI 生成战斗叙事 → HP 变更 → 战斗结束

### P1 — 移动端可玩

- [ ] **Kivy 桌面端调试**: `python mobile/main.py` 在桌面运行，验证所有 Screen 和 Widget
- [ ] **buildozer APK 打包**: 执行 `buildozer android debug`，确认 arm64 构建成功
- [ ] **真机安装测试**: APK 安装到 Android 设备，验证触控交互、软键盘、存档路径
- [ ] **内容过滤**: 移动端上架需基础敏感词过滤（Judge 提示词增强 或 新增过滤层）
- [ ] **后 4 境界逻辑补全**: 合体/大乘/渡劫/飞升 的突破判定、天劫叙事（当前仅数据定义）
- [ ] **模型切换实时生效**: 确认设置页修改模型后，下次 LLM 调用使用新配置

### P2 — 体验增强

- [ ] **成就系统**: 特定条件解锁成就（首次突破/击败强敌/收集全套）
- [ ] **离线修炼**: APP 关闭后按时间计算少量修炼进度，启动时结算
- [ ] **灵根觉醒选择**: 开局选择灵根类型（当前由 WorldBuilder 随机分配）
- [ ] **深色/浅色主题**: Kivy 主题切换
- [ ] **音效**: 突破/战斗/死亡关键事件音效反馈
- [ ] **事件日志时间线**: 按境界/类型筛选的完整事件时间线

### P3 — 长期演进

- [ ] **Web 前端**: FastAPI + WebSocket，浏览器中游玩
- [ ] **云存档同步**: 可选登录，存档上传/下载
- [ ] **Android Service 保活**: 后台修炼进度持续计算
- [ ] **本地小模型回退**: Ollama/llama.cpp 离线模式

---

## 五、PRD 待决策问题

| # | 问题 | 建议选项 | 状态 |
|---|------|---------|------|
| Q1 | 内置 Key 速率限制 | 每用户 100 次/天 | ⏳ 需与 Agens 方确认 |
| Q2 | 后 4 境界何时实现 | v0.4.0 版本 | ⏳ 待定 |
| Q3 | 战斗复杂度 | 半结构化（已采纳） | ✅ 已决策 |
| Q4 | 联网登录 | 纯离线（已采纳） | ✅ 已决策 |
| Q5 | 移动端框架 | Kivy（已确认） | ✅ 已决策 |
| Q6 | 内置 Key 合规 | 需与 Agens 方确认 | ⏳ 待定 |
| Q7 | 内容过滤 | 基础敏感词过滤 | ⏳ 移动端上架前必须 |
| Q8 | 存档兼容 | 可破坏升级（已采纳） | ✅ 已决策 |

---

## 六、运行与测试命令

```bash
# 终端 REPL 模式
cd D:\chat\agens
python -m agens_novel.repl.loop

# 运行全部测试（435 项）
python -m pytest tests/ -q

# 运行单个模块测试
python -m pytest tests/unit/test_combat.py -v
python -m pytest tests/unit/test_realm.py -v

# Kivy 桌面调试
cd D:\chat\agens\mobile
python main.py

# APK 打包（需 Linux 环境 + buildozer）
cd D:\chat\agens\mobile
buildozer android debug

# 语法检查全部文件
python -c "
import ast, pathlib
for f in pathlib.Path('src').rglob('*.py'):
    ast.parse(f.read_text(encoding='utf-8'))
print('All files OK')
"
```

---

## 七、常见陷阱提醒

1. **导入路径**: `repl/game_session.py` 必须用 `from ..game.constants`（双点），不是 `from .game.constants`
2. **asyncio 嵌套**: Kivy 环境中不能直接 `asyncio.run()`，必须走 EngineAdapter 线程桥接
3. **LangGraph MemorySaver**: 进程内检查点，退出即丢失；持久化依赖 save_manager.py
4. **内置 Key 占位符**: 当前 base64 编码的 Key 需替换为真实 Agens API Key 才能实际调用 LLM
5. **settings 双源**: 桌面端用环境变量，移动端用 JSON 文件 + apply_settings_to_env()
6. **bool 守卫**: apply_delta 中 bool 值被忽略（防止 True/False 被当 1/0）
7. **combat 字段**: GameSession.combat 为 None 时表示非战斗状态，非战斗时 CombatBar 应隐藏
8. **流式结束**: 流式输出结束后仍需走 Judge → apply_delta 完整路径
