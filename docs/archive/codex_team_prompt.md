# 已归档

本文档为历史 Codex 团队提示词草稿，仅用于追溯旧方案，不作为当前实现依据。当前实现请以仓库根目录 `AGENTS.md`、`docs/prototypes/` 和最新交付报告为准。

# 文字修仙模拟器 — Codex 智能体软件开发团队

## 项目概述

项目名：agens-novel（文字修仙模拟器）
仓库根目录：`D:\chat\agens`
目标：依据 `docs/prototypes/index.html` 高保真原型图，对 Kivy 移动端代码进行全面改造，使最终 APK 的界面、交互、视觉与原型图一致。
测试基线：557 passed, 0 failed（改动后必须保持 0 failed）
技术栈：Python 3.12 / Kivy 2.3 / LangGraph / httpx / Rich / Typer / Buildozer

---

## 团队角色与职责

### 角色 1：产品经理（Product Manager）

**职责**：需求拆解、优先级排序、验收标准定义、原型-代码对齐审查

**输入**：
- 原型图 HTML+CSS：`docs/prototypes/index.html` + `docs/prototypes/prototype.css`
- 当前代码：`mobile/` + `src/agens_novel/`
- 差距分析报告（见下方"差距清单"章节）

**输出**：
1. 按 Phase 拆分的用户故事列表（每个 Phase 可独立测试）
2. 每个用户故事的验收条件（Given-When-Then 格式）
3. 原型与代码的对齐核查表（确认每张原型图的每个元素都有对应实现）
4. 优先级调整建议（如发现原型设计不合理之处，提出替代方案）

**工作流程**：
1. 阅读 `docs/prototypes/index.html` 全部 10 张原型图
2. 阅读 `docs/prototypes/prototype.css` 全部视觉规范
3. 对比 `mobile/` 下所有 screen/widget 代码
4. 输出按 Phase 排序的用户故事 + 验收条件
5. 在开发过程中，审核每个 PR/提交是否与原型意图一致

### 角色 2：高级开发工程师（Senior Developer）

**职责**：架构设计、核心代码实现、代码质量把控、技术决策

**约束（必须遵守）**：
- `src/agens_novel/llm/` 目录零修改（client.py / sse.py / retry.py 是通用组件）
- `stream_callback` 不进入 LangGraph state，必须通过 `repl/_stream_context.py` thread-local 传递
- `GameEngine` 是唯一游戏逻辑入口，REPL 和 Kivy 都委托 GameEngine
- API key 永远不写入磁盘，只从环境变量或内置 base64 读取
- 所有新增字段必须同步更新 `GameSession.to_save_dict()` 和 `from_save_dict()` 保持存读档兼容
- 所有 UI 改动必须同时适配 Kivy 2.3 的 canvas 指令系统（不能用 kv 语言外部文件）
- 保持 557+ 测试全绿，新增功能必须有对应测试

**输出**：
1. 架构设计文档（改动范围、新增模块、数据流变更）
2. 代码实现（按 Phase 逐步提交）
3. 每个 Phase 的自测报告
4. 代码质量自审清单

**关键文件清单（改动前必须通读）**：

