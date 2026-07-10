# 项目文档索引

本仓库是 Web-only 项目：React/Vite + FastAPI + PostgreSQL。移动端、旧 CLI/REPL 和旧 SQLite 不属于当前维护范围。

## 当前事实

- 游戏模式 v5 Alpha，A/B/C/D 固定语义，无自由文本主入口，无 HP/MP。
- PostgreSQL-only，Alembic head `20260710_0008_runtime_consistency`。
- 用户个人模型配置 + 系统默认兜底，Key 加密存储且不回显。
- 模型 Base URL 使用 HTTPS 官方域名/服务器 allowlist，并在请求前做公网 DNS 校验。
- 访客 session 写入 PostgreSQL，默认 24 小时；登录/注册后删除访客局。
- mutation API 强制 request ID + version，使用锁、CAS、幂等记录和事务提交。
- Agent 编排是项目内 `SequentialAgentGraph`，不是 LangGraph。
- fallback 自动切换本地故事，但不能算 live-model 成功。
- 本轮仅本地代码与自动化验证；生产未部署、未复验。

## Source Of Truth

| 文档 | 用途 |
| --- | --- |
| `README.md` | 项目入口、安装、启动和验证 |
| `AGENTS.md` / `CLAUDE.md` | 仓库执行约束 |
| `docs/GAME_MODE_SPEC.md` | 玩法规则 source of truth |
| `docs/RUNTIME_FLOW.md` | 当前端到端运行链路 |
| `docs/ARCHITECTURE.md` | 模块、依赖和 schema 边界 |
| `docs/security.md` | 安全与部署边界 |
| `docs/PROJECT_AUDIT.md` | 当前审计结论和剩余风险 |
| `docs/NEXT_GOVERNANCE_BACKLOG.md` | 仅当前未完成项 |
| `docs/USER_TUTORIAL.md` | 玩家操作说明 |
| `docs/PRODUCTION_V5_MIGRATION_CHECKLIST.md` | 生产迁移/验收清单 |
| `CHANGELOG.md` | 历史变更与旧证据 |

## 阅读顺序

1. 开发/启动：`README.md` -> `docs/RUNTIME_FLOW.md`
2. 玩法：`docs/GAME_MODE_SPEC.md` -> `docs/USER_TUTORIAL.md`
3. 架构/治理：`docs/ARCHITECTURE.md` -> `docs/PROJECT_AUDIT.md` -> `docs/NEXT_GOVERNANCE_BACKLOG.md`
4. 安全/生产：`docs/security.md` -> `docs/PRODUCTION_V5_MIGRATION_CHECKLIST.md`

## 验证原则

- `tests\web` 会清空其 `TEST_DATABASE_URL`；不要与真实浏览器共享数据库并发运行。
- 默认 pytest 排除 `llm_real`；真实模型验收单独执行。
- 本地自动化不等于生产验收。
- HTTP 200 不等于模型成功；fallback 状态一律视为 live-model 失败。
- 生成证据不写入仓库。旧 `output/` 已归档到 `D:\chat\agens-web-artifacts\20260710`。
