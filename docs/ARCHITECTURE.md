# 项目模块架构说明

## 2026-06-27 Main-Flow Architecture Note

- `GameEngine.handle_action()` now routes breakthrough-intent actions to the
  dedicated breakthrough flow only when `RealmSystem.can_attempt_breakthrough()`
  allows it. Otherwise the action stays in the ordinary `TurnFlow` path.
- `TurnFlow` owns the repaired mismatch behavior: model narrative/state can be
  rejected while the base rule settlement still advances and records the turn.
- `WebGameService._record_settled_turn()` continues to persist only settled
  registered-user turns, relying on `turn_history[-1]["turn"] ==
  session.turn_count` to avoid logging partial or stale turns.
- These changes preserve the existing API shape and business schema. A later
  documentation-only Alembic revision adds PostgreSQL comments without changing
  runtime tables or write behavior.

> **状态：v5 已实现 / 阶段 7/8 联调收尾中**
> **阅读对象**：新加入开发者、技术复核者、想了解全局的玩家
> **与现有文档关系**：本文是**模块视角**的地图；[RUNTIME_FLOW.md](RUNTIME_FLOW.md) 是**链路视角**的流程；[GAME_MODE_SPEC.md](GAME_MODE_SPEC.md) 是游戏模式 v5 的产品 + 技术规格；[PROJECT_AUDIT.md](PROJECT_AUDIT.md) 是结构边界和技术债队列。

## 1. 项目一句话

**WEB 文字修仙模拟器 = FastAPI 后端 + React/Vite SPA + LangGraph 多 Agent**。当前主线是**游戏模式 v5**（A/B/C/D 四按钮固定语义），引导模式与小说模式作为禁用入口保留。

## 2. 顶层分层

| 层级 | 路径 | 入口文件 | 职责 |
| --- | --- | --- | --- |
| Web 交互层 | `web/frontend-react/src/` | `main.tsx` | 浏览器展示、点击、设置、存读档入口；不直接改游戏状态 |
| API 层 | `web/backend/` | `app.py` | FastAPI 路由、Cookie 鉴权、限流、同源校验、生产 fail-fast |
| 游戏核心层 | `src/agens_novel/` | `engine/game_engine.py` | Agent 调用、规则结算、状态落账、境界、突破、死亡、飞升 |
| 数据层 | `web/backend/database*.py` + `migrations/versions/` | `database.py` | PostgreSQL 单后端；WebDatabaseProtocol 抽象；Alembic 拥有生产 schema |
| 配置 / 资源层 | `config/prompts/` + `web/frontend-react/public/assets/` | — | system prompt、图片、BGM |

依赖方向：**Web 交互层 → API 层 → 游戏核心层 → 数据层**。反向不允许。

## 3. 后端模块清单（`web/backend/`）

