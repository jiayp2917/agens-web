# 项目文档索引

本仓库是 Web-only 项目：React/Vite + FastAPI + PostgreSQL。移动端、旧 CLI/REPL 和旧 SQLite 不属于当前维护范围。

## 当前事实

- 游戏模式 v5 Alpha，A/B/C/D 固定语义，无自由文本主入口，无 HP/MP。
- PostgreSQL-only，Alembic head `20260721_0009_spirit_root_metadata`。
- 用户个人模型配置 + 系统默认兜底，Key 加密存储且不回显。
- 模型 Base URL 使用 HTTPS 官方域名/服务器 allowlist，并在请求前做公网 DNS 校验。
- 访客 session 写入 PostgreSQL，默认 24 小时；登录/注册后删除访客局。
- mutation API 强制 request ID + version，使用锁、CAS、幂等记录和事务提交。
- Agent 编排是项目内 `SequentialAgentGraph`，不是 LangGraph。
- fallback 自动切换本地故事，但不能算 live-model 成功。
- 四套世界包保留 60 回合 v1 旧档兼容；新局默认绑定九阶段 90 回合 v2。v3 的九阶段、承诺、路线后果和 post-arc 已在本地实现，但尚未完成真实模型与浏览器完整局验收，默认版本不变。
- gameplay recovery 与 provider fallback 分开记录；Narrator 契约不完整不能计作 live-model 成功。
- Narrator 内部契约是正文加四选项；选择意图和规则结果才是权威状态，兼容 state update 仅作诊断。
- 本地双模型评估使用仓库外、脱敏的 `AGENS_ARTIFACT_ROOT`；生产拒绝 `AGENS_EVALUATION_MODE`。
- 生产形态包含内部 Redis 共享限流、Squid 受控出站代理和专用 egress ACL；本地纯单测仍可使用内存限流。
- 2026-07-14 服务器隔离与生产 Stage 1 曾验证上述形态，但 strict choice 因 Narrator 正文英文残留触发 fallback 而停止；2026-07-20 重启后只读复核确认 ACL、bridge filtering 和持久化服务均未恢复。当前运行健康不等于发布验收通过，v2、回滚演练、当前候选的 strict smoke 与 ACL 持久化均待完成。
- 当前本地验证结果、精确计数和 strict live 证据只在 `PROJECT_AUDIT.md` 维护。
- 本地工作树与生产状态分开；生产通过只接受服务器侧备份、部署、回滚和 strict smoke 的脱敏事实。

## Source Of Truth

| 文档 | 用途 |
| --- | --- |
| `README.md` | 项目入口、安装、启动和验证 |
| `AGENTS.md` / `CLAUDE.md` | 仓库执行约束 |
| `docs/plan.md` | 稳定的长期目标、不变量、里程碑状态和分层验收原则 |
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
3. 架构/治理：`docs/plan.md` -> `docs/ARCHITECTURE.md` -> `docs/PROJECT_AUDIT.md` -> `docs/NEXT_GOVERNANCE_BACKLOG.md`
4. 安全/生产：`docs/security.md` -> `docs/PRODUCTION_V5_MIGRATION_CHECKLIST.md`

## 验证原则

- `tests\web` 会清空其 `TEST_DATABASE_URL`；不要与真实浏览器共享数据库并发运行。
- 默认 pytest 排除 `llm_real`；真实模型验收单独执行。
- 本地自动化不等于生产验收。
- HTTP 200 不等于模型成功；fallback 或 contract recovery 都视为 live-model 失败。
- 浏览器脚本可把临时证据写入被 Git 忽略的 `output/playwright/`；普通提交不得包含这些产物，需要长期保留时移到仓库外 artifact 目录并保存清单。