| 文件 | 当前职责 | 改动范围 |
|------|---------|---------|
| `mobile/theme.py` | 三色主题（WHITE/BLACK/GREEN） | 改为水墨风格三色（宣纸白/墨绿/暗夜），重写所有 ThemePalette |
| `mobile/screens/home_screen.py` | 主页 5 按钮 | 重构：加背景图、BGM 喇叭、读档/教程/设置改为内嵌弹窗 |
| `mobile/screens/game_screen.py` | 游戏主界面 | 重构：新 status-card 布局、选项渲染、自由度模式切换、工具栏重排 |
| `mobile/screens/settings_screen.py` | 设置独立页面 | 改为内嵌弹窗形态 + 加游玩模式/音频控制 |
| `mobile/screens/tutorial_screen.py` | 教程独立页面 | 改为内嵌弹窗形态 + 更新教程内容 |
| `mobile/screens/save_screen.py` | 存档独立页面 | 改为主页内嵌读档弹窗 |
| `mobile/widgets/status_bar.py` | 状态栏（HP/MP/EXP 条） | 改为 stat-grid 6 格布局（姓名/年龄/境界/灵根/天赋/家世/气运） |
| `mobile/widgets/action_bar.py` | 工具按钮行 | 重排为原型 10 按钮 + 自由度感知的输入框 |
| `mobile/widgets/narrative_view.py` | 叙事显示 | 加选项渲染区域（choices） |
| `mobile/main.py` | App 入口 | 注册新 Screen、AudioManager 初始化 |
| `src/agens_novel/repl/game_session.py` | 游戏状态 dataclass | 新增字段：age/talent/background/luck/attributes/game_mode |
| `src/agens_novel/game/constants.py` | 游戏常量 | 新增天赋/家世/难度/属性常量 |
| `mobile/widgets/loading_overlay.py` | 加载覆盖层 | 水墨风格适配 |
| `mobile/widgets/combat_bar.py` | 战斗栏 | 水墨风格适配 |

**新建文件**：

| 文件 | 职责 |
|------|------|
| `mobile/screens/character_create_screen.py` | 角色创建独立页面（含 2917 彩蛋） |
| `mobile/screens/death_screen.py` | 全屏死亡界面 |
| `mobile/audio_manager.py` | 音频管理单例（BGM + SFX） |
| `mobile/assets/audio/bgm/bgm_menu.ogg` | 主页 BGM（需用户提供素材） |
| `mobile/assets/audio/bgm/bgm_explore.ogg` | 探索 BGM |
| `mobile/assets/audio/bgm/bgm_combat.ogg` | 战斗 BGM |
| `mobile/assets/images/ink_home_bg.png` | 水墨主页背景图（可从原型 assets 复制） |

### 角色 3：测试工程师（Test Engineer）

**职责**：测试策略制定、测试用例编写、自动化测试执行、回归验证

**约束**：
- 所有测试必须通过 `python -m pytest -q` 运行
- 不能引入真 LLM 调用（mock 所有 LLM 交互）
- Kivy 相关测试使用 mock（`sys.modules` 注入），不依赖真 Kivy 环境
- 破坏性测试和模糊测试是必须项

**输出**：
1. 每个 Phase 的测试计划（覆盖：功能/边界/异常/视觉回归）
2. 自动化测试代码
3. 测试执行报告（通过/失败/跳过 + 覆盖率）
4. 回归测试确认（557 旧测试仍全绿）

**测试分层**：

| 层级 | 目录 | 内容 |
|------|------|------|
| 单元测试 | `tests/unit/` | GameSession 新字段、apply_delta 新守卫、GameMode 枚举、AudioManager 逻辑、角色创建验证、2917 彩蛋 |
| UI 测试 | `tests/unit/test_ui_fixes.py` 扩展 | 弹窗行为、按钮布局、自由度模式切换、选项渲染 |
| 破坏性测试 | `tests/unit/test_e2e_destructive.py` 扩展 | 新字段的 fuzz 输入、GameMode 切换时的异常、存读档边界 |
| 视觉回归 | `tests/unit/test_visual_regression.py` 新建 | 验证 theme.py 的颜色值与原型 CSS `prototype.css` 的色值对齐 |

### 角色 4：交付总监（Delivery Director）

**职责**：全流程质量把控、Phase 门禁审核、架构平衡审查、最终交付验收

**输出**：
1. 每个 Phase 的门禁检查清单
2. 代码权重分析报告（各模块代码行数占比，识别架构失衡）
3. 冗余代码扫描报告
4. 最终交付评审意见

**门禁标准**（每个 Phase 必须全部通过才能进入下一 Phase）：
- [ ] 所有新增/修改测试通过（0 failed）
- [ ] 557 旧测试仍全绿（回归零退化）
- [ ] 代码质量：无未使用 import、无死代码、无重复常量
- [ ] 架构平衡：无单一文件超过 500 行（widget/screen 类）
- [ ] 原型对齐：产品经理确认该 Phase 涵盖的原型元素全部实现
- [ ] 无安全退化：API key 不入 state、无硬编码凭据、apply_delta 防御完整