| 文件 | 关键类 / 函数 | 职责 |
| --- | --- | --- |
| `app.py` | `create_app()`, `is_production_mode()`, `validate_runtime_config()` | FastAPI 工厂、27 个路由注册、`TrustedHostMiddleware` + `BodySizeLimitMiddleware` + 同源校验、`RateLimiter`、生产 fail-fast（缺 `SESSION_SECRET` / `DATABASE_URL` / `INVITE_ADMIN_CODE` / `AGENS_ALLOWED_ORIGINS` 时拒启动） |
| `app_models.py` | `RegisterRequest`, `LoginRequest`, `StartRequest`, `ChoiceRequest`, `ActionRequest`, `SaveRequest`, `ModelSettingsRequest`, `InviteCreateRequest` | FastAPI 请求体 Pydantic 模型；从路由文件拆出，避免 `app.py` 同时承担模型定义和路由编排 |
| `service.py` | `WebRunner`, `WebGameService` | `WebRunner` 包装 `GameEngine` 并把引擎回调捕获为事件；`WebGameService` 是服务编排入口（创建 / 启动 / 选择 / 行动 / 存读档 / 终局） |
| `service_summaries.py` | `build_death_summary()` | 汇总终局成就、奖励和死亡分类；从 `service.py` 拆出，降低服务编排文件职责 |
| `database.py` | `WebDatabaseProtocol`, `create_database()` | `Protocol` 定义所有公开方法签名；工厂始终返回 PostgreSQL 后端（Option C：SQLite 后端已移除），连接来自 `DATABASE_URL` |
| `database_postgres.py` | `PostgresWebDatabase` | SQLAlchemy Core + `JSONB`；`__init__` 时按 `AGENS_ENV` 决定是否允许 `AGENS_PG_AUTO_DDL=1`（生产 fail-closed）；`initialize()` 建 `CREATE TABLE IF NOT EXISTS` + 种子 catalog |
| `database_postgres_schema.py` | `POSTGRES_SCHEMA_STATEMENTS` | test-only / local auto-DDL 语句列表；生产 schema 仍由 Alembic 拥有 |
| `auth.py` | `create_session_token`, `parse_session_token`, `create_guest_token`, `cookie_kwargs` | HMAC-SHA256 签名会话 token；`agens_session` / `agens_guest` 两个 HttpOnly Cookie；`GUEST_USER_PREFIX = "guest-"` |
| `security.py` | `hash_password`, `verify_password`, `enforce_same_origin` | 密码哈希（bcrypt 系）、CSRF、同源校验（`Origin` / `Referer`） |
| `database_common.py` | `load_json`, `dump_json`, `now_ts` | JSON 列编解码 + 时间戳 |
| `catalog_seed.py` | `SEED_TALENTS`, `SEED_FAMILY_BACKGROUNDS`, `SEED_SPIRIT_ROOTS`, `SEED_DIFFICULTIES`, `SEED_STORY_SEEDS` | 首次启动种子常量 |
| `__main__.py` | `app`（经模块 `__getattr__` 惰性构造） | `python -m web.backend` / `uvicorn web.backend.app:app` 入口；首次访问 `app` 时才 `create_app()`，import 时不打开 DB 连接 |

## 4. 游戏核心模块清单（`src/agens_novel/`）

### 4.1 引擎（`engine/`）

