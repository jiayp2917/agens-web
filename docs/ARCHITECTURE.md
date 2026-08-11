# 项目架构

当前本机定版范围为 `story_version=2`。2026-08-11 已通过当前系统默认模型的普通 Web 严格流程；
这只证明本机 v2 链路，不证明 v3、其他模型或生产部署。

## 1. 总览

`agens-web` 是 Web-only 文字修仙游戏：

```text
React/Vite
  -> FastAPI routers
  -> WebGameService (session/turn/save use cases) / WebRunner
  -> GameEngine facade
  -> StartFlow / TurnFlow / BreakthroughFlow / ModelFallbackPolicy
  -> SequentialAgentGraph (World Builder / Narrator / Judge)
  -> GameSession + RealmSystem
  -> PostgreSQL / Alembic
```

项目不使用 LangGraph。Agent 编排由项目内 `SequentialAgentGraph` 兼容层完成。

## 2. 分层约束

| 层 | 路径 | 职责 |
| --- | --- | --- |
| 前端 | `web/frontend-react/src/` | 页面、交互、请求版本、幂等 ID、弹窗与响应式布局 |
| API | `web/backend/router_*.py` | Pydantic 输入、鉴权、Cookie、限流、异常到 HTTP 映射 |
| 服务 | `web/backend/service.py`、`service_sessions.py`、`service_turns.py`、`service_saves.py` | runner 生命周期、事务编排、模型配置解析、会话/回合/存读档用例 |
| 游戏门面 | `src/agens_novel/engine/game_engine.py` | 对外稳定入口和回调协议 |
| 流程 | `start_flow.py`、`turn_flow.py`、`breakthrough_flow.py` | 按玩家路径组织开局、普通回合和突破 |
| 规则/状态 | `turn_rules.py`、`realm.py`、`spirit_roots.py`、`game_session.py`、`state_delta.py` | 权威数值、境界、寿元、灵根注册、delta 应用和存档 |
| Agent | `src/agens_novel/agents/` | prompt、模型调用、输出解析和脱敏诊断 |
| 数据 | `database_postgres.py`、`migrations/` | PostgreSQL 事务、CAS、幂等和 schema |

依赖只能沿表格向下。前端不得直接写 `GameSession`，Agent 输出不得绕过规则层直接成为权威状态。

## 3. FastAPI

`app.py` 只负责：

- 创建 FastAPI 应用；
- 校验生产必需配置；
- 安装 Host、body-size、同源和异常处理；
- 注册 routers；
- 挂载前端静态文件；
- 提供带 PostgreSQL ping 的 `/api/health`。

路由模块：

| 模块 | 端点 |
| --- | --- |
| `router_auth.py` | 注册、登录、退出、当前用户、邀请码 |
| `router_catalog.py` | 天赋、灵根、家世、难度、故事 catalog |
| `router_sessions.py` | session、start、choice、action、save、load、end、终局摘要 |
| `router_settings.py` | 用户个人模型设置、管理员系统默认设置 |

`app_dependencies.py` 提供 current user/admin、session owner、rate limit 和统一 service exception 映射。

`WebGameService` 保持路由依赖的稳定门面。`service_sessions.py`、`service_turns.py` 和
`service_saves.py` 分别承接会话生命周期、回合与存读档用例。模型配置只由普通
`ModelConfigService` 在调用前解析；产品和本地验证不再存在第二个应用工厂或评估配置链。

## 4. 会话一致性

`WebRunner` 持有一个 `GameEngine`、事件列表、当前 version 和访客 token。内存 runner 是执行缓存，PostgreSQL session snapshot 才是跨进程恢复来源。

所有状态变更请求包含：

```json
{
  "request_id": "client-generated-uuid",
  "expected_version": 3
}
```

服务端一致性层：

1. 每 session 一个 `RLock`，阻止单进程并发修改。
2. `session_mutations(session_id, request_id)` 保存原始成功结果。
3. `sessions.version` 做数据库 CAS；过期版本映射为 HTTP 409。
4. 内存 runner 在事务失败时从 rollback snapshot 恢复。
5. session snapshot、game_turn、run、奖励、遗泽和 save slot 由 `commit_session_mutation()` 原子提交。

## 5. 游戏核心

`GameEngine` 保留稳定 public 方法：

- `new_game()`
- `start_from_profile()`
- `handle_action()`
- `attempt_breakthrough()`

职责拆分：

