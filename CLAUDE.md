# agens-novel — 文字修仙模拟器

## 项目定位

AI 驱动的文字修仙模拟器（互动叙事 + 多 Agent 回合制）。玩家在 REPL 中用自然语言行动，三个 AI Agent 协作响应：

- **Narrator** — 天道叙述者，生成叙事和状态变化
- **World Builder** — 世界设计师，创建角色和世界内容
- **Judge** — 规则仲裁者，审核状态变化合理性

双前端支持：终端 REPL（Rich）+ Android APK（Kivy/Buildozer）。

## 技术栈

- **LangGraph** — 4 节点线性图（`load_settings → build_prompt → call_agnes_llm → save_artifact`）
- **Rich** — 终端 UI（角色卡、HP/MP 条、背包表格）
- **Kivy** — Android 移动端 UI（5 个 Screen + 6 个 Widget）
- **Typer** — CLI 入口
- **httpx** — OpenAI 兼容 API 调用（同步封装异步）
- **Buildozer** — APK 打包（WSL2，arm64-v8a，API 34）

## 开发入口

```powershell
cd D:\chat\agens
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"

# 设置环境变量
$env:AGNES_BASE_URL = "https://apihub.agnes-ai.com/v1"
$env:AGNES_MODEL    = "agnes-2.0-flash"
$env:AGNES_API_KEY  = "<你的 key>"
$env:PYTHONPATH     = "src"

# 启动模拟器
python -m agens_novel repl
```

## 关键文件

### Agent 源码（各自独立）
| Agent | 目录 | 系统提示词 |
|-------|------|-----------|
| Narrator | `src/agens_novel/agents/narrator/` | `config/prompts/system/narrator.md` |
| World Builder | `src/agens_novel/agents/world_builder/` | `config/prompts/system/world_builder.md` |
| Judge | `src/agens_novel/agents/judge/` | `config/prompts/system/judge.md` |

### 游戏引擎（UI 无关层）
- `engine/game_engine.py` — `GameEngine` 类（事件驱动，通过 callbacks 解耦 UI）
- `engine/render.py` — 文本格式化（角色卡、背包表、战斗信息等）

### 游戏逻辑
- `game/combat.py` — `CombatEngine`（回合制战斗、功法/物品消耗）
- `game/realm.py` — `RealmSystem`（9 境界突破 + 8 灵根加成）
- `game/constants.py` — 境界/灵根/稀有度/装备槽常量

### 游戏状态
- `state/game_schema.py` — `GameState`, `CharacterState`, `WorldState` TypedDict
- `state/reducers.py` — LangGraph state reducer（列表追加等）
- `repl/game_session.py` — `GameSession` dataclass（扁平化状态 + `apply_delta` + 序列化）

### REPL
- `repl/loop.py` — 主游戏循环（`Repl` 类，委托 `GameEngine`）
- `repl/commands.py` — 命令解析器（23 个游戏命令）
- `repl/game_view.py` — Rich 渲染（角色卡、进度条、表格）
- `repl/save_manager.py` — 存读档（JSON → `runtime/saves/`）
- `repl/turn_runner.py` — Agent 调用器（stream_callback 通过 thread-local 传递）
- `repl/_stream_context.py` — 线程局部上下文（避免 stream_callback 进入 LangGraph state）
- `repl/status_view.py` — 配置/状态显示

### 共享基础
- `llm/client.py` — `call_llm()` 异步 LLM 调用（含内置 Key base64）
- `llm/retry.py` — 指数退避重试
- `llm/sse.py` — SSE 流解析
- `llm/types.py` — `Message`, `LLMResponse` 类型
- `artifacts/store.py` — 运行产物持久化
- `utils/secrets.py` — API key 脱敏
- `utils/timing.py` — UTC 时间戳
- `paths.py` — 路径解析（config/prompts/runtime）
- `settings.py` — `Settings` 配置类（API key/URL/model）

### 移动端
- `mobile/main.py` — Kivy App 入口（平台引导 + 内置 Key 注入 + HomeScreen 注册）
- `mobile/screens/` — 6 个 Screen（home/game/settings/save/combat/tutorial）
- `mobile/widgets/` — 6 个 Widget（action_bar/combat_bar/loading_overlay/narrative_view/realm_card/status_bar）
- `mobile/service/` — 业务适配层（engine_adapter/settings_store/save_manager_compat）
- `mobile/theme.py` — 三色主题系统（WHITE/BLACK/GREEN + themed widgets）
- `mobile/buildozer.spec` — APK 打包配置

## 常用命令

```powershell
# 编译检查
python -m compileall -q src tests

# 运行测试
python -m pytest -q

# 启动 REPL
python -m agens_novel repl

# 查看 CLI 帮助
python -m agens_novel --help

# 打包 APK（通过 WSL2 + Buildozer）
/build-apk
/build-apk --clean      # 清缓存重打包
/build-apk --release    # 正式签名版
```

## 架构约束

- **不把小说正文、角色设定写入全局规则** — 游戏数据只存在于 `GameSession`
- **API key 永远不写入磁盘** — 只从环境变量 `AGNES_API_KEY` 读取（或内置 base64 Key）
- **LLM 层零修改** — `llm/client.py`, `llm/retry.py`, `llm/sse.py` 是通用组件
- **Agent 独立** — 每个 Agent 目录自包含（`nodes.py` + `graph.py`）
- **stream_callback 不进入 LangGraph state** — 通过 `repl/_stream_context.py` 线程局部变量传递，避免 msgpack 序列化失败
- **GameEngine 是唯一游戏逻辑入口** — REPL 和移动端都委托 GameEngine，不直接改 GameSession
- **Engine 通过 callbacks 解耦 UI** — `on_narrative/on_error/on_combat_update/on_finale` 等回调由 UI 层注册

## 游戏数据流

```
玩家输入 → parse_command()
    │
    ├── /new → World Builder → 初始化 GameSession
    ├── 行动 → Narrator → Judge → apply_delta → 显示 → 自动存档
    ├── /breakthrough → RealmSystem.attempt_breakthrough() → 突破判定
    ├── /attack /defend /flee /technique /item → CombatEngine → 战斗回合
    └── /save /load /status → 存档管理 / 状态显示
```

### apply_delta 规则
- `"+N"` 字符串 → 增量加（`current + N`）
- `"-N"` 字符串 → 增量减（`max(0, current - N)`）
- `int` → 绝对赋值
- `bool` → 忽略（bool 是 int 子类，已加守卫）
- 其他类型 → 静默忽略
- `techniques_add` / `inventory_add` / `lore_add` / `discovered_add` → `list.extend()`
- `status_effects` → 直接赋值（含 `isinstance(val, list)` 守卫）
- `realm` → 白名单校验（9 境界）
- `None` → 安全跳过（`xxx_add=None` 不崩溃）

## 测试

```powershell
python -m pytest -q                          # 全部测试
python -m pytest tests/unit/test_destructive.py -v  # 破坏性测试
python -m pytest tests/integration/ -v       # 真 LLM 集成测试（需要 AGNES_API_KEY）
```

537 个测试覆盖：命令解析、Agent 输出解析、游戏回合循环、存读档、状态 delta、渲染、破坏性输入、9 境界突破、战斗系统、真 LLM 端到端、UI 修复验证、e2e 全链路。