| 文件 | 关键对象 | 职责 |
| --- | --- | --- |
| `game_engine.py` | `GameEngine` | 唯一游戏逻辑入口；持有 `GameSession` + `RealmSystem`；11 个回调钩子（`on_narrative` / `on_status_bar` / `on_error` / `on_info` / `on_game_over` / `on_character_created` / `on_loading` / `on_stream_chunk` / `on_finale` / `on_model_failure_choice`）；`start_from_profile()` 与 `handle_action()` 是两个主入口 |
| `turn_runner.py` | `run_turn_sync(agent_name, user_input, session, **kwargs)` | 同步包装 LangGraph；线程隔离的 `model` / `base_url` / `api_key_set`；通过 `_stream_context.set(callback)` 避免 msgpack 序列化 callable |
| `turn_rules.py` | `settle_turn(choice_text, session)` | **规则引擎权威结算**：分类 A/B/C/D、按境界抽 elapsed_years、按风险系数与难度系数调整、属性增量、剩余寿元、`game_over_reason` 判定，并把编年史事件上下文传给 narrator |
| `event_catalog.py` | `select_chronicle_event`, `stage_feedback_due` | 数据驱动普通回合事件表；按世界包、命数画像、路线和回合阶段选择事件，阶段节点写入 `world.lore_add` |
| `world_catalog.py` | `WORLD_PACKS`, `world_pack_for_key`, `world_key_for_name` | 四套固定世界包（西陲裂土、玄都盟境、沧澜群岛、青岚药境）及事件权重/势力/冲突元数据 |
| `action_delta_policy.py` | `apply_breakthrough_flag_rule`, `validate_narrative_delta_consistency` | 纯函数规则引擎；渡劫境界追加 `tribulation_elixir` / `ascension_protection` 标志；narrative vs delta 一致性校验 |
| `choices.py` | `complete_choices()`, `fallback_choices()`, `normalize_choices()` | A/B/C/D 归一化；模型输出不足 4 个时用 `fallback_choices(session)` 按当前 `location` 兜底；D 固定为气运/天命路线 |
| `render.py` | `format_status_bar`, `format_log` 以及历史/测试用文本格式化函数 | 状态 → 文本字符串；Web 响应当前只暴露 `panels.status_bar`，旧状态/背包/功法/地图/任务/境界工具面板不再作为产品入口 |
| `local_story.py` | `start_local_story()`, `advance_local_story()`, `validate_local_story_graph()` | 回合期模型失败的固定本地故事图；角色创建开局模型失败优先走 profile-aware fallback，不再默认进入 `misty_gate` |
| `profile_opening.py` | `profile_default_world`, `profile_opening`, `profile_summary`, `fate_profile`, `fate_tendency` | 开局输入归一化；按角色名、天赋、灵根、家世、难度、六维属性和随机/手选模式推导结构化命数画像 |
| `world_generator.py` | `build_world_prompt`, `build_world_fallback`, `parse_world_response` | World Builder prompt + profile-aware 本地兜底；输出本局世界观、0-16 岁编年史、16 岁初始局势、外界情报和 A/B/C/D choices |
| `death_rewards.py` | `categorize_death`, `evaluate_achievements`, `compute_rewards`, `bonuses_to_legacy`, `apply_legacy_bonuses`, `build_run_summary` | 终局分类（飞升 > 因果反噬 > 事件 > 寿元 > 手动）+ 成就评估 + 奖励计算 + 跨局传承奖励 |
| `model_result.py` | `ModelResultKind`, `classify_narrator_result`, `classify_world_builder_result`, `classify_judge_result`, `result_diagnostics` | 模型输出分类（OK / REQUEST_FAILED / INCOMPLETE_OUTPUT / JUDGE_FAILED / LOCAL_FALLBACK）；用于遥测与 UI 兜底判定 |

### 4.2 Agent（`agents/`）

每个 Agent 都是 4 节点 LangGraph：`load_settings → build_prompt → call_agnes_llm → save_artifact`。

| Agent | 路径 | 温度 / tokens | 节点要点 |
| --- | --- | --- | --- |
| **Narrator** | `agents/narrator/` | 默认 | 加载 `prompts/system/narrator.md`；拼接 `<当前状态>` + 压缩后的 `chat_history`（开场上下文 + 省略占位 + 最近 6 条）+ `<玩家行动>`；普通回合默认不二次 repair，突破等少数路径可启用；解析叙事正文 + `<state_update>` + `<choices>`，并记录脱敏契约诊断 |
| **Judge** | `agents/judge/` | `temperature=0.2`, `max_tokens=512` | 审核 Narrator 提议的 `state_delta`；返回 `approved` / `corrected_delta` / `judgment_note` / `review_score`；LLMError 默认 `approved=False`（安全失败） |
| **World Builder** | `agents/world_builder/` | `temperature=0.6`, `max_tokens=4096` | 新游戏和角色创建开局生成世界 + 角色；解析 `<world_data>` JSON 标签；保留 `chronicle_0_16`、`initial_situation_16`、`fate_hooks` 等动态开局字段；清理内部错误/调试字段 |
| **Sequential 包装** | `agents/sequential.py` | — | `SequentialAgentGraph` 通用 4 节点编排；3 个 Agent 共享同一编排 |
| **共享 helper** | `agents/common.py` | — | `load_agent_settings()`（narrator / judge / world_builder 的 `load_settings` 均委托至此）+ `normalize_choices()`（agents 层 A/B/C/D 选项清理，上限 4）+ `prompt_metrics()`（narrator / judge 共享）+ `call_agnes_llm_common()`（judge / world_builder 共享的非流式 LLM 调用，narrator 因 streaming/repair 保留自有实现） |

