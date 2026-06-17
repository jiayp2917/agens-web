# agens_novel Architecture

## 概述

`agens_novel` 是文字修仙模拟器的核心引擎，提供游戏逻辑、状态管理、AI 集成等功能。本模块与 Kivy UI 层（`mobile/`）分离，可独立测试和运行。

- **版本**：0.4.0
- **Python**：≥3.11
- **入口**：仅 `mobile/main.py`（Android/Kivy），无 CLI/REPL/终端入口
- **Agent 框架**：LangGraph（3 Agent：Narrator / World Builder / Judge）
- **LLM 协议**：OpenAI 兼容 HTTP（SSE 流式 + 非流式）

## 模块协作流程

```
mobile/main.py (Kivy 入口)
    ↓
mobile/service/engine_adapter.py (UI ↔ 引擎唯一桥，线程安全)
    ↓
src/agens_novel/engine/game_engine.py (核心游戏循环，唯一逻辑入口)
    ├─→ engine/turn_runner.py (每回合调 LLM Agent，asyncio.run)
    ├─→ engine/render.py (游戏状态 → UI 文本)
    ├─→ game/realm.py (境界推进与突破判定)
    ├─→ game/combat.py (回合制战斗，不走 LLM)
    └─→ persistence/save_manager.py (JSON 多槽位存档)
    ↓
src/agens_novel/session/game_session.py (运行时可变状态，Engine 持有)
    ↓
src/agens_novel/agents/{narrator,world_builder,judge}/ (LangGraph Agent)
    ↓
src/agens_novel/llm/client.py (OpenAI 兼容 HTTP)
    ↓
src/agens_novel/state/{game_schema,reducers}.py (类型 schema + reducer)
```

**引擎回调清单**（`GameEngine` → `EngineAdapter` → Kivy 主线程）：

| 回调 | 触发时机 |
|------|---------|
| `on_narrative(text, turn_count, choices)` | 每回合叙事产出 |
| `on_stream_chunk(chunk_text, is_partial)` | SSE 流式增量 |
| `on_combat_update(state)` | 战斗状态变更 |
| `on_status_bar(data)` | 角色状态变更（更新顶部状态栏） |
| `on_info(message)` | 系统提示/引导（如"感悟不足"） |
| `on_loading(is_loading, message)` | 加载中/加载完成 |
| `on_game_over(reason)` | 死亡等非飞升终局 |
| `on_finale(reason)` | 飞升终局（渡劫突破成功→飞升成仙） |

## 核心模块

### `engine/` — 游戏引擎

| 文件 | 职责 | 关键入口 | 依赖 |
|------|------|---------|------|
| `game_engine.py` | 核心游戏循环：回合处理、阶段推进、突破、战斗分发、通过回调向 UI 推送事件 | `GameEngine.handle_action` / `.start_from_profile` / `.attempt_breakthrough` / `.normalize_choices` / `._set_choices` | session, game, persistence, agents |
| `turn_runner.py` | 同步执行单次 LangGraph Agent 调用（`asyncio.run` 内部），按 agent 名查表 import graph，经 `_stream_context` 透传流式回调 | `run_turn_sync(agent_name, user_input, session, **kwargs)` | agents, _stream_context |
| `render.py` | 将游戏状态渲染为 UI 文本（角色卡、状态栏、境界信息） | `format_status_card` / `format_status_bar` / `format_realm` | session |
| `_stream_context.py` | thread-local 流式回调上下文 | `set_stream_callback` / `get_stream_callback` | — |

### `session/` — 会话管理

| 文件 | 职责 | 关键入口 | 依赖 |
|------|------|---------|------|
| `game_session.py` | 运行时可变状态 dataclass（角色属性/世界/背包/战斗/回合计数），带守卫的 `apply_delta`（bool/空值/类型守卫、整数解析 `+N`/`-N`），JSON 往返序列化 | `GameSession.apply_delta` / `.to_save_dict()` / `.from_save_dict(data)` | game.constants |

### `game/` — 游戏规则（纯本地逻辑，不依赖 LLM）

| 文件 | 职责 | 关键入口 | 依赖 |
|------|------|---------|------|
| `realm.py` | 境界系统：小层推进、突破资格判定、突破执行（含感悟/道具门槛、成功率、飞升终态判定） | `RealmSystem.try_advance_stage` / `.can_attempt_breakthrough` / `.attempt_breakthrough` | constants |
| `combat.py` | 回合制战斗系统，不依赖 LLM | `CombatEngine` | — |
| `constants.py` | 游戏常量：9 境界 `REALM_ORDER`、`REALM_CONFIGS`（含 stages/经验/感悟门槛/突破道具/成功率）、属性名等 | `REALM_ORDER` / `REALM_CONFIGS` | — |

### `agents/` — LangGraph Agent（3 个）

