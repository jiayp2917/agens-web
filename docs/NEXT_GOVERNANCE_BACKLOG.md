# Next Governance Backlog

本文件只列当前未完成项。已完成工作和历史证据进入 `CHANGELOG.md`；当前本地结果进入 `PROJECT_AUDIT.md`。

## P0

当前复核未发现新的 P0。`f302d37` 内容补丁与本地代码/浏览器验收已通过；生产仍未完成 strict choice、回滚、v2 与 ACL 持久化验收，不得按已发布版本对外宣称完成。

## P1 Local Acceptance

1. **Docker 当前候选门禁**
   - 本机当前没有可用 Docker CLI，尚未对 `f302d37` 执行 Compose config 或镜像构建。恢复 Docker CLI 后先补此门禁；未通过前不生成生产候选包、不部署，也不重试生产 choice。

2. **模型延迟与异常响应**
   - 当前 fingerprint `ac14d076` + `agens_web_test` headed Chrome 矩阵 164/164 choice 严格 live；choice p50=9495ms、p95=18025ms、max=44636ms。目标 p50≤5s/p95≤15s **未达**。
   - Narrator 仍主导单回合延迟；当前矩阵 Judge 12 次，延迟长尾仍需 provider/模型侧或并发化处理，不能只靠本地编排优化。
   - 408/429/5xx、整体时限、取消传播专项已由 `tests/unit/llm/test_llm_error_paths.py`（49 项）锁定；偶发严格契约重试已在矩阵观察到（fixed-c 2 次 incomplete retry 恢复）。
   - 本批已为 World Builder 增加 provider JSON schema，并补回 `new_game.character` 完整契约；最新矩阵开场严格 live 通过，后续仍需监控 provider 截断。
   - 不输出 Key、模型地址真值、账号、Cookie、邀请码、原始 prompt 或原始响应。

3. **路线内容差异**
   - 90 回合 v2 与黄金路线已实现；后续继续降低 C/D 路线高相似度，增加世界专属兑现和失败结局差异。

## P1 Production Follow-up

生产隔离、备份、Stage 1、Redis/Squid 和基础 health 曾完成；2026-07-20 重启后 ACL 与 bridge filtering 未恢复。当前待办：

1. 先恢复 Docker CLI 并完成当前 `f302d37` 的 Compose config 与镜像构建门禁；未通过前不部署、不重试 production choice。
2. 生成候选包、重新备份并以 v1 执行 strict start + choice、存读档、幂等和 409 smoke；失败则按既有 v1 恢复路径停止，不回退 schema。
3. 在 v1 通过且尚无业务 v2 存档时演练旧镜像回滚，重新部署最终镜像后切换 v2 并完成 v2 strict smoke。
4. 安装 `f4c7333` 的持久化资产，先做 service restart，再做受控主机重启；复核 Redis/Squid/application health、`br_netfilter`、bridge filtering 与 `DOCKER-USER` 首位 ACL。禁止在活跃 Docker 主机卸载 `br_netfilter`。

生产 strict live 必须同时满足 Narrator `ok`、无 provider fallback、无 gameplay recovery、契约完整和回合连续；HTTP 200 单独不算通过。

## P2 Maintainability

1. 拆 `database_postgres.py`：优先抽 session mutation、catalog 和 rewards repository，保持 `WebDatabaseProtocol` 不变。
2. 继续按触碰范围拆 `tests/web/test_web_api.py` 的 session/turn 主题，避免无关大改。
3. 为模型 URL 校验增加可插拔的固定解析/连接层，作为现有应用校验、Squid 和主机 ACL 之外的额外防线。
4. 扩展前端测试到完整账号流程、长文本和恢复后继续游玩；HTTP 409 单元测试与真实键盘/焦点证据已完成。
