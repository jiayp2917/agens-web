# Project Audit

## Scope

本文件只记录当前本地工作树在 2026-07-22 的可复核状态。它不复述历史服务器操作、旧 fingerprint
的性能数字或过期测试计数。本轮没有连接、修改或验证生产环境；本地通过不能构成部署或公开发布结论。

## Current Architecture

- 前端：React 18、Vite、TypeScript、Vitest/RTL。
- API：FastAPI，按 auth/catalog/session/settings 路由拆分。
- 游戏：`GameEngine` 门面，StartFlow、TurnFlow、BreakthroughFlow 和 fallback policy 分工。
- Agent：项目内 `SequentialAgentGraph`，不是 LangGraph。
- 数据：PostgreSQL-only；Alembic head 是 `20260721_0009_spirit_root_metadata`。
- 内容：v1 为 60 回合旧档兼容，v2 为默认九阶段 90 回合；v3 已实现但默认未切换。

## Closed Local Findings

### Security And Persistence

- 用户模型 URL 在保存和请求前通过同一 HTTPS、allowlist、DNS/IP、无重定向和无环境代理校验；非公网地址 fail closed。
- 用户和系统模型 Key 使用 `MODEL_CONFIG_SECRET` 派生的 Fernet 密文。响应、日志、session、存档和回合记录只保留脱敏状态；用户 Key 不写入 `os.environ`。
- 访客 session 使用 PostgreSQL token hash 与 TTL；登录/注册后删除访客局。写请求通过会话锁、CAS、幂等记录和单一事务提交 session、turn、run、奖励、进度与遗泽。
- 迁移 `20260710_0008_runtime_consistency` 对无法关联的历史 turn fail closed；`20260721_0009_spirit_root_metadata` 为灵根 catalog 增加展示 metadata，不修改会话或玩法数据。

### Rule Authority And Content

- 规则引擎拥有年龄、寿元、境界、伤势、死亡、奖励、终局和 A/B/C/D 槽位语义。模型只表达叙事和固定槽位选项，不能改变权威结果。
- Judge `approved` 只接受 JSON bool；突破、飞升和死亡先记录叙事/turn history，再结算终局。`GameSession.error` 随存档保存和恢复。
- Narrator 使用 `NarratorEnvelopeV1(narrative, choices)`；`state_update` 仅保留为兼容诊断，不参与权威状态或 strict 结果。World Builder 和 Judge 使用各自版本化 envelope。
- v3 为每局生成两条命数承诺，包含九阶段事件、最近五项 motif 去重、路线后果以及主线在第 90 回合后的 `post_arc`。v1/v2 按精确版本读取，v3 仍不是默认内容。
- 本地 fallback 开场已修复“牵动，其”和“生于魔道遗孤”等已知模板拼接问题；fallback 回合调用 `settle_turn()`，会同步推进年龄、寿元和主线状态。

### Provider Evaluation Boundary

- 评估使用只读 resolver、私有运行时凭据上下文和 transport adapter；Key 不进入环境复制、数据库、session、Agent 可序列化 state、日志或证据。
- 评估模式必须使用仓库外 `AGENS_ARTIFACT_ROOT`。ArtifactSink 只写脱敏响应副本、manifest/hash、调用/延迟/token/费用指标，禁止 prompt、Key、Cookie、Authorization、真实 Base URL 和玩家数据；产品路径不双写 `runtime/artifacts` 或 `output/playwright`。
- `AGENS_ENV=prod|production` 下拒绝评估模式。真实模型测试必须标为 `llm_real`，fallback、repair 和 contract recovery 不能计为 strict 成功。

## Current Local Verification

### Static, Database And Frontend Gates

- `python -m compileall -q src tests web scripts migrations`：通过。
- Ruff 常规检查和 `--select C901`：均通过。
- `mypy src web\\backend`：93 个 source files，0 errors。
- PostgreSQL `tests\\web -n0`：95 passed，1 warning（第三方 Starlette TestClient 弃用提示）。
- `pytest -q -m "not llm_real"`：863 passed，16 warnings（同一第三方弃用提示）。
- Vitest：8 files、13 tests passed；React production build 通过；`npm audit --audit-level=high` 为 0 vulnerabilities。

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
