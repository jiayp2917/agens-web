# agens-novel — Android 文字修仙模拟器

## 项目定位

AI 驱动的 Android 竖屏文字修仙模拟器。产品入口只保留 Kivy/Buildozer 移动端；终端 REPL/CLI 不再作为对外通路。核心玩法由三个 Agent 协作：

- **Narrator**：生成叙事、状态变化和下一回合 A/B/C 选项。
- **World Builder**：创建角色、世界开局和开场 A/B/C 选项。
- **Judge**：审核状态变化与世界逻辑是否合理。

## 当前玩法契约

- 单一 A/B/C/D 模式：A/B/C 由模型基于上下文生成；D 是玩家底部输入框自由键入。
- 模型失败或无选项时才兜底，并显示“天道紊乱，暂以因果残影指引。”。
- 战斗不提供常驻按钮，玩家通过 D 输入框键入攻击、防御、逃跑、施展功法等行动。
- 主页、读档、教程、设置使用 Android/Kivy 弹窗或页面，不恢复旧独立终端入口。
- 界面不得明示隐藏触发规则或隐藏模式名称。
- 境界顺序：练气、筑基、金丹、元婴、化神、合体、大乘、渡劫、飞升；不得恢复已删除的旧境界。

## 技术栈

- **Kivy**：Android UI。
- **Buildozer**：Android APK 打包。
- **LangGraph**：Agent 调用图。
- **httpx**：OpenAI 兼容 API 调用。
- **pytest**：核心逻辑、迁移兼容和 UI 源码契约测试。

## 开发入口

产品验证只走 Android APK + USB 真机调试；Windows 桌面 Kivy 窗口不再作为流程验证方式。

测试环境：

```powershell
cd D:\chat\agens
python -m venv .venv
.\.venv\Scripts\activate
pip install -e ".[dev]"
```

USB 真机调试：

```powershell
$adb = 'C:\Users\29176\adb\platform-tools\adb.exe'
& $adb devices -l
& $adb install -r D:\chat\plan\<apk-name>.apk
& $adb shell am force-stop org.agens.agensnovel
& $adb shell am start -n org.agens.agensnovel/org.kivy.android.PythonActivity
```

可选模型环境变量：

```powershell
$env:AGNES_BASE_URL = "https://apihub.agnes-ai.com/v1"
$env:AGNES_MODEL    = "agnes-2.0-flash"
$env:AGNES_API_KEY  = "<你的 key>"
```

## 文档索引

后续智能体先读 `docs/INDEX.md`。项目结构边界、冗余清理和技术债见 `docs/PROJECT_AUDIT.md`。非玩法类执行细则见 `docs/AGENT_OPERATION_RULES.md`。

## 关键文件

### Agent

| Agent | 目录 | 系统提示词 |
| --- | --- | --- |
| Narrator | `src/agens_novel/agents/narrator/` | `config/prompts/system/narrator.md` |
| World Builder | `src/agens_novel/agents/world_builder/` | `config/prompts/system/world_builder.md` |
| Judge | `src/agens_novel/agents/judge/` | `config/prompts/system/judge.md` |

### 核心层

| 模块 | 关键文件 | 职责 |
|------|---------|------|
| Engine | `src/agens_novel/engine/game_engine.py` | 唯一游戏逻辑入口，通过 callbacks 解耦 UI |
| | `src/agens_novel/engine/turn_runner.py` | Agent 调用器，每回合 LLM 调用 |
| | `src/agens_novel/engine/render.py` | UI 无关的文本格式化 |
| Session | `src/agens_novel/session/game_session.py` | 会话状态、`apply_delta`、序列化 |
| Game | `src/agens_novel/game/realm.py` | 境界突破与资源/感悟门槛 |
| | `src/agens_novel/game/combat.py` | 回合制战斗逻辑 |
| | `src/agens_novel/game/constants.py` | 游戏常量配置 |
| Persistence | `src/agens_novel/persistence/save_manager.py` | JSON 存读档 |
| State | `src/agens_novel/state/game_schema.py` | 游戏状态数据模型 |
| | `src/agens_novel/state/reducers.py` | 状态更新器 |
| LLM | `src/agens_novel/llm/client.py` | OpenAI 兼容 HTTP 客户端 |
| | `src/agens_novel/llm/sse.py` | SSE 流式响应解析 |

### 测试分层