---

## 差距清单（差距分析的完整输出）

以下为原型 vs 代码的逐项差距，供各角色参考：

### 缺失项（16 项）

| # | 差距 | 涉及文件 | 影响 Phase |
|---|------|---------|-----------|
| 1 | 主页水墨背景图 | `home_screen.py` + `mobile/assets/images/` | Phase 1 |
| 2 | 右上角 BGM 喇叭开关 | `home_screen.py` + `audio_manager.py`(新) | Phase 1 |
| 3 | 读档→主页内弹窗（非跳转） | `home_screen.py` + `save_screen.py` 重构 | Phase 2 |
| 4 | 教程→主页内弹窗（非跳转） | `home_screen.py` + `tutorial_screen.py` 重构 | Phase 2 |
| 5 | 设置→主页内弹窗（非跳转） | `home_screen.py` + `settings_screen.py` 重构 | Phase 2 |
| 6 | 游玩模式三档（高/中/低自由度） | `game_session.py` + `constants.py` + `game_screen.py` | Phase 3 |
| 7 | 中自由度选项渲染 | `game_screen.py` + `narrative_view.py` | Phase 3 |
| 8 | 低自由度强制选项模式 | `game_screen.py` + `action_bar.py` | Phase 3 |
| 9 | 顶部信息栏新字段（年龄/天赋/家世/气运） | `status_bar.py` + `game_session.py` | Phase 4 |
| 10 | 角色创建独立页面 | `character_create_screen.py`(新) | Phase 5 |
| 11 | 6 属性条（根骨/悟性/气运/心性/体魄/神识） | `character_create_screen.py`(新) + `game_session.py` | Phase 5 |
| 12 | 随机按钮 + 鼓励提示 | `character_create_screen.py`(新) | Phase 5 |
| 13 | 2917 彩蛋 | `character_create_screen.py`(新) | Phase 5 |
| 14 | 全屏死亡界面（道途已断 + 三按钮） | `death_screen.py`(新) | Phase 6 |
| 15 | 水墨视觉主题（宣纸白/墨绿/暗夜） | `theme.py` 全量重写 | Phase 1 |
| 16 | BGM/SFX 音频控制 UI | `settings_screen.py`（弹窗内） | Phase 2 |

### 部分实现项（5 项）

| # | 差距 | 现状 | 需要 |
|---|------|------|------|
| 17 | 主页 5 按钮 | 有 5 按钮但内容不同（继续游戏/存档管理 vs 读档/教程） | 替换按钮列表 |
| 18 | 工具栏 10 按钮 | 有 8 个但缺"重开"和"设置"按钮 | 重排+新增 |
| 19 | 顶部状态栏 | 有 HP/MP/EXP 但原型无这些 | 重新设计为 stat-grid |
| 20 | 叙事区选项 | 后端有 choices 字段但始终为空 + 无前端渲染 | 加解析+渲染 |
| 21 | 设置主题色 | 有 3 套但风格与水墨不一致 | 改色值 |

---

## Phase 实施计划

### Phase 1：视觉基础设施（水墨主题 + 背景图 + 音频框架）

**目标**：建立水墨视觉体系和音频基础设施，不改变交互逻辑。

**改动范围**：
1. `mobile/theme.py` — 三套 ThemePalette 重写为水墨色系：
   - 宣纸白：bg=#f7f3ea, surface=#fff8f0, primary=#52746d, accent=#a77d38
   - 墨绿：bg=#dfe9df, surface=#c8d8c8, primary=#3a5c42, accent=#8a6d2b
   - 暗夜：bg=#202a27, surface=#2d3b36, primary=#7aad9e, accent=#d4a54a
   - 所有色值必须与 `prototype.css` 的 `:root` 变量对齐
2. `mobile/assets/images/ink_home_bg.png` — 从 `docs/prototypes/assets/ink-home-bg.png` 复制
3. `home_screen.py` — 加水墨背景图加载 + 右上角喇叭按钮
4. `mobile/audio_manager.py`(新) — AudioManager 单例骨架（play_bgm/stop_bgm/play_sfx/toggle）
5. 所有 widget/screen 的 canvas 颜色跟随新主题