验收边界：`fallback_choices()` 或 TurnFlow 的语义补齐只保证玩家不断流；
它不是完整模型选项质量证明。live-model 成功仍要求非 fallback 且叙事、结构化
状态、选项三者同时可用；缺叙事正文、坏 `state_update` 或系统收益未落账都必须
被标记为不完整或按基础规则压制。

### 4.3 状态与会话（`session/`）

| 文件 | 关键对象 | 职责 |
| --- | --- | --- |
| `session/game_session.py` | `GameSession` dataclass | 单局权威内存状态；含 `_LEGACY_CHARACTER_FIELDS` 防御（`__setattr__` 拦截 hp/mp 等历史字段）；`apply_delta(delta)` 是唯一允许的外部写入入口（数值上下限、字段白名单、`_add` 列表合并） |

### 4.4 游戏规则（`game/`）

| 文件 | 关键对象 | 职责 |
| --- | --- | --- |
| `realm.py` | `RealmConfig` dataclass + `RealmSystem` | 9 境界配置（每境界 stages / 寿元 / 突破率 / 破境材料）；`can_attempt_breakthrough()` / `calculate_breakthrough_rate()` / `attempt_breakthrough()` / `try_advance_stage()`；飞升命中时设 `finale=True + game_over=True` |
| `constants.py` | 见下表 | 所有静态常量 |

`constants.py` 中关键常量：

- **6 维属性**：`root_bone(根骨)` / `comprehension(悟性)` / `luck(气运)` / `willpower(心性)` / `physique(体魄)` / `soul(神魂)`
- **属性尺度**：运行时统一 0-10，`DEFAULT_ATTRIBUTES` 每项为 5；旧 0-100 只在存档加载、World Builder 入局和 catalog 迁移中兼容归一化。
- **9 境界**：`练气 → 筑基 → 金丹 → 元婴 → 化神 → 合体 → 大乘 → 渡劫 → 飞升`
- **6 稀有度**：白 / 绿 / 蓝 / 紫 / 橙 / 红；权重 90 / 60 / 30 / 14 / 5 / 1
- **天赋** 5 种 + **灵根** 8 种 + **家世** 5 种 + **难度** 3 档
- **开局内容**：由 catalog（天赋 / 灵根 / 家世 / 难度）与六维属性共同决定；不再保留游戏名称或隐藏开局码。

## 5. 前端模块清单（`web/frontend-react/src/`）

### 5.1 入口与类型

| 文件 | 关键导出 | 职责 |
| --- | --- | --- |
| `main.tsx` | `App` 组件 | 根组件；5 视图状态机（`home` / `auth` / `character` / `game` / `ending`）；持 `user` / `session` / `busy` / `dialogMode` / `tutorialOpen`；挂顶栏 + BGM + 教程弹窗 |
| `api/client.ts` | `api<T>()`, `User`, `Session`, `SaveRow`, `ModelSettings` | fetch 包装（`credentials: "include"`、错误抛 `Error(detail)`）；4 个核心 DTO 类型 |
| `lib/api.ts` | `api`, `View`, `AuthMode`, `DialogMode`, `DeathSummaryResponse`, `fetchDeathSummary()`, `fetchCatalog()` | re-export + 终局摘要获取 + catalog 获取 |
| `lib/catalog.ts` | `attributes`, `fallbackCatalogs`, `manual*Names`, `randomOnlySpiritRootNames`, `manualAttributeBudget`/`Min`/`Max`, `choiceSemantics`, `realmLifespanCap`, `modelPresets`, `visibleEventTypes`, `hiddenEventTexts` | 静态数据 + fallback |
| `lib/util.ts` | `pickRandom`, `isManualRarity`, `uniqueByName`, `itemLabel`, `toPositiveNumber`, `eventText`, `isReadableEvent`, `formatTime` | 工具函数 |
| `styles.css` | — | 全局样式（1105 行）；水墨主题 + `≥760px` / `≤900px` / `≤480px` 三个断点 |

### 5.2 5 个页面（`pages/`）

