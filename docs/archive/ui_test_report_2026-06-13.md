# 已归档

本文档为历史 UI 测试与问题记录，仅用于追溯旧移动端结构，不作为当前实现依据。当前实现请以仓库根目录 `AGENTS.md`、`docs/prototypes/` 和最新交付报告为准。

# UI 测试问题报告

**日期**: 2026-06-13
**测试环境**: 桌面 Kivy (Python 3.11.9 + Kivy 2.3.1, Windows 11)
**主题**: 明亮白 (默认)
**截图**: 用户在游戏中实际操作后提供
**更新**: 2026-06-13 追加第二轮测试记录 + 用户交互设计需求

---

## 修复状态（2026-06-13 第二次更新）

所有报告中的致命/严重问题已修复。测试结果：**537 passed, 0 failed**。

| # | 问题 | 修复状态 | 修复内容 |
|---|------|---------|---------|
| 1 | JSON 泄露到流式 UI | ✅ 已修复 | `NarrativeView.append_chunk()` 缓冲过滤 `<state_update>` 标签 |
| 2 | msgpack 序列化错误 | ✅ 已修复 | `stream_callback` 通过 `threading.local()` 传递，不再进入 LangGraph state |
| 3 | 颜色对比度不足 | ✅ 已修复 | `text_secondary` 0.45→0.35, `text_hint` 0.6→0.45 |
| 4 | 按钮行挤压 | ✅ 已缓解 | 按钮重组（主页/新游戏/状态/背包/功法/存档/读档/突破）+ 输入框命令 |
| 5 | 叙事区域比例 | ✅ 自动解决 | 随问题 1 修复 |
| 6 | 弹窗背景不统一 | ✅ 已修复 | `themed_popup` 设 `background=""` 覆盖默认深色 9-patch |
| 7 | 叙事区信息污染 | ✅ 自动解决 | 随问题 2 修复 |
| 8 | 固定按钮 vs 自由输入 | ✅ 已修复 | 输入框支持 `/command` 斜杠命令（中英文双语） |
| - | 无主界面 | ✅ 已修复 | 新建 `HomeScreen`（主页/新游戏/存档管理/设置/退出） |
| - | 存档无选择 | ✅ 已修复 | 存档/读档弹窗支持 5 个档位选择 + 快速存读档 |

### 新增文件

| 文件 | 用途 |
|------|------|
| `src/agens_novel/repl/_stream_context.py` | 线程局部上下文传递 stream_callback |
| `mobile/screens/home_screen.py` | 主界面 Screen |
| `tests/unit/test_ui_fixes.py` | UI 修复验证测试（52 个） |
| `tests/unit/test_e2e_destructive.py` | e2e 破坏性测试（40 个） |

### 代码质量审查发现

| 严重度 | 数量 | 关键问题 |
|--------|------|---------|
| Medium | 12 | 三重 agent 代码重复、base64 key 双处同步、已修复的 import bug |
| Low | 19 | 未使用 imports、dead constants、dead methods、orphan modules |

完整审查报告已记录在本次会话中。

---

## 问题总览

| # | 严重度 | 类别 | 概要 |
|---|--------|------|------|
| 1 | **致命** | 内容显示 | LLM 返回的 `<state_update>` JSON 原始文本直接显示给玩家 |
| 2 | **致命** | 运行时错误 | 每次 narrator 调用后均抛出 `TypeError: Type is not msgpack serializable: method` |
| 3 | **严重** | 颜色/视觉 | 状态栏文字颜色与背景对比度不足，文字难以辨识 |
| 4 | **中等** | UI 布局 | 按钮行 10 个按钮横向挤压，文字溢出或过小 |
| 5 | **中等** | UI 布局 | 叙事区域与状态栏/操作栏比例失调，有效叙事区域过小 |
| 6 | **低** | 体验 | 弹窗深灰背景与明亮白主题风格不统一 |

---

## 问题 1: LLM 原始 JSON 直接显示给玩家

### 现象

玩家输入任何行动后，叙事区域不仅显示叙事文本，还完整显示 `<state_update>` JSON 块，例如：

```
<state_update>
{
  "character": {
    "mp": "-5"
  },
  "world": {
    "current_scene": "寂静幽深的青云山小径"
  },
  "meta": {
    "game_over": false
  }
}
</state_update>
```

### 根因分析

**流式传输时，`_parse_narrator_output` 的剥离逻辑未作用于流式文本。**

调用链：

1. 玩家输入 → `GameScreen._on_user_action()` → `adapter.handle_action()` → 后台线程
2. `GameEngine.handle_action()` 调用 `run_turn_sync("narrator", ..., stream_callback=self._stream_callback)`
3. `turn_runner.py:88-89`: 把 `stream_callback` 放入 LangGraph state dict
4. `narrator/nodes.py:120-129`: `call_agnes_llm` 用 `call_llm_stream` 流式接收 **每个 chunk**
5. **每个 chunk 通过 `stream_callback` → `engine.on_stream_chunk` → `engine_adapter` → `Clock.schedule_once` → `NarrativeView.append_chunk()` 直接追加到 UI Label**
6. 最终 `save_artifact` 的 `_parse_narrator_output` **确实会剥离 JSON** 并返回干净的 `narrative` 文本
7. 但此时流式文本已经全部显示在 UI 上了

**关键矛盾**: 流式模式下，LLM 原始输出（含 `<state_update>` 标签和 JSON）已经逐 chunk 显示给用户。事后 `save_artifact` 剥离了 JSON 并触发 `on_narrative` 回调（会调用 `finalize_stream()` + `add_narrative(clean_text)`），但用户已经看到了完整原始输出。

### 相关文件

| 文件 | 行号 | 职责 |
|------|------|------|
| `src/agens_novel/agents/narrator/nodes.py` | L96-149 | `call_agnes_llm` — 流式 chunk 无过滤直接回调 |
| `src/agens_novel/agents/narrator/nodes.py` | L199-221 | `_parse_narrator_output` — 只在 `save_artifact` 阶段剥离 |
| `src/agens_novel/engine/game_engine.py` | L196-212 | `handle_action` — 先流式，后解析；解析成功/失败都直接传 narrative |
| `mobile/widgets/narrative_view.py` | L78-109 | `append_chunk` — 无条件显示 chunk 文本 |
| `mobile/service/engine_adapter.py` | L51-52 | 流式回调桥接到 Kivy 主线程 |

