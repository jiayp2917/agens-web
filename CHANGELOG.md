# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.4.0] — 2026-06-12

### Added — 全面可玩化

**9 境界全部解锁**

- 后 4 境界（合体/大乘/渡劫/飞升）突破逻辑完整开放
- 飞升境界触发大结局（`meta.finale`），引擎回调 `on_game_over`
- 8 灵根 `cultivation_bonus` 全程生效（天/地/玄/黄 × 金/木/水/火/土/冰/雷/暗）
- 新增 `tests/unit/test_realm_full.py`（9 境界突破全覆盖）

**战斗系统**

- REPL 端 5 个战斗命令：`/attack` `/technique <名>` `/item <名>` `/defend` `/flee`
- `CombatEngine` 回合制战斗（功法 MP 消耗、丹药效果、状态影响）
- 新增 `/breakthrough` 命令（终端 + Kivy 双前端可用）
- 新增 `combat_narrator.md` 系统提示词

**Settings UI 增强**

- 8 个服务商预设：Agnes Flash / 2.0 / 1.5 + DeepSeek + 通义千问 + 智谱 GLM + Ollama + 自部署
- 选预设自动填入 Base URL，Model 可覆盖
- 4 个 TextInput 绑定回车键（`on_text_validate` 链式推进）
- 内置 Key 状态指示（自定义 Key / 内置 Key）

**APK 构建流水线**

- Buildozer 完整配置（Python 3.11.9，API 34，arm64-v8a）
- `/build-apk` Claude Code skill：7 步自动打包（WSL rsync → 软链 → buildozer → APK → 桌面）
- 支持 `--clean` 清除缓存、`--release` 正式签名
- WSL2 环境一键打包，输出 22MB debug APK

**移动端 UI**

- 5 个 Screen：game / settings / save / combat / tutorial
- 6 个 Widget：action_bar / combat_bar / loading_overlay / narrative_view / realm_card / status_bar
- `EngineAdapter` 业务适配层（Kivy ↔ GameEngine）
- Android 私有目录存储 settings.json / saves/

### Changed

- `apply_delta` 防御强化：realm 白名单 + `xxx_add=None` 守卫 + 整数字段负数下限 + `status_effects` isinstance 守卫
- `_has_api_key` 统一为 `Settings.has_api_key()`（settings.json > 环境变量 > 内置 Key）
- REPL 命令从 17 个扩展到 23 个
- `GameEngine` 重构为 UI 无关层（callback 驱动，REPL/Kivy 双前端复用）

### Fixed

- 修复 `world_builder` 的 `max_tokens=1024` 导致 JSON 截断 → `4096`
- 修复 Kivy 3.14+ lambda 赋值语法不兼容 Python 3.11 → 改用 `def` 命名函数
- 修复 PEP 668 阻止 WSL 系统级 pip → `PIP_BREAK_SYSTEM_PACKAGES=1`

### Tests

- 445 个测试全部通过（从 219 → 445，新增 226 个）
- 新增测试文件：`test_realm_full.py`, `test_combat.py`, `test_game_engine.py`, `test_game_turn.py`, `test_constants.py`, `test_engine_render.py`, `test_mobile_startup.py`, `test_e2e_real_llm.py`

## [0.2.0] — 2026-06-12

### Changed — 重大改造

**从 "AI 小说写作助手" 改造为 "AI 文字修仙模拟器"**

- REPL 从线性写作流水线改为**回合制游戏循环**
- 删除 5 个旧 Agent（Chat / Planner / Writer / Reviewer / Editor）和编排器
- 新增 3 个游戏 Agent：
  - **Narrator** — 天道叙述者，处理玩家行动，生成叙事 + `<state_update>` 状态变化
  - **World Builder** — 世界设计师，`/new` 创建角色和世界
  - **Judge** — 规则仲裁者，审核状态变化合理性
- 新增 `GameSession` dataclass（替代 `PipelineSession`），支持：
  - 扁平化角色/世界状态字段
  - `apply_delta()` 增量更新（`+N`/`-N` 字符串、int 绝对值）
  - JSON 序列化存读档
- 新增 17 个游戏命令（`/new` `/save` `/load` `/status` `/inv` `/skills` `/map` `/quest` `/log` `/expand` `/reset` 等）
- 新增 Rich 格式化 UI（HP/MP 进度条、角色卡面板、背包/功法表格）
- 新增自动存档系统（`runtime/saves/`，路径清理防止目录穿越）
- 新增 3 个修仙主题系统提示词

### Fixed

- `apply_delta()` 中 `bool` 子类绕过 `int` 检查的 bug（`True`/`False` 会被当作 1/0 写入 hp）
- `apply_delta()` 中 `+abc`/`-xyz` 等非法增量字符串导致 `ValueError` 崩溃（增加 try/except）
- `render_inventory_table()` / `render_skills_table()` 对非字典物品的 `AttributeError` 崩溃

### Removed

- 删除旧 Agent 目录：`agents/chat/`, `agents/planner/`, `agents/writer/`, `agents/reviewer/`, `agents/editor/`
- 删除编排器：`orchestrator/`
- 删除旧状态类型：`orchestrator_schema.py`, `schema.py`, `chat_schema.py`
- 删除旧 REPL 组件：`pipeline_session.py`, `stage_runner.py`, `planner_view.py`
- 删除旧系统提示词：`chat.md`, `planner.md`, `writer.md`, `reviewer.md`, `editor.md`
- 删除旧测试：`test_repl_pipeline.py`, `test_orchestrator.py`, `test_writer.py`, `test_planner_parse.py`, `test_reviewer_parse.py`

### Tests

- 全部测试重写/替换为游戏上下文
- 新增 117 个破坏性测试（`test_destructive.py`）
- 总计 219 个测试全部通过

### Docs

- 重写 `README.md` 为修仙模拟器使用指南
- 重写 `docs/README.md` 为 LangGraph 4-node 模式速查
- 新建 `docs/agents.md` 替代旧 `docs/writer_agent.md`
- 更新 `docs/security.md` 移除 Writer Agent 引用
- 更新 `config/default.yaml` 为游戏 Agent 配置
- 新建 `CLAUDE.md` 项目级 AI 助手指引
- 新建 `CHANGELOG.md`

## [0.1.0] — 2026-06-10

### Added

- 初始版本：AI 小说写作助手
- LangGraph 多 Agent 流水线架构
- 5 个写作 Agent（Chat / Planner / Writer / Reviewer / Editor）+ 编排器
- 交互式 REPL（`/plan` `/write` `/review` `/edit` `/run` `/step`）
- LLM 客户端（OpenAI 兼容、重试、SSE）
- 运行产物持久化
- API key 安全处理（环境变量 + 日志脱敏）
- 中文 i18n 全量覆盖
