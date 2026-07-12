# Next Governance Backlog

本文件只列当前未完成项。已完成工作和历史证据进入 `CHANGELOG.md`；当前本地结果进入 `PROJECT_AUDIT.md`。

## P0

当前本地代码与验证未发现未处理 P0。生产发布前若缺少模型请求出站 ACL，应重新评估 DNS rebinding 残余风险的发布级别。

## P1 Local Acceptance

1. **Docker gate**
   - 在具备 Docker 的环境运行：
   - `docker compose --env-file deploy/production.env.example -f deploy/docker-compose.yml config --quiet`
   - `docker build --tag agens-web:local .`
   - 启动一次性 migration service 与 app，确认非 root、read-only、健康检查和回滚路径。

2. **模型延迟与异常响应**
   - 2026-07-12 矩阵实测（`019b941` clean + 独立 `agens_web_live` 库）：140/140 choice 严格 live，全 live 回合 choice p50=9069ms、p95=17529ms、max=26234ms。目标 p50≤5s/p95≤15s **未达**。
   - 拆分已做：Narrator 主导 ~8.5–9.4s/回合（每回合必调，~90%+），residual（持久化+网络+页面+规则结算+Judge 摊销）仅 ~0.1–1.3s → 瓶颈在 provider 单次调用延迟，非本地编排。Judge 间歇触发（0–6 次/局，~5.3–8.6s/次）推高 p95/max。降延迟需 provider/模型侧或并发化。
   - 408/429/5xx、整体时限、取消传播专项已由 `tests/unit/llm/test_llm_error_paths.py`（49 项）锁定；偶发严格契约重试已在矩阵观察到（fixed-c 2 次 incomplete retry 恢复）。
   - 开场 World Builder 7 次中 2 次 `incomplete_output`（疑似截断，completion_tokens 一致 1673）回退确定性开场，重跑成功属瞬态；可评估为开场启用 provider JSON schema 或放宽开场契约重试。
   - 不输出 Key、模型地址真值、账号、Cookie、邀请码、原始 prompt 或原始响应。

3. **DNS egress defense**
   - 在部署层增加拒绝 loopback/private/link-local/metadata 的出站 ACL 或受控代理。
   - 应用 allowlist 与连接前 DNS 校验继续保留，但不能单独视为消除 DNS rebinding TOCTOU。

4. **标准局长扩展**
   - 当前内容版本按 60 回合规则终局运行；下一内容批次基于真实玩家反馈扩展到标准 90 回合目标。
   - 优先增加阶段、分支兑现和结局差异，不以继续增加世界数量作为成果。
   - 玩法、内容或状态落账再次变化后，在最新工作树 fingerprint 重跑 A/B/C/D 各 20 回合和规则终局长局；浏览器数据库继续与 `tests\web` 隔离。2026-07-12 已在 `019b941`(clean) + 独立 `agens_web_live` 库重跑 A/B/C/D 各 20 + mixed 60（140/140 choice live），但 mixed-60 跑满 60 回合未触发 `game_over`，规则终局长局样本本批未捕获，待内容侧确认 60 回合主线收束触发条件后再补一次规则终局长局。

## P1 Production Follow-up

生产部署、迁移、备份、回滚和 strict live smoke 按
`docs/PRODUCTION_V5_MIGRATION_CHECKLIST.md` 单独执行。当前本地工作树未部署，任何历史生产成功都不能替代本次服务器侧复核。

生产 strict live 必须同时满足 Narrator `ok`、无 provider fallback、无 gameplay recovery、契约完整和回合连续；HTTP 200 单独不算通过。

## P2 Maintainability

1. 拆 `database_postgres.py`：优先抽 session mutation、catalog 和 rewards repository，保持 `WebDatabaseProtocol` 不变。
2. 拆 `tests/web/test_web_api.py`：auth、model settings、production-hardening、save/load 已拆出；session/turn persistence 仍与 gameplay flow 混在原文件，后续连同把 `_create_invite`/`_login_user`/`_register`/`_model_payload`/`_use_public_model_dns`/`_runner` 迁到 `conftest.py` 一起拆。
3. 评估把应用内 RateLimiter 换成 Redis 或反向代理限流；单实例 Alpha 可保留现实现。
4. 为模型 URL 校验增加可插拔的固定解析/连接层，进一步缩小 DNS rebinding 窗口。
5. 扩展前端测试到完整账号流程、长文本和恢复后继续游玩；HTTP 409 单元测试与真实键盘/焦点证据已完成。
6. 稳定 pre-existing flaky `test_notice_board_description_is_not_treated_as_claimed_reward`：回合 1 随机推进 stage 时，`_narrative_conflicts_with_stage_delta` 把叙事中「练气N层」任务等级描述误判为玩家境界声明并覆盖 narrator 叙事。需正则/上下文消歧或产品判定，属叙事一致性产品行为。