### 建议修复方向

**方案 A: 客户端缓冲过滤（推荐）**
- `NarrativeView.append_chunk()` 缓存 chunk，检测到 `<state_update>` 后停止显示
- `finalize_stream()` 或 `add_narrative()` 时清除流式 label，用干净 narrative 替换

**方案 B: 服务端预过滤**
- `call_agnes_llm` 的 `on_chunk` 回调里拦截含 `<state_update>` 的 chunk，不向 UI 推送
- 需要状态机跟踪"是否已进入 `<state_update>` 区域"

---

## 问题 2: msgpack 序列化错误（每次 narrator 调用必现）

### 现象

日志中每次 narrator 调用都产生同样的错误：

```
[ERROR] narrator error
...
  File "langgraph/checkpoint/serde/jsonplus.py", line 860, in _msgpack_enc
    return ormsgpack.packb(data, default=_msgpack_default, option=_option)
TypeError: Type is not msgpack serializable: method
```

### 根因分析

`turn_runner.py:88-89` 将 `stream_callback`（一个 Python method/bindable function）放入 LangGraph state dict：

```python
if agent_name == "narrator" and stream_callback is not None:
    state["stream_callback"] = stream_callback
```

LangGraph 使用 `MemorySaver` 做 checkpoint，checkpoint 时会用 msgpack 序列化 state 中所有值。Python method 不是 msgpack 可序列化类型，导致 **每次 checkpoint 都失败**。

虽然 LLM 调用本身成功了（artifact 正常写入），但 checkpoint 失败导致：
- 叙事结果被 `_parse_narrator_output` 正确解析，却因外层 try/except 被吞掉
- `game_engine.py:202-206` 的 `except Exception` 捕获了这个 TypeError
- 玩家看到 `[错误] 叙述失败（详见日志）`
- 但流式文本已经显示出来了（因为 chunk 回调发生在 checkpoint 失败之前）

### 相关文件

| 文件 | 行号 | 职责 |
|------|------|------|
| `src/agens_novel/repl/turn_runner.py` | L62-63, L88-89 | `stream_callback` 放入 state，未在进入 graph 前移除 |
| `src/agens_novel/agents/narrator/graph.py` | L27 | `MemorySaver()` 做 checkpointer |
| `src/agens_novel/engine/game_engine.py` | L198-206 | 捕获异常，显示"叙述失败" |

### 建议修复方向

`turn_runner.py` 在构建 state 时，将 `stream_callback` 从 kwargs 中 pop 出来后，**不要放入 state dict**。改为：
- 从 state 中移除 `stream_callback`
- 在 `call_agnes_llm` 中通过其他方式传递（如闭包/全局 context）
- 或在 graph 编译时用 `MemorySaver()` 之外的方式，或自定义 serde 跳过不可序列化字段

---

## 问题 3: 颜色冲突 / 文字难以辨识

### 现象

从截图看，明亮白主题下：
- **状态栏背景** `surface=(1.0, 1.0, 1.0, 1)` — 纯白
- **主文字色** `text=(0.13, 0.13, 0.13, 1)` — 近黑
- **次要文字色** `text_secondary=(0.45, 0.45, 0.45, 1)` — 中灰
- **提示文字色** `text_hint=(0.6, 0.6, 0.6, 1)` — 浅灰

问题在于：
1. **状态栏高度仅 56dp**（两行 22+28dp），内含 7 个标签 + 3 个进度条 + 5 个数值标签，全部是纯文字无图标区分
2. `text_secondary` 灰 0.45 在白底上对比度约 3.2:1，**未达到 WCAG AA 标准（4.5:1）**
3. `text_hint` 灰 0.6 对比度约 2.1:1，**严重不可读**
4. 进度条 HP 绿 `(0.2, 0.75, 0.3, 1)` 和 MP 蓝 `(0.25, 0.45, 0.85, 1)` 在灰底 `bar_bg=(0.85, 0.85, 0.88, 1)` 上视觉区分度足够

### 相关文件

| 文件 | 行号 |
|------|------|
| `mobile/theme.py` | L55-76（WHITE palette） |
| `mobile/widgets/status_bar.py` | L18-137（整个 StatusBar） |

### 建议修复方向

- `text_secondary` 调暗至 `(0.35, 0.35, 0.35, 1)` → 对比度 ~5.6:1
- `text_hint` 调暗至 `(0.45, 0.45, 0.45, 1)` → 对比度 ~3.9:1（勉强可用）或改为带主题色前缀标签区分
- 状态栏用更鲜明的色彩区分区域（如 HP 红底标签、MP 蓝底标签）

---

## 问题 4: 按钮行挤压

### 现象

`GameActionBar` 底部有 10 个按钮（8 个普通 + 2 个战斗模式），全部横向排列在一个 `height=dp(36)` 的 `BoxLayout` 中。每个按钮 `size_hint_x=None, width=dp(52)`。

10 × 52dp = 520dp。在窗口宽度较小时（截图显示约 1280px 但 Kivy 按钮实际渲染可能更窄），按钮互相挤压，导致：
- 中文字体 11dp 在 52dp 宽度内基本可显示 2 个字
- 但"新游戏"（3字）、"突破"（2字）、"装备"（2字）在窄屏幕上可能溢出
- 按钮间距仅 `spacing=dp(2)`，视觉拥挤

### 相关文件

| 文件 | 行号 |
|------|------|
| `mobile/widgets/action_bar.py` | L26-41, L97-109 |

### 建议修复方向

- 分两行排列：上行 5 个核心按钮（新游戏/状态/背包/功法/地图），下行 5 个（任务/存档/读档/突破/装备）
- 或使用 `ScrollView` 包裹按钮行，允许水平滚动
- 减少按钮数量：合并"突破"到状态面板内、"装备"到背包面板内

---

## 问题 5: 叙事区域比例过小

### 现象

从截图分析，整个窗口纵向分配：

| 区域 | 高度 |
|------|------|
| StatusBar | 56dp (固定) |
| RealmCard | ~40dp (固定) |
| NarrativeView | `size_hint_y=1` 占剩余空间 |
| CombatBar | 0dp (隐藏) |
| GameActionBar | 100dp (固定) |

