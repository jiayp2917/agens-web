# 项目架构

## 1. 总览

`agens-web` 是 Web-only 文字修仙游戏：

```text
React/Vite
  -> FastAPI routers
  -> WebGameService / WebRunner
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
| 服务 | `web/backend/service*.py` | runner 生命周期、事务编排、模型配置解析、奖励摘要 |
| 游戏门面 | `src/agens_novel/engine/game_engine.py` | 对外稳定入口和回调协议 |
| 流程 | `start_flow.py`、`turn_flow.py`、`breakthrough_flow.py` | 按玩家路径组织开局、普通回合和突破 |
| 规则/状态 | `turn_rules.py`、`realm.py`、`game_session.py` | 权威数值、境界、寿元、delta 应用和存档 |
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
| `turn_rules.py` | A/B/C/D 类别、时间、属性、寿元、事件、终局规则 |
| `action_delta_policy.py` | 模型 delta 清洗、叙事/落账一致性、规则字段覆盖 |
| `game_session.py` | 权威状态、delta 分区应用、存档序列化 |

Judge 的 `approved` 只接受 JSON 布尔值。突破结果、age、lifespan、game_over、finale 等规则字段不接受模型覆盖。

## 6. Agent 与模型客户端

三个 Agent 使用 `SequentialAgentGraph` 顺序执行 load settings、build prompt、call LLM、save artifact。

- World Builder：本局世界、0-16 岁编年史、16 岁局势和初始 A/B/C/D。
- Narrator：短编年史、候选 delta 和下一回合选项。
- Judge：只审核高风险或连续性敏感的非规则变化。

`llm/client.py` 使用 `httpx.AsyncClient`：

- `follow_redirects=False`
- `trust_env=False`
- 408/429/5xx 可重试
- `AGNES_TOTAL_TIMEOUT_SECONDS` 整体时限
- asyncio 取消自然传播
- 保存配置和请求前共用 `llm/url_security.py` SSRF 校验

## 7. 模型配置

| 表 | 所有者 | 用途 |
| --- | --- | --- |
| `model_config` | 管理员 | 系统 Agens 默认 |
| `user_model_configs` | 单个注册用户 | 个人 provider/base URL/model/加密 Key |

Key 由 `MODEL_CONFIG_SECRET` 派生的 Fernet 密钥加密。响应只返回 masked 状态。缺少或错误 secret 时 fail closed，不退回密文、其他用户 Key 或进程全局用户 Key。

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
- PostgreSQL 只通过内部网络访问。

## 11. 已删除内容

- 旧 SQLite 后端和旧自由文本玩法；
- 应用副本启动时自动迁移的 entrypoint；
- 不安全的 `scripts/run_with_key.ps1`；
- 未引用的 `ascension_gate.png`；
- 仓库内 `output/`，已移到 `D:\chat\agens-web-artifacts\20260710` 并生成 SHA-256 清单。
