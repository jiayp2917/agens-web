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

- **Kivy**：Android UI 与桌面调试窗口。
- **Buildozer**：Android APK 打包。
- **LangGraph**：Agent 调用图。
- **httpx**：OpenAI 兼容 API 调用。
- **pytest**：核心逻辑、迁移兼容和 UI 源码契约测试。

## 开发入口

```powershell
cd D:\chat\agens
.\.venv311\Scripts\python.exe mobile\main.py
```

测试环境：

```powershell
cd D:\chat\agens
python -m venv .venv
.\.venv\Scripts\activate
pip install -e ".[dev]"
```

可选模型环境变量：

```powershell
$env:AGNES_BASE_URL = "https://apihub.agnes-ai.com/v1"
$env:AGNES_MODEL    = "agnes-2.0-flash"
$env:AGNES_API_KEY  = "<你的 key>"
```

## 关键文件

### Agent

| Agent | 目录 | 系统提示词 |
| --- | --- | --- |
| Narrator | `src/agens_novel/agents/narrator/` | `config/prompts/system/narrator.md` |
| World Builder | `src/agens_novel/agents/world_builder/` | `config/prompts/system/world_builder.md` |
| Judge | `src/agens_novel/agents/judge/` | `config/prompts/system/judge.md` |

### 核心层

- `src/agens_novel/engine/game_engine.py`：唯一游戏逻辑入口，通过 callbacks 解耦 UI。
- `src/agens_novel/engine/turn_runner.py`：Agent 调用器。
- `src/agens_novel/session/game_session.py`：会话状态、`apply_delta`、序列化。
- `src/agens_novel/persistence/save_manager.py`：JSON 存读档。
- `src/agens_novel/game/realm.py`：境界突破与资源/感悟门槛。
- `src/agens_novel/game/combat.py`：回合制战斗逻辑。
- `src/agens_novel/engine/render.py`：UI 无关的文本格式化。

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
.\.venv\Scripts\python.exe -m compileall -q src tests mobile\main.py mobile\audio_manager.py mobile\screens mobile\widgets mobile\service demo_full_flow.py

# 运行测试
.\.venv\Scripts\python.exe -m pytest -q

# 桌面调试 Android/Kivy 窗口
.\.venv311\Scripts\python.exe mobile\main.py

# APK 打包
/build-apk
/build-apk --clean
/build-apk --release
```