在 ~800dp 高度的窗口中：叙事区域 = 800 - 56 - 40 - 100 = **604dp**，理论上足够。

但实际上截图中叙事区域大部分被弹窗（`_show_text_popup` 的 Popup）遮挡，弹窗 `size_hint=(0.85, 0.6)` 占了 60% 高度。弹窗内显示的是原始 JSON（问题 1），导致有效叙事阅读空间为零。

### 相关文件

| 文件 | 行号 |
|------|------|
| `mobile/screens/game_screen.py` | L60-88（布局构建） |
| `mobile/screens/game_screen.py` | L277-299（`_show_text_popup`） |

### 建议修复方向

此问题主要是问题 1（JSON 泄露到叙事区）的连锁反应。修复问题 1 后，叙事区域应该只显示干净的叙事文本，比例会恢复正常。

---

## 问题 6: 弹窗风格与主题不统一

### 现象

Kivy `Popup` 默认有一个深灰色标题栏和边框，即使 `background_color=theme.surface` 设为白色。截图中弹窗背景偏深灰 `#222222`，与明亮白主题的 `surface=(1.0, 1.0, 1.0, 1)` 不一致。

原因：Kivy Popup 的 `background` 是一个默认的 9-patch 图片（`atlas://data/images/defaulttheme/button`），这个图片本身带深色底纹。`background_color` 是叠加在这个图片上的色调，不能完全覆盖。

### 相关文件

| 文件 | 行号 |
|------|------|
| `mobile/theme.py` | L344-357（`themed_popup`） |

### 建议修复方向

- 在 `themed_popup` 中设置 `popup.background = ''`（空字符串）或提供一个纯白色的 9-patch 图片
- 或者用 `popup.separator_color` + `popup.title_color` + 自定义 background atlas

---

## 附: 日志关键时间线

| 时间 (UTC+8) | 事件 | 结果 |
|--------------|------|------|
| 02:40:05 | World Builder: `new_game` 用户输入 "2" | ✅ 成功，角色创建 |
| 02:40:24 | LLM 200 OK (world_builder) | 2209 chars artifact |
| 02:41:02 | Narrator: 第 1 次调用 (user="2") | ❌ msgpack TypeError |
| 02:41:44 | Narrator: 第 2 次调用 (user="10") | ❌ msgpack TypeError |
| 02:42:06 | Narrator: 第 3 次调用 (user="8") | ❌ msgpack TypeError |
| 02:43:58 | Narrator: 第 4 次调用 (user="5") | ❌ msgpack TypeError |
| 02:47:09 | Narrator: 第 5 次调用 (user="8") | ❌ msgpack TypeError |
| 02:47:38 | Narrator: 第 6 次调用 (user="372") | ❌ msgpack TypeError |
| 02:48:26 | Narrator: 第 7 次调用 (user="126") | ❌ msgpack TypeError |
| 02:48:34 | Narrator: 第 8 次调用 (user="774") | ❌ msgpack TypeError（日志截断） |

**每次 narrator 调用的模式相同**：
1. LLM 调用成功 → artifact 写入 → 流式 chunk 推送到 UI → checkpoint 时 msgpack 失败 → except 吞掉结果 → UI 显示"叙述失败"

---

## LLM 输出样本分析

从 8 次 narrator 输出的 artifact 文件看，LLM 返回格式一致：

```
[叙事文本（2-4 段）]

<state_update>
{
  "character": { ... },
  "world": { ... },
  "meta": { "game_over": false }
}
</state_update>
```

`_parse_narrator_output` **可以正确剥离** JSON（在 `save_artifact` 阶段），但由于问题 2（msgpack 错误在 `save_artifact` 之后的 checkpoint 阶段发生），整个 graph 被标记为失败，`game_engine.py:202` 的 except 捕获并显示"叙述失败"。

**实际上叙事文本已经被流式推送到 UI 了**，只是状态更新（apply_delta）没有执行，所以玩家的 HP/MP/经验等数值始终不变。

---

## 修复优先级建议

| 优先级 | 问题 | 预估工作量 |
|--------|------|-----------|
| P0 | #2 msgpack 序列化（移除 state 中的 stream_callback） | 10 行改动 |
| P0 | #1 JSON 泄露到流式输出（chunk 级过滤） | 30 行改动 |
| P1 | #3 颜色对比度 | 5 行改动（调 palette 数值） |
| P1 | #6 弹窗背景 | 5 行改动 |
| P2 | #4 按钮行布局 | 20 行改动 |
| P2 | #5 叙事区域比例 | 随问题 1 自动解决 |

---

# 第二轮测试记录（2026-06-13 02:50）

## 新截图分析

### 截图 3 描述

**整体布局**: 与截图 1/2 一致（顶部状态栏 + 中间叙事区 + 底部操作栏）

**状态栏正常**:
- HP: 100/100（绿色满条）
- MP: 50/50（蓝色满条）
- 灵根: 木灵根(地级)
- EXP: 0/100（灰色空条）
- 境界: 练气第1层

**叙事区域**（关键问题 — 严重的信息污染）:
- 多行 `[错误] 叙述失败（详见日志）` 反复出现
- 多行 `当前不在战斗中。` 反复出现（约 15 行）
- 用户输入的原始文本 `> 狗日的系统` / `> 你好你是么模型` / `> 真是二比` 可见
- **大量重复的 LLM 原始输出文本**：约 50 行 `你是什么模型你是么模型你是么模型...` — 这是流式 chunk 未经 JSON 剥离直接显示的结果
- 叙事区被错误信息和原始输出淹没，**有效叙事内容为零**

**底部操作栏**:
- 战斗按钮行（普攻/功法/丹药/防御/逃跑）— 蓝色按钮
- 功能按钮行（新游戏/状态/背包/功法/地图/任务/存档/读档/突破/装备）— 蓝色按钮，10 个一行
- 输入框 + 发送按钮

### 新增发现

| # | 严重度 | 类别 | 概要 |
|---|--------|------|------|
| 7 | **致命** | 内容污染 | 错误信息 `[错误] 叙述失败` 和 `当前不在战斗中` 在叙事区大量重复堆积 |
| 8 | **致命** | 交互设计 | 战斗操作（普攻/防御/逃跑）仅通过固定按钮触发，不支持自由输入 |

---

