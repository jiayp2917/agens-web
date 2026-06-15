# 文字修仙模拟器 — 全流程修复与演示报告

**日期**: 2026-06-13
**分支**: master
**测试结果**: 584 passed, 0 failed

---

## 一、修复摘要

### 核心问题修复

| # | 问题 | 修复方式 | 文件 |
|---|------|---------|------|
| 1 | 小层不推进 | 新增 `RealmSystem.try_advance_stage()` 自动推进机制，每行动后检查 XP 阈值 | `src/agens_novel/game/realm.py` |
| 2 | StatusBar 不显示层数 | 添加中文化层数标签 (练气三层、筑基二层等) | `mobile/widgets/status_bar.py` |
| 3 | 移动端无自然语言突破入口 | 新增 `_parse_breakthrough_action()` 检测突破关键词 | `src/agens_novel/engine/game_engine.py` |
| 4 | 飞升结局未接入 Kivy | 添加 `on_finale` 回调桥接 + DeathScreen 飞升专用 UI | `mobile/service/engine_adapter.py`, `mobile/screens/game_screen.py`, `mobile/screens/death_screen.py` |
| 5 | 突破后 experience_to_next 未重置 | 突破成功时重置为新境界 require 值 | `src/agens_novel/game/realm.py` |

### 修改文件列表 (14 files)

**引擎层 (2)**:
- `src/agens_novel/engine/game_engine.py` — 突破关键词路由、链式阶段推进、`_parse_breakthrough_action`
- `src/agens_novel/game/realm.py` — `try_advance_stage()`、突破后重置 `experience_to_next`

**移动端 (5)**:
- `mobile/widgets/status_bar.py` — 层数显示 (`_stage_label`)
- `mobile/service/engine_adapter.py` — `on_finale` 回调桥接
- `mobile/screens/game_screen.py` — `_on_finale` 处理
- `mobile/screens/death_screen.py` — 飞升/死亡双模式 UI
- `mobile/widgets/action_bar.py` — (已存在，战斗模式提示)

**测试 (2)**:
- `tests/unit/test_game_engine.py` — +8 测试 (阶段推进、突破路由、飞升回调)
- `tests/test_play_simulation.py` — 修复突破关键词冲突

**演示 (1)**:
- `demo_full_flow.py` — Kivy 全流程演示脚本 (mock LLM)

**其他已修改 (无关本次)**:
- `config/prompts/system/judge.md`, `config/prompts/system/narrator.md`
- `mobile/screens/character_create_screen.py`, `mobile/screens/home_screen.py`
- `mobile/widgets/combat_bar.py`, `mobile/widgets/loading_overlay.py`, `mobile/widgets/narrative_view.py`

---

## 二、测试结果

```
584 passed in 42.66s
```

### 新增测试 (8 个)

**TestStageAdvancement**:
- `test_advance_stage_on_xp_threshold` — XP 达标自动升层
- `test_no_advance_at_max_stage` — 满层时不再推进
- `test_chain_multiple_stages_in_action` — 高 XP 一次行动连升多层

**TestBreakthroughRouting**:
- `test_parse_breakthrough_action` — 检测「突破」「尝试突破」「冲击筑基」等关键词
- `test_breakthrough_not_during_combat` — 战斗中不路由突破
- `test_handle_action_routes_breakthrough` — 键入突破文字正确路由到 `attempt_breakthrough`

**TestFinaleCallback**:
- `test_finale_callback_on_ascension` — 突破至飞升触发 `on_finale`
- `test_death_screen_no_finale_for_normal_death` — 普通死亡不触发 finale

---

## 三、可视化全流程演示结果

**结果: ✅ 成功 — 从练气跑到飞升**

Kivy 窗口可见，通过输入框推进，完整记录每个主境界截图。

### 截图目录