| 页面 | 主要职责 | 关键 API |
| --- | --- | --- |
| `HomePage.tsx` | 首页品牌 + 5 入口按钮 + QQ 群卡片；纯展示，不调 API | — |
| `AuthPage.tsx` | 登录 / 注册表单；含"返回首页" | `POST /api/auth/login`、`POST /api/auth/register` |
| `CharacterCreatePage.tsx` | 角色创建；4 个 catalog 拉取 + 自行选择 / 随机生成 + 6 维滑块；提交后切到 game | `GET /api/catalog/{talents|spirit_roots|family_backgrounds|difficulties}` + `POST /api/sessions/{id}/start` |
| `GamePage.tsx` | 游戏主界面；左侧角色摘要 + 编年史故事行 + 4 选项；移动端顶部摘要 + 单列选项 | `POST /api/sessions/{id}/choice`（用户点击）；由 `App.runTurn()` 中转 |
| `EndingPage.tsx` | 飞升 / 本局结束页 + `death_summary` 侧栏（成就 / 奖励 / 最近 6 条叙事） | `GET /api/sessions/{id}/death_summary` |

### 5.3 6 个组件（`components/`）

| 组件 | Props / 行为 |
| --- | --- |
| `TutorialDialog.tsx` | `{ onClose }`；A/B/C/D 弹窗说明 |
| `BgmToggle.tsx` | 无 props；右上角扬声器；`<audio src="/assets/audio/bgm.flac" loop preload="none" />`；音量 0.42 |
| `FallbackBanner.tsx` | `{ session, busy, runTurn }`；模型失败时顶部条幅 + "继续本局 / 结束本局" |
| `SettingsSaveDialog.tsx` | `{ mode, session, user, onClose, setSession, setView, onAuth }`；存档 / 设置双 tab 弹窗；负责 tab、数据刷新和消息展示 |
| ModelSettingsPanel.tsx | user, settings, setSettings, setMessage, onAuth; logged-in user personal model settings form + guest login/register prompt; system default maintenance uses the separate admin API |
| `SaveSlotsPanel.tsx` | `{ user, saves, onSave, onLoad, onAuth }`；固定渲染 `slot_1..slot_5`，登录用户读写云存档，访客显示不可云存档提示 |

### 5.4 资源（`public/assets/`）

| 文件 | 用途 |
| --- | --- |
| `ink_mountain_gate.png` | 首页 / 登录页 / 角色页背景 |
| `paper_texture.png` | body 背景（720px auto 重复） |
| `ascension_gate.png` | 终局页背景（与游戏页区分） |
| `qq_group.png` | 首页玩家群二维码 |
| `audio/bgm.flac` | 背景音乐 |

## 6. 数据库 Schema 总览

共 **17 张应用表**（不含 Alembic 自身的 `alembic_version`），分 5 类。当前字段类型以 PostgreSQL `text` / `jsonb` / `double precision` / `timestamptz` 为主：大量 `text` 字段不是性能瓶颈，`varchar(n)` 只在需要业务长度约束时才有治理价值。

### 身份 / 会话（4 张）

- `users(id PK, username UNIQUE, password_hash, is_admin, created_at, updated_at)`
- `invite_codes(id PK, code_hash UNIQUE, role, max_uses, uses, expires_at, disabled, created_at, created_by)`
- `sessions(id PK, user_id FK, title, snapshot JSONB, events JSONB, created_at, updated_at)` — 当前 WebRunner 状态（仅账号局）
- `saves(id PK, user_id FK, name, snapshot JSONB, events JSONB, created_at, updated_at, UNIQUE(user_id, name))` — 手动存档

### 模型配置（2 张）

- `model_config(id PK CHECK id=1, provider, base_url, model, api_key_masked, api_key_set, api_key_encrypted, updated_at)` — 系统默认模型配置单例
- `user_model_configs(user_id PK/FK ON DELETE CASCADE, provider, base_url, model, api_key_masked, api_key_set, api_key_encrypted, updated_at)` — 注册用户个人模型配置

### 目录（5 张）