## 问题 7: 叙事区域信息污染

### 现象

每次用户操作失败时，叙事区追加 `[错误] 叙述失败（详见日志）`。由于问题 2（msgpack 错误）导致 **每次操作都失败**，该错误信息不断堆积。同时 `当前不在战斗中。` 也在大量重复。

### 根因

`game_engine.py:204` 的 `_emit("on_error", "叙述失败（详见日志）")` → `game_screen.py:112` 的 `self.narrative_view.add_info(f"[错误] {msg}")` — 每次错误都在叙事区追加一行，没有上限，没有清理机制。

战斗相关的 `当前不在战斗中` 来自 `game_engine.py` 的 `_handle_combat_start_or_update` 或 combat 判断逻辑。

### 建议修复方向

- 修复问题 2（msgpack）后此问题自然消失
- 额外保险：`NarrativeView` 限制错误信息行数（如最近 3 条），或同类错误去重

---

## 问题 8: 交互设计 — 固定按钮 vs 自由输入

### 用户需求

> 普攻、防御逃跑等操作均可通过键盘输入进行，要求自由度高，各种内容非必要均通过输入进行（新游戏、存档、回档等）

### 当前状态

| 操作 | 触发方式 | 问题 |
|------|---------|------|
| 普攻/功法/丹药/防御/逃跑 | 仅 CombatBar 按钮 | 无法通过输入框自由描述战斗动作 |
| 新游戏 | GameActionBar 按钮 + 弹窗 | 无法通过输入框输入 `/new` 触发 |
| 存档/读档 | GameActionBar 按钮 | 无法通过输入框 `/save` `/load` 触发 |
| 状态/背包/功法/地图/任务/装备 | GameActionBar 按钮 → 弹窗 | 无法通过输入查看 |
| 突破 | GameActionBar 按钮 | 无法通过输入框 `/breakthrough` 触发 |
| 自由行动 | 输入框 | ✅ 唯一支持自由输入的入口 |

### 设计分析

当前架构是 **按钮驱动**：所有操作都通过点击按钮 → `_on_command(cmd)` → 间接调用 `GameEngine` 方法。输入框只用于自由文本行动（`_on_user_action` → `adapter.handle_action`）。

`game_screen.py:194-218` 的 `_on_user_command` 是命令分发器，但它只从按钮回调接收 cmd 字符串，不解析输入框文本。

### 建议修复方向

**方案: 输入框命令识别**

在 `_on_user_action` 前加一层命令解析：

```python
def _on_user_action(self, text: str) -> None:
    # 检测 /command 格式
    if text.startswith("/"):
        cmd = parse_slash_command(text)
        if cmd:
            self._on_user_command(cmd)
            return
    # 否则作为自由行动处理
    self.narrative_view.add_info(f"> {text}")
    self.adapter.handle_action(text)
```

支持的命令映射：
- `/new` / `/新游戏` → `_show_new_game_dialog()`
- `/save` / `/存档` → `adapter.save("manual")`
- `/load` / `/读档` → `adapter.load("manual")`
- `/status` / `/状态` → `_show_text_popup("角色状态", ...)`
- `/inv` / `/背包` → `_show_text_popup("背包", ...)`
- `/skills` / `/功法` → `_show_text_popup("功法", ...)`
- `/map` / `/地图` → `_show_text_popup("地图", ...)`
- `/quest` / `/任务` → `_show_text_popup("任务", ...)`
- `/breakthrough` / `/突破` → `_on_breakthrough()`
- `/equipment` / `/装备` → `_show_text_popup("装备", ...)`

战斗操作通过自然语言：
- 用户输入 "用基础剑法攻击敌人" → narrator LLM 识别为战斗动作 → 生成战斗叙事
- 用户输入 "防御" / "逃跑" → narrator 理解意图 → 触发战斗逻辑
- 不需要 `/attack` 等前缀，LLM 本身理解中文战斗意图

**按钮保留但降级为快捷方式**：
- 按钮仍然存在，作为快捷入口
- 但所有操作都可以通过输入框完成
- 战斗按钮（普攻/功法/丹药/防御/逃跑）可以保留作为移动端快捷操作

### 相关文件

| 文件 | 行号 | 职责 |
|------|------|------|
| `mobile/screens/game_screen.py` | L189-217 | `_on_user_action` / `_on_user_command` — 需要合并 |
| `src/agens_novel/repl/commands.py` | 全文件 | 命令解析器（桌面端已有，可复用逻辑） |
| `src/agens_novel/engine/game_engine.py` | L170-259 | `handle_action` — 自由文本处理 |

---

## 日志时间线（第二轮，追加）

| 时间 (UTC+8) | 事件 | 结果 |
|--------------|------|------|
| 02:48:34 | Narrator 第 8 次 (user=774) | ❌ msgpack TypeError |
| 02:50:51 | Narrator 第 9 次 (user=4) | ❌ msgpack TypeError |
| 02:51:20 | Narrator 第 10 次 (user=13) | ❌ msgpack TypeError |

**总计 10 次连续失败**，全部同根因：`stream_callback` 进入 LangGraph state → msgpack 序列化失败。

---

## 修订后修复优先级

| 优先级 | 问题 | 预估工作量 | 影响 |
|--------|------|-----------|------|
| **P0** | #2 msgpack 序列化 | 10 行 | **核心阻塞**：修复后所有叙事+状态更新恢复正常 |
| **P0** | #1 JSON 泄露到流式输出 | 30 行 | 修复后 UI 不再显示原始 JSON |
| **P1** | #8 输入框命令识别 | 40 行 | 用户核心需求：自由输入驱动一切 |
| **P1** | #7 错误信息堆积 | 5 行 | 随 P0 修复自然消失，加保险限制 |
| **P1** | #3 颜色对比度 | 5 行 | 可读性 |
| **P1** | #6 弹窗背景 | 5 行 | 视觉一致性 |
| **P2** | #4 按钮行布局 | 20 行 | 随 P1 简化按钮后自然缓解 |
| **P2** | #5 叙事区域比例 | 随 P0 自动解决 | — |

---

# 第三轮测试记录（2026-06-13 02:56-02:59）

## 用户操作分析

用户在 02:56-02:59 期间继续密集测试，日志新增 473 行（847→1320），**新增 6 次 narrator 调用，全部因 msgpack 失败**。