**验收条件**：
- [ ] `python -m pytest -q` 全绿
- [ ] 桌面 `python mobile/main.py` 启动后主页有水墨背景
- [ ] 喇叭按钮可见且可点击（可暂无音频文件）
- [ ] 三套主题切换后颜色与原型 CSS 一致（视觉回归测试）

### Phase 2：主页弹窗化（读档/教程/设置改为内嵌弹窗）

**目标**：主页的读档、教程、设置不再跳转独立页面，改为主页内宣纸质感弹窗。

**改动范围**：
1. `home_screen.py` — 新增 3 个弹窗方法：
   - `_show_load_popup()` — 宣纸弹窗，含自动存档 + 5 手动档位 + 读取/删除操作
   - `_show_tutorial_popup()` — 宣纸弹窗，含 3-5 页教程 + 翻页
   - `_show_settings_popup()` — 宣纸弹窗，含模型配置 + 主题 + 游玩模式 + 音频控制
2. 按钮文字替换：继续游戏→删除，存档管理→改为"读档"，新增"教程"
3. 设置弹窗内新增：游玩模式 segmented 控件、音频控制 segmented 控件
4. 宣纸弹窗样式：`themed_popup` 改造为支持宣纸纹理背景

**验收条件**：
- [ ] 主页点击"读档"→ 弹窗覆盖在主页上，不跳转
- [ ] 主页点击"教程"→ 弹窗覆盖在主页上，可翻页
- [ ] 主页点击"设置"→ 弹窗覆盖在主页上，含游玩模式和音频控件
- [ ] 弹窗有宣纸质感（半透明背景 + 模糊遮罩）

### Phase 3：自由度模式系统

**目标**：实现高/中/低三种游玩模式，影响游戏界面的选项显示和输入框行为。

**改动范围**：
1. `src/agens_novel/game/constants.py` — 新增 `GameMode` 枚举（HIGH/MID/LOW）
2. `src/agens_novel/repl/game_session.py` — 新增 `game_mode` 字段，默认 `"high"`
3. `game_screen.py` — 依据 `game_session.game_mode` 切换 UI：
   - HIGH：纯叙事 + 输入框（当前默认行为）
   - MID：叙事 + 2-4 选项按钮 + 输入框（"也可以自由输入行动"）
   - LOW：叙事 + 选项按钮，输入框弱化（"请选择上方行动"），发送按钮文字改为"定"
4. `narrative_view.py` — 新增 `render_choices()` 方法，渲染选项按钮
5. `action_bar.py` — 输入框 hint_text 和发送按钮文字随模式变化

**验收条件**：
- [ ] 切换到中自由度 → 叙事下方出现选项按钮 + 输入框可用
- [ ] 切换到低自由度 → 选项按钮存在，输入框弱化
- [ ] 切换到高自由度 → 无选项，纯输入
- [ ] 游玩模式持久化到 settings.json，重启后保留

### Phase 4：游戏界面顶部信息栏重构

**目标**：状态栏从 HP/MP/EXP 条改为原型设计的 stat-grid 7 格布局。

**改动范围**：
1. `src/agens_novel/repl/game_session.py` — 新增字段：
   - `age: int = 16`
   - `talent: str = ""`（天赋）
   - `family_background: str = ""`（家世）
   - `luck: str = "中上"`（气运，文字描述）
2. `src/agens_novel/game/constants.py` — 新增常量：
   - `TALENT_OPTIONS = [...]`
   - `FAMILY_BACKGROUNDS = [...]`
   - `LUCK_LEVELS = [...]`
3. `status_bar.py` — 重写为 stat-grid 布局（2 行 × 3 列 + 姓名行 + 回合数右上角）
4. HP/MP/EXP 条移除或降级（原型中没有，但可保留在详情弹窗中）
5. `to_save_dict()` / `from_save_dict()` 同步更新

**验收条件**：
- [ ] 游戏界面顶部显示：姓名(左) + 回合数(右上)
- [ ] stat-grid 6 格：年龄/境界/灵根/天赋/家世/气运
- [ ] 存读档兼容：旧存档加载时新字段用默认值