`D:\chat\agens\demo_screenshots\`

| 文件 | 节点 | 大小 |
|------|------|------|
| `01_home0001.png` | 主页 | 162KB |
| `02_character_create0001.png` | 角色创建 | 162KB |
| `03_qi_refining0001.png` | 练气 | 52KB |
| `04_foundation0001.png` | 筑基 | 144KB |
| `05_golden_core0001.png` | 金丹 | 146KB |
| `06_nascent_soul0001.png` | 元婴 | 130KB |
| `07_spirit_transformation0001.png` | 化神 | 140KB |
| `08_unity0001.png` | 合体 | 133KB |
| `09_maha0001.png` | 大乘 | 135KB |
| `10_tribulation0001.png` | 渡劫 | 134KB |
| `11_ascension0001.png` | 飞升结局 | 39KB |

### 境界轨迹

```
练气一层 → 练气九层 → 突破筑基 → 筑基一层 → 筑基四层 →
突破金丹 → 金丹一层 → 金丹四层 → 突破元婴 → 元婴一层 →
元婴四层 → 突破化神 → 化神一层 → 化神四层 → 突破合体 →
合体一层 → 合体四层 → 突破大乘 → 大乘一层 → 大乘四层 →
突破渡劫 → 渡劫一层 → 渡劫四层 → 冲击飞升 → 🎉 飞升成仙！
```

---

## 四、实现细节

### 1. 小层推进机制

```
玩家键入"闭关修炼/吐纳/历练"等
→ Narrator LLM 返回 experience delta
→ apply_delta 增加 XP
→ try_advance_stage() 循环检查:
    ├── XP ≥ experience_to_next 且 stage < max_stage → 升一层，扣 XP
    └── XP < experience_to_next 或 已满层 → 停止
→ UI 显示 on_info "修为精进！练气第五层（5/9）"
```

XP 阈值使用 `REALM_CONFIGS[realm].experience_required`，不再随层数累加。

### 2. 自然语言突破触发

关键词匹配 (支持空格分隔):
- `突破`, `尝试突破`, `冲关`, `破境`
- `冲击筑基/金丹/元婴/化神/合体/大乘/渡劫/飞升`
- `准备突破`, `准备渡劫`, `渡劫飞升`

战斗中不路由突破。突破资格由 `RealmSystem.can_attempt_breakthrough()` 判定。

### 3. 飞升结局 UI

- `EngineAdapter` 新增 `on_finale` 回调桥接
- `GameScreen._on_finale()` → 设置 DeathScreen `is_finale=True`
- DeathScreen 飞升模式:
  - 标题: "飞升成仙" (success_color 绿色)
  - 按钮: "再入轮回"
  - 文案: "九天之上，金光万丈。你回望凡尘最后一缕云烟，踏过天门..."

### 4. 突破后 experience_to_next 修复

之前突破成功后 `experience_to_next` 保持旧值，导致新境界的 XP 阈值错误。修复后突破 delta 包含新境界的 `experience_required`。

---

## 五、已发现问题与修复记录

| # | 发现 | 修复 |
|---|------|------|
| 1 | 小层不推进 — LLM delta 被 `_sanitize_action_delta` 拦截 | 新增引擎级自动推进 `try_advance_stage()` |
| 2 | `experience_to_next` 随层数累加，导致满层时突破 XP 不足 | 移除层数累加逻辑，使用固定 realm 值 |
| 3 | 突破后 `experience_to_next` 未重置 | 突破 delta 增加新境界值 |
| 4 | "冲击筑基" 不在突破关键词列表 | 补充为完整列表 (筑基→飞升) |
| 5 | 一次行动只升一层 (即使 XP 足够连升) | 引擎改用 while 循环链式推进 |
| 6 | Kivy DeathScreen 无飞升区分 | 添加 `is_finale` 标志和双模式 UI |

---

## 六、剩余风险与建议

1. **截图质量**: `03_qi_refining` (52KB) 和 `11_ascension` (39KB) 明显小于其他截图，可能 UI 渲染不完整 — 建议人工复查。
2. **XP 阈值平衡**: 当前每个境界固定 XP 阈值，小层推进消耗等量 XP。练气 9 层需要 900 XP (9×100)，渡劫 4 层需要 80000 XP (4×20000)。实际游戏中需通过 LLM 返回合理的 XP 增量。
3. **战斗系统**: 键入式战斗已支持，但战斗数值和奖励需实际游玩验证。
4. **移动端兼容性**: demo 在 Windows Kivy 上运行，APK 表现需在真机验证。
5. **Mock LLM 与真实 LLM 差距**: demo 使用确定性 mock，真实 LLM 的响应质量和一致性需单独评估。

---

## 七、执行命令

```powershell
# 运行全量测试
cd D:\chat\agens
.venv\Scripts\python.exe -m pytest -q

# 运行 Kivy 演示 (需 .venv311)
.venv311\Scripts\python.exe demo_full_flow.py

# 仅验证编译
.venv\Scripts\python.exe -m compileall -q src tests mobile\main.py mobile\screens mobile\widgets mobile\service

# 启动正常游戏
.venv311\Scripts\python.exe mobile\main.py
```