从 artifact 文件反推用户输入内容（通过 `user=N` 中的 N 推断字数）：

| 时间 (UTC+8) | user 长度 | 推测输入内容 | LLM 响应 |
|-------------|----------|-------------|---------|
| 02:56:27 | 22 | 约 7-8 中文字 | ✅ 正常叙事（突破失败，HP-10） |
| 02:57:12 | 9 | 约 3 中文字 | ✅ 正常叙事（突破到金丹） |
| 02:57:46 | 10 | 约 3-4 中文字 | ✅ 正常叙事（渡劫→九重天劫战斗） |
| 02:58:23 | 17 | 约 5-6 中文字 | ✅ 正常叙事（飞升成仙大结局） |
| 02:58:54 | 8 | 约 2-3 中文字 | ✅ 正常叙事（game_over=true） |
| 02:59:24 | 12 | 约 4 中文字 | ✅ 正常叙事（回到练气层突破失败） |

## 关键发现 9: LLM 叙事质量很高，但全部被 msgpack 吞掉

### LLM 输出样本（质量评估）

**正常叙事**（突破失败）:
> 云雾缭绕的青云山巅，寒风凛冽。你身着洗得发白的粗布道袍，站在悬崖边...强行催动灵气，结果不仅未能冲破瓶颈，反而因心神不宁导致气机逆冲...

**境界突破叙事**（金丹）:
> 你睁开双眼，原本浑浊的灵台瞬间变得清明如镜。一股磅礴而凝实的力量在丹田中缓缓流转，那是凝结成形的金丹...

**飞升大结局**:
> 苍穹之上，原本平静的云层骤然翻滚，化作墨色深渊。九道紫金色雷霆如巨龙般在天际游弋...光门在你面前缓缓开启...你深吸一口气，迈步走入其中...

### 状态评估

| 指标 | 状态 |
|------|------|
| LLM 连通性 | ✅ 每次都 200 OK |
| 叙事文风 | ✅ 修仙风格浓厚，描写生动 |
| state_delta 格式 | ✅ 正确的 JSON 结构 |
| Checkpoint 序列化 | ❌ 全部失败（msgpack） |
| 状态应用到 GameSession | ❌ 全部未执行（apply_delta 被跳过） |
| UI 显示干净叙事 | ❌ 显示原始 JSON + 错误信息 |

**结论**: 游戏引擎的核心 LLM 链路完全正常，唯一的致命瓶颈是 `turn_runner.py:88-89` 把 `stream_callback` 塞进 LangGraph state 导致 msgpack 序列化失败。

## 关键发现 10: LLM 自行推进了完整游戏线

从 6 个连续 artifact 可以看到 LLM（agnes-2.0-flash）在没有状态反馈的情况下自行推进了：

1. 练气 → 突破失败（HP-10）
2. 练气 → 金丹（realm="金丹", HP+50, MP+100）
3. 金丹 → 渡劫（realm="渡劫", 触发九重天劫战斗）
4. 渡劫 → 飞升（realm="飞升", finale=true, game_over=true）
5. 飞升后大结局（game_over=true）
6. 又回到练气（说明可能是新游戏或状态未更新）

**问题**: 由于 apply_delta 没有执行，GameSession 始终停留在 world_builder 创建的初始状态（练气一层）。LLM 收到的 `game_state_json` 每次都是同一个初始状态，所以它能自由发挥不受约束。

### 安全隐患

LLM 在 state_delta 中提交了 `realm="飞升"`，如果 apply_delta 执行了：
- `game_session.apply_delta({"character": {"realm": "飞升"}})` → 当前 `apply_delta` **没有 realm 白名单校验**，会直接接受
- 玩家一步就从练气跳到飞升

这证实了计划文档中 Phase 1.1（apply_delta 防御）的必要性。

## 关键发现 11: 战斗系统被 LLM 自行触发

Artifact `2026-06-12T18-57-46Z_3f48c986` 中 LLM 输出了完整的 combat 结构：

```json
"combat": {
  "phase": "player_turn",
  "enemy": {
    "name": "九重天劫",
    "hp": 10000,
    "enemy": {
      "name": "九重天劫",
      "hp": 10000,
      "hp_max": 10000,
      "techniques": [{"name": "灭世雷罚", "mp_cost": 0, "element": "雷"}]
    },
    "available_actions": ["technique", "item", "defend", "flee"],
    "narrative": "第一道天劫即将落下..."
  }
}
```

但战斗按钮（普攻/功法/丹药/防御/逃跑）无法触发，因为：
1. apply_delta 没执行 → `game_session.combat` 保持 None
2. `_handle_combat_start_or_update` 没被调用
3. CombatBar 始终隐藏

---

## 累计失败统计

| 时间段 | narrator 调用次数 | 成功 | 失败 | 失败原因 |
|--------|-----------------|------|------|---------|
| 02:41-02:49 (第一轮) | 8 | 0 | 8 | msgpack TypeError |
| 02:50-02:51 (第二轮) | 2 | 0 | 2 | msgpack TypeError |
| 02:56-02:59 (第三轮) | 6 | 0 | 6 | msgpack TypeError |
| **合计** | **16** | **0** | **16** | **100% 失败率** |

---

## 运行时状态快照

### 游戏会话（GameSession）
- 始终停留在 world_builder 初始化后的状态
- `char_name`: 不确定（world_builder 输出 "2" 作为用户输入）
- `realm`: 练气
- `realm_stage`: 1
- `hp/mp`: 100/50（从未变化）
- `game_over`: False（LLM 多次尝试设 True 但未生效）

### LLM 通信
- API Key: 有效（每次 200 OK）
- 模型: agnes-2.0-flash
- 响应时间: 2-4 秒
- 代理: 127.0.0.1:10809（VPN）
- Artifacts: 正常写入（16 个 output.md）

### Kivy UI
- 窗口: 正常运行，未崩溃
- 主题: 明亮白
- 字体: NotoSansSC 正常显示中文
- 叙事区: 被错误信息和原始 JSON 淹没
- 状态栏: 显示初始值，永不更新

---

# 第四轮监测记录（2026-06-13 03:00-03:01）

## 日志增长: 1320 → 1557 行（+237 行）

新增 3 次 narrator 调用，全部失败，同根因 msgpack TypeError。