### Phase 5：角色创建独立页面

**目标**：新建独立角色创建页面，替代当前单行 TextInput 弹窗。

**改动范围**：
1. `mobile/screens/character_create_screen.py`(新) — 完整角色创建页面：
   - 顶部"返回"按钮 + "创建角色"标题
   - 游戏名称输入框
   - 角色名输入框
   - 天赋 Spinner（下拉选择）
   - 灵根 Spinner（8 灵根）
   - 家世 Spinner
   - 难度 Spinner（简单/普通/困难）
   - 6 属性条（根骨/悟性/气运/心性/体魄/神识）— 每条带进度条 + 数值
   - "随机"按钮 — 随机分配属性值
   - 鼓励文案："随机可能获得更好的初始面板"
   - "开始"按钮
2. 2917 彩蛋逻辑：
   - 游戏名称输入 "2917" 时，自动触发：
     - 角色名 = "阿清"
     - 所有属性 = 99/100
     - 家世 = "隐世仙族"
     - 天赋 = "天命道胎"
     - 灵根 = "混沌天灵根"
     - 显示"开局命格"面板（属性全满/家世/天赋/灵根 四格）
     - 开场叙事（"云海倒悬，九峰钟声同时响起..."）
     - "重选"/"入世"两按钮
3. `game_session.py` — 新增属性字段：`attributes: dict`（含 6 个子属性数值）
4. `game_screen.py` — "新游戏"按钮跳转到 `character_create` screen
5. `main.py` — 注册 CharacterCreateScreen

**验收条件**：
- [ ] 点击"新游戏"→ 跳转到独立角色创建页面
- [ ] 所有表单字段可交互（Spinner 可选、属性条有数值）
- [ ] 点击"随机"→ 属性值随机变化
- [ ] 输入游戏名称 "2917" → 自动填满顶级属性 + 显示"开局命格"面板
- [ ] 点击"入世"→ 跳转到游戏界面，角色信息正确

### Phase 6：死亡界面 + 最终整合

**目标**：全屏死亡界面替换弹窗，完成所有原型的收尾工作。

**改动范围**：
1. `mobile/screens/death_screen.py`(新) — 全屏死亡界面：
   - "道途已断"标题（红色）
   - 诗意死亡文案
   - 三按钮：重新开始 / 读取存档 / 返回主页
2. `game_screen.py` — `_on_game_over()` 改为跳转到 death_screen
3. `main.py` — 注册 DeathScreen
4. 工具栏新增"重开"和"设置"按钮
5. 全局视觉审查：确保所有 screen/widget 使用水墨风格

**验收条件**：
- [ ] 角色死亡 → 全屏死亡界面（非弹窗）
- [ ] 三按钮均可点击且功能正确
- [ ] 工具栏包含 10 个按钮（原型指定的全部）
- [ ] 全部 10 张原型图的每个元素都有对应代码实现

---

## 代码质量审核标准

交付总监在每个 Phase 门禁审核时检查：

### 1. 代码质量
- 无未使用的 import（`pyflakes` 级别检查）
- 无死代码（未被调用的函数、未引用的变量）
- 无重复常量（境界/灵根/天赋等只定义一次，其他地方 import）
- 函数单一职责（单函数不超过 40 行）
- 类型注解完整（公开方法有参数和返回类型）
- docstring 与实现一致（无过时描述）

### 2. 冗余代码
- 同一逻辑不出现 2 次以上（如颜色值、常量定义）
- 废弃的 Screen 如不再独立使用（SaveScreen/TutorialScreen 改为弹窗后），评估是否删除
- 无被注释掉的代码块（删掉或提取）

### 3. 架构平衡
- 各 screen 文件不超过 500 行（超出则拆分子组件到 widgets/）
- 各 widget 文件不超过 300 行
- `game_session.py` 字段数不超过 40 个（dataclass 太胖则提取嵌套结构）
- `game_engine.py` 方法数不超过 25 个（超出则提取到子模块）
- 每个模块有单一职责：screen 只管布局，widget 只管 UI 组件，service 只管适配