- `catalog_talents`、`catalog_family_backgrounds`、`catalog_spirit_roots`、`catalog_difficulties`、`catalog_story_seeds`

JSONB 列：`attribute_mods` / `tags` / `initial_resources` / `initial_risks` / `story_tags` / `event_tags`（双后端均通过 `load_json` 解码）

### 死亡奖励（3 张）

- `run_achievements(user_id, session_id, achievement_key, achievement_name, description, death_cause, achieved_at)`
- `account_rewards(user_id, reward_type, reward_value, label, source_session_id, granted_at)`
- `legacy_bonuses(user_id, bonus_type, bonus_value, label, runs_remaining, source_session_id, granted_at)` — 跨局传承，下局开局消费

### v5 回合遥测（3 张）

- `game_runs(id PK, user_id, session_id, char_name, realm, death_cause, ascended, turn_count, finished_at)`
- `game_turns(id PK, run_id, turn_no, start_age, elapsed_years, end_age, lifespan, remaining_lifespan, choice_taken, choices JSONB, state_delta JSONB, state_after JSONB, calendar_summary, narrative, event_kind, end_reason, created_at, UNIQUE(run_id, turn_no))`
- `player_progress(user_id PK, runs_completed, ascension_count, updated_at)`

结构判断：

- `users` → `sessions` / `saves` / `user_model_configs` / reward / progress 的用户隔离关系合理；个人模型配置用 `ON DELETE CASCADE`，符合“用户删除后清除个人密文配置”的语义。
- `model_config` 保持 `id = 1` 单例，作为系统默认 Agens 兜底；用户接口不共用该行。
- `game_turns.run_id` 当前是“回合分组 ID”，运行时等于 `session_id`，用于局中连续回合遥测；`game_runs` 是终局汇总/进度表，不是活跃 run 主表，所以当前不应把 `game_turns.run_id` 直接加外键到 `game_runs(id)`，否则可能阻断局中回合写入。后续若要强关系，应先把字段重命名为 `session_id`，或新增活跃 run 主表后再迁移。
- 后续性能治理优先看真实慢查询和 `EXPLAIN ANALYZE`；比起把 `text` 改成 `varchar`，更值得评估的是 `saves(user_id, updated_at DESC)`、`sessions(user_id, updated_at DESC)`、`run_achievements(user_id, session_id)`、`account_rewards(user_id, granted_at DESC)`、`legacy_bonuses(user_id, runs_remaining, granted_at)` 等查询索引。
- `created_at` / `updated_at` 多数仍是 Unix epoch `double precision`，这是历史兼容选择；若以后统一为 `timestamptz`，应单独规划迁移，不和玩法改动混做。

### Alembic 迁移（`migrations/versions/`）

| 版本 | 作用 |
| --- | --- |
| `20260621_0001_initial_web_pg.py` | 身份 + 5 catalog + 3 reward 表 |
| `20260621_0002_catalog_rewards_bridge.py` | 桥接老 DB；CREATE TABLE IF NOT EXISTS；downgrade 是 no-op |
| `20260622_0003_game_mode_v5_runs_turns_progress.py` | 新增 `game_runs` / `game_turns` / `player_progress` |
| `20260622_0004_ddl_disallow_production.py` | **no-op 策略迁移**；标记生产 schema 由 Alembic 拥有；`down_revision = "20260622_0003"` |
| `20260622_0005_user_model_configs.py` | 新增用户级加密模型配置表；系统默认配置增加 `api_key_encrypted` |
| `20260704_0006_attribute_scale_cleanup.py` | 归一化 catalog 属性修正到 0-10 属性尺度 |
| `20260705_0007_schema_comments.py` | 为表和字段补 PostgreSQL 中文注释，不改变业务结构 |

### DDL 治理

- **本地 / 测试**：PostgreSQL 默认 `AGENS_PG_AUTO_DDL=1` 时允许应用启动时建表
- **生产**：`AGENS_ENV=production` 下拒绝 `AGENS_PG_AUTO_DDL=1`（fail-closed `RuntimeError`）；schema 必须由 Alembic 迁移创建；catalog 与死亡奖励表也必须由迁移覆盖