| 模块 | 职责 |
| --- | --- |
| `start_flow.py` | profile 校验、动态开局、World Builder、profile-aware fallback |
| `turn_flow.py` | 普通回合、本地故事、Narrator/Judge、记录与选项提交 |
| `breakthrough_flow.py` | 规则突破、叙事、Judge 非权威修正、终局回调 |
| `model_fallback_policy.py` | 失败决策、脱敏玩家提示 |
| `turn_rules.py` | A/B/C/D 类别、时间、属性、寿元、事件、长期剧情和终局规则 |
| `event_catalog.py` | 数据驱动编年史事件、阶段目标、选项提示和允许 delta 类型 |
| `story_catalog.py` / `story_catalog_data.py` | 统一查询门面和四套世界的版本化主线数据：v1 60 回合兼容、v2 九阶段 90 回合、v3 承诺、路线后果和 post-arc |
| `rule_contracts.py` | `ChoiceIntentV1` 与 `RuleTurnOutcomeV1` 的规则权威边界 |
| `action_delta_policy.py` | 兼容模型 delta 的诊断清洗、叙事/落账一致性守卫 |
| `game_session.py` / `state_delta.py` | 权威状态门面、delta 分区应用、存档序列化 |

Judge 的 `approved` 只接受 JSON 布尔值。突破结果、age、lifespan、game_over、finale 和 `story_update` 等规则字段不接受模型覆盖。Session/存档保存 `story_key`、`story_version` 和可变 `story_state`，不会复制不可变剧情定义，也不会静默升级旧存档。

## 6. Agent 与模型客户端

三个 Agent 使用 `SequentialAgentGraph` 顺序执行 load settings、build prompt、call LLM、save artifact。
普通回合的权威顺序是 `ChoiceIntentV1 -> RuleTurnOutcomeV1 -> NarratorEnvelopeV1 -> persistence`；
Agent 不拥有状态结算权。

- World Builder：本局世界、0-16 岁编年史、16 岁局势和初始 A/B/C/D。
- Narrator：短编年史和下一回合四项选项。内部统一为 `NarratorEnvelopeV1(narrative, choices)`；Agens 可用 JSON Schema，DeepSeek 可用已探测的 JSON object 或兼容标签。旧 `state_update` 可被 parser 读取作诊断，但不会进入规则或持久化权威状态。
- World Builder：内部为 `WorldOpeningEnvelopeV1`；它只提供开场表现，世界/剧情绑定仍由规则目录校验。
- Judge：内部为 `JudgeDecisionV1`；只审核高风险或连续性敏感的非规则表现，不能改变规则结果。

`llm/client.py` 使用 `httpx.AsyncClient`：

- `follow_redirects=False`
- `trust_env=True`，继承标准 `HTTP_PROXY`、`HTTPS_PROXY` 和 `NO_PROXY`
- 408/429/5xx 可重试
- `AGNES_TOTAL_TIMEOUT_SECONDS` 整体时限
- asyncio 取消自然传播
- 保存配置和请求前共用 `llm/url_security.py` SSRF 校验

Narrator 请求成功但正文或四项选项不完整时，TurnFlow 可用规则结果和本地主线选项维持游戏，但该路径记录为 `contract_recovery`，与 provider fallback 分开，不能计入严格 live 验收。兼容 parser 可以读取裸 JSON 或行式选项；严格分类要求归一化后的 envelope 完整、四槽唯一、无可见英文或结构残留，而不强迫所有 provider 使用相同 wire format。模型历史投影为 `AcceptedTurnContextV1`，只保存已接受正文、选项和规则后果摘要。

确定性场景和权威回放位于 `src/agens_novel/verification/`，用于普通本地验证，不装配模型配置或发起模型调用。本地浏览器验收的 CLI 仍由 `scripts/local_visible_playtest.cjs` 提供，并通过普通 Web API 运行。浏览器驱动、持久化回合审计、玩家可见内容审计、报告构造和最终裁决分别位于 `scripts/playtest/`；运行产物只允许在系统临时目录或显式指定的仓库外目录中出现。

## 7. 模型配置

| 表 | 所有者 | 用途 |
| --- | --- | --- |
| `model_config` | 管理员 | 系统 Agens 默认 |
| `user_model_configs` | 单个注册用户 | 个人 provider/base URL/model/加密 Key |