| 时间 (UTC+8) | user 长度 | run_id (尾) | LLM 响应 |
|-------------|----------|------------|---------|
| 03:00:27 | 16 | 5dc2f4e4 | ✅ 叙事正常（修真之旅起点，凡铁长剑） |
| 03:00:55 | 3 | cdec3f01 | ✅ 叙事正常（角色死亡，game_over=true） |
| 03:01:29 | 8 | 0ed3c25f | ✅ 叙事正常（练气→筑基突破成功） |

## LLM 输出分析

### Artifact `5dc2f4e4` — 重置叙事
LLM 自行生成了完整的初始装备列表（凡铁长剑 attack+5, 粗布麻衣 defense+2），这是第 2 次 LLM 自行做 world_builder 的工作。说明用户可能点了"新游戏"按钮或输入了类似重置指令。

### Artifact `cdec3f01` — 角色死亡
用户仅输入 3 个字符（可能"去死"/"死"之类），LLM 生成了角色死亡叙事并设 `game_over: true, hp: 0`。LLM 对极端输入的响应合理且富有文学性。

### Artifact `0ed3c25f` — 筑基突破
LLM 自行将角色从练气提升到筑基，还附带了 `hp_max: "+200", mp_max: "+300"` 的增量。叙事质量高（"灵力彻底贯通全身...你的气息不再浮躁"）。

**新增观察**: `status_effects_add: ["灵力震荡"]` — LLM 尝试用 `xxx_add` 语法添加状态效果，这是 apply_delta 支持的格式。

## 累计失败统计（更新）

| 时间段 | narrator 调用次数 | 成功 | 失败 | 失败原因 |
|--------|-----------------|------|------|---------|
| 02:41-02:49 (第一轮) | 8 | 0 | 8 | msgpack TypeError |
| 02:50-02:51 (第二轮) | 2 | 0 | 2 | msgpack TypeError |
| 02:56-02:59 (第三轮) | 6 | 0 | 6 | msgpack TypeError |
| 03:00-03:01 (第四轮) | 3 | 0 | 3 | msgpack TypeError |
| **合计** | **19** | **0** | **19** | **100% 失败率** |

**无新错误类型**。持续监测中。

---

# 第五轮监测记录（2026-06-13 03:02-03:04）

## 日志增长: 1557 → 1825 行（+268 行）

新增 3 次 narrator 调用 + 1 次 world_builder 调用（新游戏） + 存档/读档操作。

## 新增操作时间线

| 时间 (UTC+8) | 操作 | 结果 |
|-------------|------|------|
| 03:02:33 | Narrator (user=1343) | ❌ msgpack TypeError |
| 03:03:05 | Narrator (user=4560) | ❌ msgpack TypeError |
| 03:03:xx | **存档 manual.json** | ✅ 成功 |
| 03:03:xx | **读档 manual.json** | ✅ 成功 |
| 03:03:xx | **存档 manual.json** (再存) | ✅ 成功 |
| 03:03:52 | **World Builder (user=5)** | ✅ 成功（2861 chars, 新角色 "无名"） |
| 03:04:09 | Narrator (user=4) | ❌ msgpack TypeError |

## 关键发现 12: 存档/读档正常工作，但无法恢复有意义的状态

日志确认：
```
Game saved to C:\Users\29176\AppData\Roaming\xianxia\saves\manual.json
Game loaded from C:\Users\29176\AppData\Roaming\xianxia\saves\manual.json
Game saved to C:\Users\29176\AppData\Roaming\xianxia\saves\manual.json
```

存读档功能本身正常，但由于 apply_delta 从未成功执行，保存的永远是初始状态（练气一层, HP 100/MP 50），读档后也没有任何变化。

## 关键发现 13: user 长度异常增长 — 叙事区累积文本作为输入

| 调用 | user 长度 | 说明 |
|------|----------|------|
| 03:02:33 | **1343** | 异常长（约 400+ 中文字） |
| 03:03:05 | **4560** | 极端长（约 1500+ 中文字） |

正常用户输入应在 2-50 字符。1343 和 4560 远超正常范围。

**推测原因**: 用户可能在输入框中粘贴了大量文本，或者叙事区的累积内容被误传为 user_input。需要确认 `_on_user_action` 是否正确只取输入框文本（`self.text_input.text.strip()`）。

另一种可能：用户输入了很长的修仙描述文本，或者输入框的文本在某种错误下累积了之前的流式输出。

## 关键发现 14: World Builder 成功但 narrator 紧接着就失败

用户成功点击"新游戏"→ world_builder 创建了新角色 "无名"（练气一层, HP 100/MP 50），但随后第一次 narrator 调用（user=4, 可能是 "你好" 或类似）立即失败。

**确认**: world_builder 不使用流式（用 `call_llm` 非 `call_llm_stream`），所以 `stream_callback` 不会进入 state → msgpack 不报错 → world_builder 100% 成功。只有 narrator 用流式才会触发 msgpack 错误。

### 最新 narrator 输出质量

`dd0a1da1`（新游戏后第一次叙事）:
> 山门外的青石广场上，寒风卷起几片枯叶。一名身穿粗布麻衣的少年...

LLM 还自行生成了任务系统：
```json
"active_quests_add": [{
  "id": "q001",
  "title": "初入仙途",
  "description": "前往外门执事堂报道，领取第一笔修炼资源。",
  "rewards": {"experience": 50, "items": [{"name": "下品灵石", "quantity": 5}]}
}]
```

这超出了 apply_delta 当前支持的字段（`active_quests_add` 不在 reducer 中），即使 msgpack 修复了，这部分也会被静默忽略。

## 累计失败统计（更新）

| 时间段 | narrator 调用次数 | 成功 | 失败 | 失败原因 |
|--------|-----------------|------|------|---------|
| 02:41-02:49 (第一轮) | 8 | 0 | 8 | msgpack TypeError |
| 02:50-02:51 (第二轮) | 2 | 0 | 2 | msgpack TypeError |
| 02:56-02:59 (第三轮) | 6 | 0 | 6 | msgpack TypeError |
| 03:00-03:01 (第四轮) | 3 | 0 | 3 | msgpack TypeError |
| 03:02-03:04 (第五轮) | 3 | 0 | 3 | msgpack TypeError |
| **合计** | **22** | **0** | **22** | **100% 失败率** |

