# Project Audit

## 2026-08-06 Local Runtime Verification

- `DATABASE_URL` now remains an explicit override, while local non-production commands resolve the established loopback PostgreSQL database by default. Production still fails closed without an explicit URL.
- The current local default was exercised through Alembic head, PostgreSQL Web tests, migration integration, backup/restore and a no-model guest-session API flow. The local HTTP Cookie default is now non-secure only outside production; production keeps the explicit secure-cookie requirement.
- The current verification completed without real model calls: `tests\\web -n0` passed 95 tests, the full non-`llm_real` suite passed 884 tests with 1 deselection, Vitest passed 18 tests, and the frontend build and high-severity audit passed.

## 2026-08-01 Unified Local Runtime Cleanup

- `ead9620` and `0c163e5` removed the dedicated evaluation runtime. Local development, tests and browser verification now use ordinary `web.backend.app` and PostgreSQL-first `ModelConfigService` resolution; the deleted evaluation variables no longer exist in active source, configuration or deployment examples.
- Standard proxy environment variables are inherited by HTTPX. HTTPS URL validation, redirect refusal, request timeouts, envelope validation, rule authority, v1/v2/v3 save compatibility and explicit player handling of model failures are unchanged.
- Targeted cleanup regressions, static checks, frontend tests/build/audit and skill-copy verification passed. The later 2026-08-06 entry records the completed local PostgreSQL, browser-home and backup/restore verification.
- 本机只保留一个 PostgreSQL 开发/测试数据库。显式 `DATABASE_URL` 可覆盖默认连接；测试允许清空其应用表或重建 `public` schema，并且必须与迁移、备份恢复和浏览器流程串行运行。

## Scope

本文件只记录当前本地工作树在 2026-08-01 的可复核状态。它不复述历史服务器操作、旧 fingerprint
的性能数字或过期测试计数。本轮没有连接、修改或验证生产环境；本地通过不能构成部署或公开发布结论。

## Current Architecture

- 前端：React 18、Vite、TypeScript、Vitest/RTL。
- API：FastAPI，按 auth/catalog/session/settings 路由拆分。
- 服务：`WebGameService` 保持 API 门面，session 生命周期、回合和存读档由独立 use-case 模块承接；模型调用前统一通过 `ModelConfigService` 解析当前配置。
- 游戏：`GameEngine` 门面，StartFlow、TurnFlow、BreakthroughFlow 和 fallback policy 分工。
- Agent：项目内 `SequentialAgentGraph`，不是 LangGraph。
- 数据：PostgreSQL-only；Alembic head 是 `20260721_0009_spirit_root_metadata`。
- 内容：v1 为 60 回合旧档兼容，v2 为默认九阶段 90 回合；v3 已实现但默认未切换。

## Closed Local Findings

### Security And Persistence

- 用户模型 URL 在保存和请求前通过同一 HTTPS、allowlist、DNS/IP 和无重定向校验；非公网地址 fail closed。HTTP 客户端只继承标准代理环境变量。
- 用户和系统模型 Key 使用 `MODEL_CONFIG_SECRET` 派生的 Fernet 密文。系统环境 Key 可在本机运行时直接使用，不会被无法解密的旧系统密文遮蔽。响应、日志、session、存档和回合记录只保留脱敏状态；用户 Key 不写入 `os.environ`。
- 访客 session 使用 PostgreSQL token hash 与 TTL；登录/注册后删除访客局。写请求通过会话锁、CAS、幂等记录和单一事务提交 session、turn、run、奖励、进度与遗泽。
- 迁移 `20260710_0008_runtime_consistency` 对无法关联的历史 turn fail closed；`20260721_0009_spirit_root_metadata` 为灵根 catalog 增加展示 metadata，不修改会话或玩法数据。

### Rule Authority And Content

- 规则引擎拥有年龄、寿元、境界、伤势、死亡、奖励、终局和 A/B/C/D 槽位语义。模型只表达叙事和固定槽位选项，不能改变权威结果。
- Judge `approved` 只接受 JSON bool；突破、飞升和死亡先记录叙事/turn history，再结算终局。`GameSession.error` 随存档保存和恢复。
- Narrator 使用 `NarratorEnvelopeV1(narrative, choices)`；`state_update` 仅保留为兼容诊断，不参与权威状态或 strict 结果。World Builder 和 Judge 使用各自版本化 envelope。
- v3 为每局生成两条命数承诺，包含九阶段事件、最近五项 motif 去重、路线后果以及主线在第 90 回合后的 `post_arc`。v1/v2 按精确版本读取，v3 仍不是默认内容。
- 玩家明确选择本地故事后的开场已修复“牵动，其”和“生于魔道遗孤”等已知模板拼接问题；本地故事回合调用 `settle_turn()`，会同步推进年龄、寿元和主线状态。

### Model Runtime Boundary

- `ModelConfigService` 优先读取 PostgreSQL 系统模型配置；数据库未配置时才使用系统或兼容 Agens 环境变量作为启动回退。Key 只在单次调用边界读取或解密，不进入 session、Agent 可序列化 state、数据库响应或日志。
- HTTPX 继承标准 `HTTP_PROXY`、`HTTPS_PROXY` 和 `NO_PROXY`，保持 HTTPS URL 校验、禁止重定向和整体时限。不存在专用模型代理变量、第二个应用、预算账本或证据根。
- 浏览器验证复用普通 Web API，临时脱敏汇总只能写入系统临时目录或显式仓库外目录。真实模型测试必须标为 `llm_real`，fallback、repair 和 contract recovery 不能计为 strict 成功。