| 层级 | 目录 | 内容 |
|------|------|------|
| E2E | `tests/e2e/` | 端到端测试（play_simulation） |
| Integration | `tests/integration/` | 跨模块测试 |
| Unit | `tests/unit/` | 单元测试，按模块分层 |
| | `tests/unit/game/` | 游戏规则测试 |
| | `tests/unit/engine/` | 引擎逻辑测试 |
| | `tests/unit/state/` | 状态管理测试 |
| | `tests/unit/llm/` | LLM 集成测试 |
| | `tests/unit/agents/` | Agent 测试 |
| | `tests/unit/settings/` | 配置测试 |
| Mobile | `tests/mobile/` | 移动端测试 |
| Destructive | `tests/destructive/` | 破坏性场景测试 |

### Android 层

- `mobile/main.py`：Kivy App 入口。
- `mobile/screens/home_screen.py`：主页、设置、读档、教程弹窗。
- `mobile/screens/character_create_screen.py`：角色创建。
- `mobile/screens/game_screen.py`：主游戏页、更多工具弹窗、存读档弹窗。
- `mobile/screens/death_screen.py`：死亡与飞升终局。
- `mobile/widgets/action_bar.py`：底部 D 输入栏与“更多”入口。
- `mobile/widgets/narrative_view.py`：叙事与 A/B/C 选项。
- `mobile/widgets/status_bar.py`：顶部角色信息。
- `mobile/widgets/combat_bar.py`：紧凑战斗状态提示。
- `mobile/service/engine_adapter.py`：Kivy 主线程和 GameEngine 的桥接。
- `mobile/buildozer.spec`：APK 打包配置。

## 架构约束

- 不恢复 `agens-novel` CLI、`python -m agens_novel repl` 或 Rich/Typer 终端 UI。
- `GameEngine` 是唯一游戏逻辑入口；Android UI 不直接改 `GameSession`。
- Agent、LLM client、Session、Persistence 保持 UI 无关。
- API key 不写入仓库、文档、日志或持久化环境变量；只从当前进程环境变量或用户设置读取。
- `llm/client.py`、`llm/retry.py`、`llm/sse.py` 是通用 LLM 层，非必要不改。
- 资产放在 `mobile/assets/`，Buildozer 需包含最终使用格式。
- 不回退用户已有改动；遇到脏工作区先理解再修改。

## 常用命令

```powershell
# 编译检查
.\.venv\Scripts\python.exe -m compileall -q src tests mobile\main.py mobile\audio_manager.py mobile\screens mobile\widgets mobile\service

# 运行测试
.\.venv\Scripts\python.exe -m pytest -q

# APK 打包
/build-apk
/build-apk --clean
/build-apk --release
```
## 通用编码准则


**权衡：** 这些准则偏向谨慎而非速度。对于简单任务，请使用判断力。


### 1. 第一规则：不确定就问


**不要假设。不要隐藏困惑。需求、边界、设计方向或预期结果不明确时，先停下来问用户。**


实现前：
- 明确陈述你的假设。不确定时提问。
- 存在多种解释时，提出它们，不要默默选择。
- 存在更简单方案时说出来。有理由时要反驳。
- 有不清楚的地方停下来，指出困惑点并提问。
- 这条规则优先于执行速度，尤其适用于 UI 方向、真实作品写回、破坏性清理、大范围重构、Git 提交/推送、API key 处理、模型供应商调整，以及任何可能让用户不清楚“到底改了什么”的操作。


### 2. 简洁优先


**解决问题的最少代码。不要投机。**


- 不添加超出需求的功能。
- 不为单用途代码创建抽象。
- 不添加未请求的"灵活性"或"可配置性"。
- 不为不可能的场景添加错误处理。
- 如果200行能写成50行，就重写。


自问："高级工程师会说这太复杂吗？"如果是，简化。


### 3. 精准改动


**只触碰必须改动的。只清理自己的烂摊子。**


编辑现有代码时：
- 不要"改进"相邻代码、注释或格式。
- 不要重构没坏的东西。
- 匹配现有风格，即使你会用不同方式。
- 注意到无关的死代码时，提出它，不要删除。


当改动产生孤立代码时：
- 移除你的改动导致未使用的 import/变量/函数。
- 不要删除预先存在的死代码，除非被要求。


验证标准：每一行改动都可追溯到用户请求。


### 4. 目标驱动执行


**定义成功标准，循环验证直到完成。**


将任务转化为可验证的目标：
- "添加验证" → "为无效输入写测试，然后让测试通过"
- "修复 bug" → "写一个复现 bug 的测试，然后让测试通过"
- "重构 X" → "确保重构前后测试都通过"


对于多步骤任务，陈述简要计划：
```
1. [步骤] → 验证: [检查]
2. [步骤] → 验证: [检查]
3. [步骤] → 验证: [检查]
```


强成功标准让你能独立循环。弱标准（"让它工作"）需要持续澄清。


---