**附加**: world_builder 调用 2 次，全部成功（非流式，不受 msgpack 影响）。

---

# 第六轮监测记录（2026-06-13 03:04）

## 日志增长: 1825 → 1982 行（+157 行）

新增 2 次 narrator 调用，同根因 msgpack TypeError。无新错误类型。

| 时间 (UTC+8) | user 长度 | 结果 |
|-------------|----------|------|
| 03:04:30 | 4 | ❌ msgpack TypeError |
| 03:04:47 | 4 | ❌ msgpack TypeError |

两次 user=4（约 1-2 中文字），可能是短指令如"走"/"看"/"修炼"等。

## 累计失败统计（更新）

| 合计 | **24** | **0** | **24** | **100% 失败率** |

用户仍在持续测试。模式无变化，msgpack 错误持续阻塞所有叙事功能。

---

# 用户需求记录 #2（2026-06-13 03:05）

用户在持续测试后提出 5 个新需求/问题：

## 需求 1: 存档/读档增加选择项

### 用户原文
> 存档、读档需要增加一个选择项，可以进行不同的游戏

### 当前状态

**GameScreen 快捷按钮**（`game_screen.py:209-212`）:
- 存档: `adapter.save("manual")` — 硬编码 slot 名 `"manual"`，只有一个档位
- 读档: `adapter.load("manual")` — 同样只读 `"manual"`，无选择界面

**SaveScreen**（`screens/save_screen.py`）已有多档位：
- 自动存档（autosave，只读）
- 5 个手动档位（slot_1 到 slot_5，可存/读/删）
- 但用户无法从 GameScreen 直接到达 SaveScreen（没有导航按钮）

### 问题分析

1. **GameScreen 底部按钮 "存档"/"读档"** 直接写入/读取 `"manual"` 单一档位，无法选择
2. **SaveScreen 已实现多档位管理**，但无入口可达（当前导航缺少 "存档管理" 按钮）
3. 读档后 **narrative_view 不刷新**（只更新 status_bar 和 realm_card）

### 建议修复方向

- **方案 A**: GameScreen 的 "存档"/"读档" 按钮改为跳转到 SaveScreen
- **方案 B**: 存档保留快捷行为（自动覆盖 manual），读档改为弹出档位选择弹窗（读取 list_saves()）
- 存档选择 UI 可复用 SaveScreen 已有的逻辑

### 相关文件

| 文件 | 行号 | 现状 |
|------|------|------|
| `mobile/screens/game_screen.py` | L209-212 | 硬编码 save/load "manual" |
| `mobile/screens/save_screen.py` | 全文件 | 已有多档位管理 UI |
| `mobile/widgets/action_bar.py` | L26-35 | BUTTONS 列表无 "存档管理" |
| `src/agens_novel/repl/save_manager.py` | `list_saves()`, `get_manual_save_slots()` | 后端已支持 |
| `src/agens_novel/engine/game_engine.py` | L500-525 | save/load 后端完整 |

---

## 问题 2: 回合数不更新

### 用户原文
> 回合数不更新

### 根因分析

**直接原因**: `game_engine.py:192` 的 `self.game_session.turn_count += 1` 在 `handle_action()` 中执行，但由于 msgpack 错误（问题 #2），`run_turn_sync` 抛异常后被 `except` 捕获（L202-206），然后 **执行回退** `turn_count -= 1`（L205）。

所以回合数永远不会增加。

**次要原因**: 即使 msgpack 修复后，`game_engine.py:192` 的 `turn_count += 1` 是在 narrator 调用**之前**执行的，而 L205 的 `-1` 是在**失败时**回退。如果 narrator 成功，回合数应该正常更新。

### StatusBar 显示

`status_bar.py:116`: `self.lbl_turn.text = f"回合{session.turn_count}"` — 显示逻辑正确，数据源有问题。

### 建议修复方向

修复 msgpack 错误后此问题自动解决。

---

## 问题 3: 游戏回不到主界面

### 用户原文
> 游戏回不到主界面

### 当前状态

**没有主界面**。App 启动直接进入 GameScreen 或 TutorialScreen（`main.py:108-124`）：

```python
sm.add_widget(GameScreen(name="game"))
sm.add_widget(SettingsScreen(name="settings"))
sm.add_widget(SaveScreen(name="save"))
sm.add_widget(CombatScreen(name="combat"))
sm.add_widget(TutorialScreen(name="tutorial"))
```

- 首次使用（无 API key）→ TutorialScreen
- 正常启动 → GameScreen

**GameScreen 没有导航回任何 "主菜单" 的能力**。用户从 GameScreen 可以：
- 跳转 SettingsScreen（Settings 按钮？需确认入口）
- 跳转 SaveScreen（无入口）
- 跳转 CombatScreen（战斗时自动切换）

但没有任何 "回到主界面" 或 "退出游戏" 的功能。

### 建议修复方向

新建 **HomeScreen / MainMenuScreen**：
- 游戏标题 + Logo 图片
- "继续游戏"（读取 autosave）
- "新游戏"（进入 GameScreen → _show_new_game_dialog）
- "存档管理"（跳转 SaveScreen）
- "设置"（跳转 SettingsScreen）
- "退出"（关闭 app）

在 `main.py` 中注册为第一个 Screen，启动时显示。

---

## 需求 4: 主界面增加设计感图片

### 用户原文
> 主界面增加一个具有设计感的图片,设计不出来，可以告知我提示词

### 设计建议

主界面需要一个 **修仙/仙侠风格的主视觉图**，建议内容：

**图片提示词（可用于 Midjourney / Stable Diffusion / DALL-E）**：

> **英文提示词（推荐）**:
> Chinese xianxia cultivation fantasy art, a lone cultivator in flowing white robes standing on a misty mountain peak, surrounded by swirling spiritual energy clouds in ethereal blue and green tones, ancient Chinese temple pagoda in the background, golden sunlight breaking through clouds, ink wash painting style combined with modern digital art, serene and majestic atmosphere, no text, aspect ratio 16:9

> **中文描述**:
> 仙侠修真风格主视觉：一位身穿白色道袍的独行修士立于云雾缭绕的山巅，周围环绕着蓝绿色灵气漩涡，远处有古风亭台楼阁，金色阳光穿破云层，水墨画与现代数字艺术结合风格，宁静庄严氛围，无文字