| Agent | 目录 | 职责 | 关键入口 |
|-------|------|------|---------|
| Narrator | `narrator/` | 叙事生成：产出 narrative + `<state_update>` + `<choices>`（最多 3 条，即 A/B/C 选项） | `graph.py::build_narrator_graph` / `nodes.py::_parse_narrator_output` |
| World Builder | `world_builder/` | 开局世界生成：从角色 profile 产出 `character`/`world`/`opening_narrative`/`choices` | `graph.py::build_world_builder_graph` / `nodes.py::_parse_world_builder_output` |
| Judge | `judge/` | 审核玩家动作合理性：安全默认 `{"approved": False}`（NOT approve），审核通过才 apply delta | `graph.py::build_judge_graph` / `nodes.py::_parse_judge_output` |

三个 Agent 依赖：`llm`、`config/prompts/system/*.md`

### `llm/` — LLM 集成

| 文件 | 职责 | 关键入口 |
|------|------|---------|
| `client.py` | OpenAI 兼容 HTTP 客户端：`POST {base}/chat/completions`，SSE 流式 + 非流式两路；`_resolve_config` 读 `AGNES_BASE_URL`/`AGNES_API_KEY`/`AGNES_MODEL`（优先级：显式参数 > 环境变量；API key 无内置默认值） | `LLMClient.chat` / `.stream_chat` |
| `sse.py` | SSE 流式响应解析 | `parse_sse` |
| `retry.py` | 重试逻辑 | — |
| `types.py` | LLM 相关类型定义 | — |

### `persistence/` — 存档系统

| 文件 | 职责 | 关键入口 |
|------|------|---------|
| `save_manager.py` | JSON 多槽位存读档：5 手动档（slot_1..slot_5）+ 1 自动档（autosave）；损坏文件容错返回 None；存档目录可经 `set_save_dir` 覆盖 | `save_game` / `load_game` / `list_saves` / `delete_save` / `rename_save` / `set_save_dir` |

### `state/` — 状态类型

| 文件 | 职责 | 关键入口 |
|------|------|---------|
| `game_schema.py` | 游戏状态数据模型（TypedDict schema） | 类型定义 |
| `reducers.py` | LangGraph `Annotated` reducer：`last_wins` / `apply_combat_delta` / `Append` / `ReplaceList` | — |

### `artifacts/` — 审计工件

| 文件 | 职责 | 关键入口 |
|------|------|---------|
| `store.py` | 每次 LLM 调用的输入/输出/错误审计工件，JSONL 写入 `runtime/artifacts/` | `ArtifactStore.record` / `.recent` |

### `utils/` — 工具

| 文件 | 职责 |
|------|------|
| `secrets.py` | 密钥脱敏：`redact` / `redact_dict` |
| `timing.py` | 计时器 |

### 顶层文件

| 文件 | 职责 |
|------|------|
| `paths.py` | 全局路径解析中枢：`PROJECT_ROOT` / `RUNTIME_DIR` / `SAVE_DIR` / `CONFIG_DIR` / `PROMPT_DIR` 等；支持 `AGENS_NOVEL_ROOT` 环境变量覆盖（Android 用） |
| `settings.py` | `Settings` 类：从 `AGNES_*` 环境变量读取配置，repr 时对 API key 脱敏 |
| `logging_setup.py` | `SecretRedactor` logging Filter：正则重写 `sk-...` 与 `AGNES_API_KEY=...` 形字符串，防日志泄漏 |
| `bgm.py` | 跨环境 BGM 服务：Kivy SoundLoader → pygame → 静默 stub 三级回退，best-effort fire-and-forget |

## 移动端 (`mobile/`)