Key 由 `MODEL_CONFIG_SECRET` 派生的 Fernet 密钥加密。响应只返回 masked 状态。本机系统环境 Key 是直接来源；仅当环境 Key 缺失且数据库密文无法解密时 fail closed，不退回密文或其他用户 Key。

## 8. PostgreSQL Schema

当前 18 张应用表：

- 身份：`users`、`invite_codes`
- 会话：`sessions`、`session_mutations`、`saves`
- 模型：`model_config`、`user_model_configs`
- catalog：5 张 catalog 表
- 运行与奖励：`game_runs`、`game_turns`、`player_progress`、`run_achievements`、`account_rewards`、`legacy_bonuses`

`20260710_0008_runtime_consistency` 增加：

- session version、访客 token hash、过期时间和 nullable user owner；
- active/completed game run；
- `game_turns.run_id` 外键与 request 唯一约束；
- session mutation 幂等表；
- 奖励、成就、遗泽业务唯一约束。

`20260721_0009_spirit_root_metadata` 为灵根 catalog 增加 `rarity` 与 `description`，供现有角色创建界面展示；不改变用户会话或游戏规则数据。

读旧档通过 session mutation 事务回退当前 active run：删除存档回合之后的 `game_turns`，同步 run 摘要，再写 snapshot 和幂等结果。已完成终局拒绝原地回退，避免奖励与历史不一致。

测试 auto-DDL 只用于本地测试。`AGENS_ENV=prod|production` 时禁止 `AGENS_PG_AUTO_DDL=1`。

## 9. 前端

`main.tsx` 持有 user、session、view 和 dialog 状态。`api/client.ts` 定义 Session/Character/World/Event DTO，并负责凭据请求。

关键交互：

- 每次 mutation 生成 UUID，并携带当前 session version。
- 同步 ref 阻止双击在 React state 更新前重复提交。
- HTTP 409 后重新读取权威 session。
- 登录/注册成功清除前端访客 session。
- fallback banner 无“继续本局”死按钮，玩家直接选择 A/B/C/D。
- 弹窗使用 focus trap；Vitest/RTL 覆盖认证回调、fallback、双击和焦点限制。

## 10. 部署

`uv.lock` 锁定 Python 依赖。Docker 多阶段构建前端和 Python 环境，最终镜像以 UID/GID 10001 运行。

Compose：

- `agens-web-migrate` 一次性执行 Alembic；
- 应用等待 migration 成功；
- read-only root、cap drop、no-new-privileges、tmpfs、CPU/内存/PID 限制；
- PostgreSQL、Redis 与 Squid 只通过内部网络访问，不发布宿主机端口；
- 生产 `RateLimiter` 使用 Redis 原子滑动窗口，两个应用实例共享计数，Redis 故障时敏感写请求 fail closed 为 503；
- LLM 客户端继承标准 `HTTP_PROXY`、`HTTPS_PROXY` 和 `NO_PROXY`，保持 `follow_redirects=False`；部署若使用 Squid，通过这些标准变量配置，而非应用专用代理变量。
- `deploy/apply-egress-acl.sh` 是独立的部署网络控制；本地代码不依赖其存在，也不通过它选择模型配置。

主机部署顺序是安全边界的一部分：必须先解析依赖地址、完整写入应用专用链并将其插入 `DOCKER-USER` 首位，最后才启用 `net.bridge.bridge-nf-call-iptables=1`。运行 Docker 容器的主机不得通过卸载 `br_netfilter` 恢复状态，因为它可能连带移除 `bridge` 模块并使 Docker 网络对象与内核 bridge 设备失去一致性；恢复只能保留模块并按已记录值调整 sysctl。

本地迁移门禁在唯一的本机 `DATABASE_URL` 中重建 `public` schema，验证 0007 已有数据升级、孤儿/重复数据 fail-closed、0008 downgrade/re-upgrade 和 downgrade 阻塞条件。`scripts/verify_pg_backup_restore.py` 使用同一数据库完成 `pg_dump`、清库和 `pg_restore`，验证 head、18 张表和数据标记，结束时恢复 Alembic head。

## 11. 已删除内容

- 旧 SQLite 后端和旧自由文本玩法；
- 应用副本启动时自动迁移的 entrypoint；
- 不安全的 `scripts/run_with_key.ps1`；
- 未引用的 `ascension_gate.png`；
- 仓库内 `output/`，已移到 `D:\chat\agens-web-artifacts\20260710` 并生成 SHA-256 清单。