### Governance Implementation

- `game/spirit_roots.py` 是灵根名称、品级、修炼/突破修正和展示 metadata 的唯一注册表；规则映射与 catalog 初始化从它生成。同步只追加缺失名称和补齐缺失 metadata，不删除或覆盖既有记录。前端在寿元字段合法时直接显示权威值。
- 产品与本地验证统一使用普通 `ModelConfigService` 和公开 Web API；已删除评估应用工厂、只读 resolver、账本和 ArtifactSink。目录结构、字符串工具和测试夹具也已移出跨层依赖点。
- 浏览器验收已拆为浏览器驱动、持久化回合审计、可见内容审计、报告构造和纯函数裁决；脱敏 replay fixture 锁定通过、失败、fallback、重复和状态冲突的退出码语义，未调用真实模型。
- 大型回归测试按 Web API 工作流、GameSession 状态/存档历史、开局/普通回合/破境失败路径和 Narrator prompt/解析/repair 分组。`scripts/verify_skill_copies.py` 只报告 `.claude/skills` 副本漂移，不修改开发者工作树。
- `requirements-dev.txt` 与确认过时的路线文档已删除。`Makefile` 和 `scripts/import_web_data_to_pg.py` 因缺少仓库外依赖确认而保留。

## Current Local Verification

### Static, Database And Frontend Gates

- `python -m compileall -q src tests web scripts migrations`：通过。
- Ruff 常规检查和 `--select C901`：均通过。
- `mypy src web\\backend`：113 个 source files，0 errors。
- PostgreSQL `tests\\web -n0`：96 passed，1 warning（第三方 Starlette TestClient 弃用提示）。
- `pytest -q -m "not llm_real"`：914 passed，16 warnings（同一第三方弃用提示）。
- Vitest：8 files、17 tests passed；React production build 通过；`npm audit --audit-level=high` 为 0 vulnerabilities。
- `scripts/verify_skill_copies.py`：6 组兼容副本无漂移；`verify_pg_backup_restore.py` 在隔离库完成 base-to-head 恢复，验证 18 张表、业务关系和 Alembic `20260721_0009`。

### Local Browser Slice

- 隔离 Chrome 的 390x844 fallback 局确认开场中文语法正常，A 选择后从 16 岁推进到 17 岁、寿元从 84 变为 83，A/B/C/D 可继续选择。
- 该切片故意不提供模型 Key，浏览器控制台有一个预期的 401 模型请求错误；它不能作为无错误 live-model 浏览器验收，也不能替代 v3 长局或移动端长文本完整验收。

### Provider Results And Stop Conditions

- Agens capability probe：7/7 strict，使用 `json_schema`。v2 20 回合 smoke：20/20 strict，fallback、repair 和 retry 均为 0。
- DeepSeek capability probe：6/7 strict；`json_schema` 不支持，adapter 使用 `json_object`。v2 smoke 在首回合后进入 fallback，仅 1/20 strict，已按预算和质量止损，不再发起该 provider 的真实调用。
- Agens v3 三局批处理在评估时限内未产生汇总，已停止且不计通过。当前没有双模型内容、稳定性、延迟或成本优劣结论，也不得报告模型能力百分比。

### Rule-Risk Matrix

无 LLM 的 200 种子矩阵覆盖 4 个世界、2 个难度、3 组资质和 A/C 路线，共 9,600 条。所有运行均收束：飞升 398、死亡 3,226、主线失败 1,289、主线成功 4,687、未收束 0。

- 高风险相对普通的负面结果差：`+24.625pp`，95% CI `+22.208pp` 至 `+26.875pp`。
- C 相对 A：`+44.688pp`，95% CI `+43.021pp` 至 `+46.438pp`。
- 低资质相对高资质：`+16.438pp`，95% CI `+13.625pp` 至 `+19.250pp`。

这证明规则方向与主线收束，不证明真实玩家的失败概率是否合适，也不评价模型叙事质量。

## Residual Risks

| Risk | Level | Current boundary |
| --- | --- | --- |
| DeepSeek strict smoke failed | P1 | Fix the DeepSeek adapter/prompt and pass a new 20-turn smoke before any paid v3 run. |
| Agens v3 full flows incomplete | P1 | Run bounded, independently stored complete flows and browser acceptance before changing the default story version. |
| Content evaluation incomplete | P1 | Complete frozen nine-snapshot blind review plus natural ascension, death/longevity and main-failure Chrome scenarios. |
| Live latency baseline absent for this worktree | P1 | Collect a current strict live baseline; `choice p50 <= 5s` remains an observation target, not a passed gate. |
| Mobile long-text acceptance incomplete | P1 | Run a separate 390x844 long chronicle and long A/B/C/D acceptance flow. |
| Production state not reverified | P1 | Deployment, Docker, backup, rollback, ACL and production strict smoke are explicitly outside this local batch. |

## Acceptance Boundary

- HTTP 200 is not live-model success.
- `fallback=true`, `fallback_prompt.active=true`, `contract_recovery=true`, visible structure residue or a non-`ok` Narrator result fail strict live acceptance.
- Browser, PostgreSQL and local model evaluation use independent databases/processes and must not run concurrently where tests truncate shared state.
- Local tests and local browser evidence do not authorize deployment, production database changes or a public-release claim.