| 文件/目录 | 职责 | 关键说明 |
|-----------|------|---------|
| `main.py::XianxiaApp` | Kivy 入口：平台 bootstrap（设 `AGENS_NOVEL_ROOT`/`sys.path`、CJK 字体注册）、加载设置、设存档目录、组装 4 个 Screen、`on_stop` 关闭 BGM | 产品验证：Android APK + USB 真机 |
| `service/engine_adapter.py::EngineAdapter` | **UI ↔ 引擎唯一桥**：持有 `GameEngine()` 实例；引擎回调经 `Clock.schedule_once`→Kivy 主线程；阻塞调用放 daemon thread | 全 mobile 仅此处直接 import `GameEngine` |
| `service/save_manager_compat.py` | 把 `SaveManager` 存档目录改指到 Kivy `app.user_data_dir/saves` | `set_mobile_save_dir` |
| `service/settings_store.py` | 非密钥设置持久化 JSON（`settings.json` / `user_model.json`），API key 单独存入 app-private `secrets.json`，启动时注入 `os.environ` | 普通设置文件不含 key，UI 只显示掩码摘要 |
| `audio_manager.py::AudioManager` | 单例 BGM/SFX 门面：别名（如 `"default"`）走 `agens_novel.bgm`，绝对路径走 Kivy SoundLoader；缺文件即 no-op | |
| `screens/home_screen.py` | 主菜单：新游戏 / 读档 / 设置；设置弹窗含 API Key 输入框（hint "本次启动临时使用，不写入磁盘"） | |
| `screens/character_create_screen.py` | 角色创建：游戏名/角色名/天赋/灵根/家世/难度/6 属性/随机属性；"开始修行"→`adapter.start_from_profile` | |
| `screens/game_screen.py` | 主游戏界面：叙事区 + A/B/C 选项 + D 自由输入 + "更多"工具弹窗（存档/读档/状态/背包/装备/功法/任务/突破/设置） | |
| `screens/death_screen.py` | 终局页：`is_finale=True`→标题"飞升成仙"、success 配色、`ascension_gate.png` 背景、"九天之上…"文案（不复用死亡标题） | |
| `widgets/action_bar.py` | A/B/C 按钮行 + D 自由文本输入框 | |
| `widgets/combat_bar.py` | 战斗行动栏 | |
| `widgets/narrative_view.py` | 可滚动叙事显示 + 选项按钮渲染 | |
| `widgets/status_bar.py` | 6 格状态网格（境界/层数/修为/HP/MP/感悟） | |
| `widgets/realm_card.py` | 境界信息卡 | |
| `widgets/loading_overlay.py` | 加载转圈遮罩 | |
| `theme.py` | 主题与 CJK 字体注册 | |

## LLM 接入与未成功模式

### 配置来源

`LLMClient._resolve_config`（`llm/client.py`）读取配置，优先级自上而下：

| 优先级 | 来源 |
|--------|------|
| 1（最高）| 显式传参 `base_url` / `api_key` / `model` |
| 2 | 环境变量 `AGNES_BASE_URL` / `AGNES_API_KEY` / `AGNES_MODEL` |

`base_url` 和 `model` 有非密钥默认值；`api_key` 没有内置默认值。

移动端：HomeScreen 设置弹窗填入的 key → `save_api_key` 写入 app-private `secrets.json` → `apply_settings_to_env` 注入 `os.environ`（settings_store.py）。`settings.json` / `user_model.json` 不保存 key，UI 不回显明文，只显示 provider/model/key 掩码摘要。

### Agent 层闸门（关键）

三个 Agent 的 `nodes.py` 各自在调用 LLM 前检查 `os.environ.get("AGNES_API_KEY", "")`（见 `narrator/nodes.py:35`、`world_builder/nodes.py:31`、`judge/nodes.py:35`）：

```
api_key_set = bool(os.environ.get("AGNES_API_KEY", ""))
if not api_key_set:
    return {"output_text": "", "llm_error": "AGNES_API_KEY 未设置。"}
```

**这意味着**：若不设 `AGNES_API_KEY` 环境变量或当前启动内的用户设置，agent 层直接短路返回空文本 + `llm_error`，**根本不会发起 HTTP 请求**。项目不再提供内置 API key。

若设了无效 `AGNES_API_KEY`：闸门放行 → HTTP 401 → `LLMAuthError` → `except LLMError` 捕获 → 同样落 llm_error 分支。

### 引擎兜底（未成功模式下的行为）

| 场景 | 失败处理 | 位置 |
|------|---------|------|
| 开局 `start_from_profile` world_builder 失败 | 用本地 `_profile_opening()` 生成开场白+选项 | `game_engine.py` |
| 普通回合 narrator 失败/异常 | narrative 为空字符串，`_set_choices(None, fallback_notice=True)` 生成 3 条固定兜底 A/B/C，`turn_count -= 1` 回滚 | `game_engine.py` |
| judge 异常 | 默认 `{"approved": False}`（安全拒绝），不应用 delta | `game_engine.py` |
| 突破 narrator 失败 | 叙事为空，本地兜底选项 | `game_engine.py` |

兜底选项（`fallback_choices`）：3 条固定文案（如"在{location}稳住气息，观察灵气与地势变化"），伴随提示 `CHOICE_FALLBACK_NOTICE = "天道紊乱，暂以因果残影指引。"`。

**结论**：无有效 `AGNES_API_KEY` 时——核心路径（UI→引擎→存档→境界→突破→飞升/死亡终态）均为纯本地逻辑，可完整跑通；但每回合 AI 叙事为空，A/B/C 仅为带“天道紊乱”提示的兜底文案。

## 存档机制

### 目录

- 默认：`<project_root>/runtime/saves`
- 移动端覆盖：`app.user_data_dir/saves`（经 `mobile/service/save_manager_compat.py` 在启动时调用 `set_save_dir`）
- 目录由 `paths.py::SAVE_DIR` 定义，模块级 `_custom_save_dir` 优先