**技术实现方案**：
- 图片放在 `mobile/assets/images/splash.png`（或 `.jpg`）
- `buildozer.spec` 的 `source.include_exts` 需要加 `png,jpg`
- HomeScreen 用 Kivy `Image` widget 显示，`allow_stretch=True, keep_ratio=True`
- 尺寸建议: 1920×1080 或 1080×1920（竖屏），文件大小控制在 500KB 以内（APK 体积）

---

## 需求 5: 计划加入 BGM

### 用户原文
> 计划加入bgm，可以规划一下

### BGM 架构规划

#### 技术选型

| 方案 | Kivy 支持 | 复杂度 | 说明 |
|------|----------|--------|------|
| `kivy.core.audio.SoundLoader` | ✅ 内置 | 低 | 支持 wav/ogg/mp3，跨平台 |
| `kivy.lib.gstplayer` | ✅ 需 GStreamer | 中 | 更强但依赖重 |
| `pygame.mixer` | ❌ 与 Kivy 冲突 | 高 | 不推荐 |

**推荐**: `SoundLoader`，零额外依赖，Buildozer 自动打包。

#### 音轨设计

| 场景 | 文件名 | 风格 | 时长建议 |
|------|--------|------|---------|
| 主界面 | `bgm_menu.ogg` | 宁静古风，笛/筝 | 2-3 min loop |
| 日常探索 | `bgm_explore.ogg` | 轻快仙侠，琴/箫 | 3-4 min loop |
| 战斗 | `bgm_combat.ogg` | 紧张激昂，鼓/铜 | 2-3 min loop |
| 突破/飞升 | `bgm_breakthrough.ogg` | 史诗磅礴，管弦 | 2 min 一次性 |
| 游戏结束 | `bgm_gameover.ogg` | 凄美哀婉，二胡 | 1-2 min 一次性 |

格式建议: **OGG Vorbis**（体积小、质量好、Kivy 原生支持）。每首控制在 1-2MB。

#### 音效设计（可选）

| 事件 | 文件名 | 时长 |
|------|--------|------|
| 按钮点击 | `sfx_click.wav` | 0.1s |
| 获得物品 | `sfx_item.wav` | 0.5s |
| 受伤/失血 | `sfx_hurt.wav` | 0.3s |
| 境界突破 | `sfx_levelup.wav` | 1.0s |
| 游戏结束 | `sfx_death.wav` | 0.8s |

#### 代码架构

```python
# mobile/audio_manager.py（新建）

from kivy.core.audio import SoundLoader
from kivy.clock import Clock

class AudioManager:
    """Singleton audio manager for BGM and SFX."""

    _instance = None

    def __init__(self):
        self._bgm = None
        self._bgm_volume = 0.5
        self._sfx_volume = 0.7
        self._enabled = True

    @classmethod
    def instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def play_bgm(self, name: str, loop: bool = True):
        """Play a background music track."""
        self.stop_bgm()
        path = f"assets/audio/bgm/{name}.ogg"
        self._bgm = SoundLoader.load(path)
        if self._bgm:
            self._bgm.volume = self._bgm_volume
            self._bgm.loop = loop
            self._bgm.play()

    def stop_bgm(self):
        if self._bgm:
            self._bgm.stop()
            self._bgm = None

    def play_sfx(self, name: str):
        """Play a one-shot sound effect."""
        if not self._enabled:
            return
        path = f"assets/audio/sfx/{name}.wav"
        snd = SoundLoader.load(path)
        if snd:
            snd.volume = self._sfx_volume
            snd.play()

    def set_bgm_volume(self, v: float): ...
    def set_sfx_volume(self, v: float): ...
    def toggle(self): ...
```

#### 集成点

| Screen/Widget | 触发时机 | 调用 |
|--------------|---------|------|
| HomeScreen | `on_enter` | `play_bgm("bgm_menu")` |
| GameScreen | `on_enter` | `play_bgm("bgm_explore")` |
| GameScreen | `_on_combat_update(combat)` | combat != None → `play_bgm("bgm_combat")` |
| GameScreen | `_on_combat_update(None)` | `play_bgm("bgm_explore")` |
| GameScreen | `_on_breakthrough` | `play_sfx("sfx_levelup")` |
| GameScreen | `_on_game_over` | `play_bgm("bgm_gameover", loop=False)` |
| SettingsScreen | BGM 音量滑块 | `set_bgm_volume(value)` |
| SettingsScreen | SFX 开关 | `toggle()` |

#### 文件结构

```
mobile/assets/audio/
├── bgm/
│   ├── bgm_menu.ogg
│   ├── bgm_explore.ogg
│   ├── bgm_combat.ogg
│   ├── bgm_breakthrough.ogg
│   └── bgm_gameover.ogg
└── sfx/
    ├── sfx_click.wav
    ├── sfx_item.wav
    ├── sfx_hurt.wav
    ├── sfx_levelup.wav
    └── sfx_death.wav
```

#### buildozer.spec 修改

```
source.include_exts = py,png,jpg,kv,atlas,json,yaml,md,txt,otf,ttf,ogg,wav,mp3
```

#### 依赖

- 桌面: Kivy 2.3.1 自带 `SoundLoader`（依赖 SDL2_mixer）
- Android: Buildozer 自动包含 `sdl2_mixer`，无需额外配置
- 总 APK 增量: ~8-10MB（5 BGM + 5 SFX）

---

## 需求优先级总结

| 优先级 | 需求 | 依赖 | 预估工作量 |
|--------|------|------|-----------|
| **前置** | 修复 msgpack 错误 | 一切正常功能的前提 | 10 行 |
| **前置** | 修复 JSON 泄露到 UI | 正常游戏体验的前提 | 30 行 |
| P0 | 新建 HomeScreen（需求 3+4） | 无 | 60 行 + 图片资源 |
| P0 | 存档/读档选择（需求 1） | 无 | 30 行 |
| P1 | BGM 系统（需求 5） | AudioManager 新建 + 音频资源 | 80 行 + 5-10 音频文件 |
| P1 | 回合数更新（需求 2） | 随 msgpack 修复自动解决 | 0 行（自动） |
| P1 | 输入框命令识别（需求 #8） | 自由输入驱动一切 | 40 行 |