## 7. 模块串联流程（端到端）

### 7.1 创建会话

```text
浏览器 main.tsx
  → POST /api/sessions {title: "新局"}
  → app.py 路由
  → WebGameService.create_session(user_id, title, guest_token)
  → 账号：WebRunner(session_id=uuid, user_id) + db.save_session()
  → 访客：create_guest_token() → Set-Cookie agens_guest=<token>
       + WebRunner(session_id=uuid, user_id="guest:<uuid>")，内存态不落库
  → 返回 Session
  → 前端 setSession → setView("character")
```

### 7.2 角色创建 → 开局

```text
CharacterCreatePage
  → GET /api/catalog/{talents|spirit_roots|family_backgrounds|difficulties}
  → 用户填表 / 随机 → POST /api/sessions/{id}/start {char_name, talent, spirit_root, family_background, difficulty, attributes, ...}
  → WebGameService.start_session()
     ① 账号：consume legacy_bonuses（如有）
     ② engine.start_from_profile(profile)
        ├─ GameSession.reset() + 写入 character/world
        ├─ build_world_prompt() / World Builder（env-gated）
        ├─ build_world_fallback() 在未开模型或模型失败时生成差异化本地开局
        ├─ apply_profile_opening_payload() 一次性写入 world_profile / lore_facts / current_scene
        └─ complete_choices() 保持 4 个 A/B/C/D
     ③ 触发回调 on_narrative / on_status_bar / on_character_created
  → WebRunner 记录事件 → 返回 Session（含 choices）
  → 前端 setView("game")
```

### 7.3 一回合（A/B/C/D → 结算）

```text
GamePage 点击 A/B/C/D
  → POST /api/sessions/{id}/choice {choice_index}
  → WebGameService.choose()
  → engine.handle_action(action_text)
     ① 校验 game_started / game_over
     ② 若 local_story_active：advance_local_story 推进（不调 LLM）
     ③ 解析 breakthrough 关键字 → attempt_breakthrough()
     ④ 否则 turn_count += 1
     ⑤ turn_rules.settle_turn(choice_text, session)
        ├─ classify_choice：A/B/C/D 映射稳妥/机遇/风险/气运
        ├─ 按境界抽 elapsed_years（× 风险系数 × 难度系数）
        ├─ 按类别抽属性增量
        └─ 寿元扣减；≤0 且非飞升 → meta.game_over=True
     ⑥ Narrator Agent：turn_summary 注入 prompt → LLM → narrative + state_delta + choices
     ⑦ Judge Agent：审核 state_delta → approved/corrected_delta
     ⑧ apply_delta(state_delta)：写入 GameSession
     ⑨ RealmSystem.try_advance_stage：小层自动升
     ⑩ 大境界突破判定（成功率 + 灵根加成）
     ⑪ 终局判定（飞升 / 寿元 / 走火入魔）
     ⑫ _record_settled_turn（仅账号局写 game_turns）
     ⑬ _persist（仅账号局写 sessions）
  → WebRunner.record(...) 捕获回调事件
  → 返回 Session
  → 前端 runTurn：若 game_over || finale → view="ending"；否则 view="game"
```

### 7.4 终局

```text
EndingPage mount
  → GET /api/sessions/{id}/death_summary
  → WebGameService.death_summary()
     ├─ 账号：从 DB 查 run_achievements + account_rewards（按 source_session_id 聚合）
     └─ 访客：runner 内存 build_death_summary() 实时构建
  → 返回 {session_id, is_guest, summary: {death_cause, achievements[], rewards[], headline, final_realm}}
  → 渲染"飞升"（finale）或"本局结束"（game_over）+ 侧栏摘要 + 最近 6 条叙事
```

### 7.5 存档 / 读档（仅账号）