### 格式与槽位

- 格式：JSON（`json.dumps(session.to_save_dict(), indent=2)`）
- 文件名：`{name}.json`，name 经清洗为 `[alnum_-]`（防目录穿越）
- 槽位：5 手动档（`slot_1` ~ `slot_5`）+ 1 自动档（`autosave`），`MAX_MANUAL_SAVES = 5`
- 自动保存时机：每回合处理完毕后、开局完成后、突破后（`game_engine.py::_auto_save`）
- 损坏文件容错：`load_game` 返回 `None` 而非抛异常

### 关键函数

| 函数 | 签名 |
|------|------|
| `save_game(session, name)` | 保存游戏到指定槽位 |
| `load_game(name)` | 从指定槽位加载，失败返回 `None` |
| `list_saves()` | 列出所有存档（最近优先） |
| `delete_save(name)` | 删除指定存档 |
| `rename_save(old, new)` | 重命名存档 |
| `get_manual_save_slots()` | 返回可用手动档位列表 |
| `set_save_dir(path)` | 覆盖存档目录（移动端启动时调用） |

## 境界表

`src/agens_novel/game/constants.py`

**9 境界**（`REALM_ORDER`）：练气 → 筑基 → 金丹 → 元婴 → 化神 → 合体 → 大乘 → 渡劫 → 飞升

不包含任何旧版已删除境界。

`REALM_CONFIGS` 为每个境界配置：`stages`（小层数）、`experience_required`、`insight_required`（突破所需感悟）、`breakthrough_items`（突破道具需求）、`base_success_rate`（基础成功率）、`realm_bonus` 等。飞升为终态（stages=1, experience_required=999999, rate=0.0）。

突破判定（`RealmSystem.can_attempt_breakthrough`）：
1. 满层（`realm_stage >= stages`）
2. 满修为（`experience >= experience_to_next`）
3. 感悟达标（`insight >= insight_required`）
4. 有下一境界

小层推进（`try_advance_stage`）仅受修炼 XP 影响——**大境界突破才需要感悟门槛**。

## UI 集成

Android UI（Kivy）通过 **唯一入口** 调用游戏引擎：

```python
# mobile/service/engine_adapter.py
from agens_novel.engine.game_engine import GameEngine

engine = GameEngine()
engine.on_narrative = lambda text, turn, choices: ui.update_narrative(text, turn, choices)
engine.on_combat_update = lambda state: ui.update_combat(state)
engine.on_status_bar = lambda data: ui.update_status_bar(data)
engine.on_info = lambda msg: ui.show_info(msg)
engine.on_loading = lambda is_loading, msg: ui.show_loading(is_loading, msg)
engine.on_finale = lambda reason: ui.show_finale(reason)
engine.on_game_over = lambda reason: ui.show_game_over(reason)
```

**重要约定**：
- UI 只通过 `engine_adapter.py` 调用 `GameEngine`
- `game_screen.py` 对 `agens_novel.persistence.save_manager` 的少量直接 import 仅限只读列表查询（`list_saves` / `get_manual_save_slots`），不触及引擎逻辑
- 所有状态更新通过事件回调
- REPL/CLI/终端入口已于历史版本移除，仅保留 `mobile/main.py` 单一入口

## 关键文件路径

| 模块 | 关键文件 |
|------|---------|
| 引擎入口 | `src/agens_novel/engine/game_engine.py` |
| 会话管理 | `src/agens_novel/session/game_session.py` |
| 境界系统 | `src/agens_novel/game/realm.py` |
| 游戏常量 | `src/agens_novel/game/constants.py` |
| 存档系统 | `src/agens_novel/persistence/save_manager.py` |
| Agent 调用 | `src/agens_novel/engine/turn_runner.py` |
| LLM 客户端 | `src/agens_novel/llm/client.py` |
| 路径配置 | `src/agens_novel/paths.py` |
| UI 桥接 | `mobile/service/engine_adapter.py` |
| Kivy 入口 | `mobile/main.py` |

## 扩展指南

### 添加新的游戏规则
1. 在 `game/` 下创建新模块或扩展现有模块
2. 在 `GameEngine` 中添加对应的处理方法
3. 在 `engine_adapter.py` 中添加 UI 触发点

### 添加新的 Agent
1. 在 `agents/` 下创建新目录
2. 实现 LangGraph Agent 接口（graph + nodes）
3. 在 `turn_runner.py` 中注册调用

### 修改状态模型
1. 更新 `session/game_session.py`（字段 + `apply_delta` 守卫 + 序列化）
2. 更新 `state/game_schema.py`（TypedDict schema）
3. 添加对应的 reducer 到 `state/reducers.py`
4. 确保 `persistence/save_manager.py` 的 JSON 往返兼容（`to_save_dict` / `from_save_dict`）