### 4. 模块代码权重分析
每个 Phase 完成后，统计并报告：
```
mobile/screens/    — 总行数，各文件占比
mobile/widgets/    — 总行数，各文件占比
mobile/service/    — 总行数
src/agens_novel/   — 总行数，各子模块占比
tests/             — 总行数
```
如果任一模块占比超过总量的 40%，标记为"架构失衡"并提出拆分建议。

---

## 工作流程

```
Phase 1 (视觉基础)
  ├─ 产品经理：输出 Phase 1 用户故事 + 验收条件
  ├─ 高级开发：实现水墨主题 + 背景图 + AudioManager 骨架
  ├─ 测试工程师：编写视觉回归测试 + AudioManager 单元测试
  └─ 交付总监：门禁审核 → 通过后进入 Phase 2

Phase 2 (主页弹窗化)
  ├─ 产品经理：输出 Phase 2 用户故事 + 验收条件
  ├─ 高级开发：重构主页为弹窗架构
  ├─ 测试工程师：编写弹窗行为测试
  └─ 交付总监：门禁审核 → 通过后进入 Phase 3

Phase 3 (自由度模式)
  ├─ 产品经理：输出 Phase 3 用户故事 + 验收条件
  ├─ 高级开发：实现 GameMode 系统 + 选项渲染
  ├─ 测试工程师：编写模式切换测试 + 选项交互测试
  └─ 交付总监：门禁审核 → 通过后进入 Phase 4

Phase 4 (信息栏重构)
  ├─ 产品经理：输出 Phase 4 用户故事 + 验收条件
  ├─ 高级开发：新增 GameSession 字段 + 重写 StatusBar
  ├─ 测试工程师：编写新字段测试 + 存读档兼容性测试
  └─ 交付总监：门禁审核 → 通过后进入 Phase 5

Phase 5 (角色创建)
  ├─ 产品经理：输出 Phase 5 用户故事 + 验收条件
  ├─ 高级开发：新建 CharacterCreateScreen + 2917 彩蛋
  ├─ 测试工程师：编写创建流程测试 + 彩蛋触发测试
  └─ 交付总监：门禁审核 → 通过后进入 Phase 6

Phase 6 (死亡界面 + 收尾)
  ├─ 产品经理：输出 Phase 6 用户故事 + 验收条件
  ├─ 高级开发：新建 DeathScreen + 最终整合
  ├─ 测试工程师：全量回归测试 + 破坏性测试
  └─ 交付总监：最终交付评审
```

---

## 原型参考文件（只读）

| 文件 | 用途 |
|------|------|
| `docs/prototypes/index.html` | 10 张原型图的 HTML 定义，所有视觉和交互的基准 |
| `docs/prototypes/prototype.css` | 原型的完整 CSS 样式，所有颜色/尺寸/间距的基准 |
| `docs/prototypes/assets/ink-home-bg.png` | 水墨主页背景图 |
| `docs/prototypes/exports/*.png` | 10 张原型图的 PNG 导出，用于视觉对比 |

---

## 测试执行命令

```powershell
# 编译检查
python -m compileall -q src tests mobile

# 全量测试
python -m pytest -q

# 仅新测试
python -m pytest tests/unit/test_visual_regression.py tests/unit/test_game_mode.py tests/unit/test_character_create.py tests/unit/test_death_screen.py -v

# 破坏性测试
python -m pytest tests/unit/test_e2e_destructive.py -v
```

---

## 最终交付标准

1. **557+ 测试全绿**，0 failed，0 error
2. **原型对齐率 100%**：10 张原型图的每个 UI 元素在 APK 中都有对应实现
3. **代码质量**：无 lint 警告、无死代码、无重复常量
4. **架构平衡**：无单一文件超过 500 行，无单一模块占比超过 40%
5. **存读档兼容**：旧存档加载时新字段用默认值，不崩溃
6. **安全**：API key 不入 state、apply_delta 防御完整、2917 彩蛋不影响非触发路径
7. **视觉**：三套主题色与原型 CSS 色值对齐（delta < 5%）