```text
顶栏"存档"按钮
  → SettingsSaveDialog 弹窗（mode=saves）
  → GET /api/saves 列出 slot_1..slot_5
  → 保存：POST /api/sessions/{id}/save {name}
     → service.save() → db.save_game_slot(user_id, name, snapshot, events)
     → 返回 {save: SaveRow, session: Session}
  → 读档：POST /api/sessions/{id}/load {name}
     → service.load() → db.load_save() → WebRunner.from_snapshot()
     → 替换 self.runners[session_id]
     → 若 game_over||finale → view="ending"；否则 view="game"
```

### 7.6 模型不可用兜底

```text
Narrator / Judge LLMError
  → engine._set_choices() 触发 on_model_failure_choice 回调
  → WebRunner._choose_model_failure() 返回 MODEL_FAILURE_CONTINUE
  → 事件流写入 model_failure + fallback_prompt.active=True
  → 前端 GamePage 顶部出现 <FallbackBanner>
  → 用户可选"继续本局"（POST /action {action:"继续本局"}）→ engine._enter_local_story()
     或"结束本局"（POST /end {reason}）→ engine.on_game_over() 触发奖励判定
```

## 8. 关键约束（沿用 CLAUDE.md）

- **Web 前端只通过 API 调用游戏逻辑** — 不得直接修改 `GameSession`
- **`GameEngine` 是唯一游戏逻辑入口** — 所有状态变更必须经过 `apply_delta()`
- **API key 不进入前端包、日志、文档或 Git** — 仅进入后端进程环境变量与 DB 脱敏摘要
- **不在 UI 明示隐藏触发规则或内部模式名称** — 只展示玩家可理解的 A/B/C/D 选择和当前局面
- **访客 cookie（HttpOnly）是访客局唯一操作凭证** — 配合 `guest_token` 在后端校验
- **AGENS_ENV=production 下拒绝 `AGENS_PG_AUTO_DDL=1`** — 生产 schema 由 Alembic 拥有
- **9 境界顺序固定**：练气 → 筑基 → 金丹 → 元婴 → 化神 → 合体 → 大乘 → 渡劫 → 飞升，不回退、不恢复已删除项
- **生产模式隐藏 `/docs`、`/redoc`、`/openapi.json`**，启用 Host 白名单
- **状态变更 API 需同源 / 允许来源校验**（`enforce_same_origin`）

## 9. 验证入口

```powershell
# 后端编译 + 全部测试
.\.venv\Scripts\python.exe -m compileall -q src tests web
$env:TEST_DATABASE_URL = "postgresql+psycopg://agens_test@127.0.0.1:55432/agens_web_test"
.\.venv\Scripts\python.exe -m pytest -q

# 仅 Web 测试
.\.venv\Scripts\python.exe -m pytest -q tests\web

# 前端构建
cd d:\chat\agens-web\web\frontend-react
npm run build
```

## 10. 相关文档

- [RUNTIME_FLOW.md](RUNTIME_FLOW.md) — 当前运行链路（流程视角）
- [GAME_MODE_SPEC.md](GAME_MODE_SPEC.md) — 游戏模式 v5 产品 + 技术规格
- [PROJECT_AUDIT.md](PROJECT_AUDIT.md) — 结构边界 + 技术债
- [Project audit](PROJECT_AUDIT.md) — 当前结构边界、已清理内容和剩余风险
- [USER_TUTORIAL.md](USER_TUTORIAL.md) — 中文玩家入门指南

## 2026-06-28 Model Settings Architecture

- `model_config` remains the singleton system default. It stores provider/base URL/model, masked key state, and encrypted key material.
- `user_model_configs` stores one encrypted personal model config per `user_id` with `ON DELETE CASCADE` isolation.
- `MODEL_CONFIG_SECRET` derives the application-layer encryption key. Missing secret while decrypting stored keys fails closed, so runtime does not fall back to another user's key or a process-global key.
- Frontend settings are available to logged-in ordinary users. Admin-only system default management uses the separate `/api/admin/settings/model` API.
