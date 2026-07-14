# Next Governance Backlog

本文件只列当前未完成项。已完成工作和历史证据进入 `CHANGELOG.md`；当前本地结果进入 `PROJECT_AUDIT.md`。

## P0

当前本地代码与验证未发现未处理 P0。生产当前健康，但候选尚未通过 strict choice 验收，不得按已发布版本对外宣称完成。

## P1 Local Acceptance

1. **Narrator 英文正文可靠性**
   - 生产 v1 strict smoke 中，start non-fallback，但首个 choice 的两次 Narrator 输出均因正文英文残留被判 incomplete，最终进入 fallback。
   - 需要在不放宽玩家可见文本门禁的前提下，优先收紧 prompt；若做确定性处理，只能安全替换已知词或丢弃含未知英文的句段，不能静默保留英文，也不能接受缺 narrative/state_delta/四选项的结果。
   - 新提交必须补单元测试，并重新执行生产 v1 strict choice、旧镜像回滚演练、v2 切换和 v2 strict smoke。

2. **模型延迟与异常响应**
   - 当前 fingerprint `ac14d076` + `agens_web_test` headed Chrome 矩阵 164/164 choice 严格 live；choice p50=9495ms、p95=18025ms、max=44636ms。目标 p50≤5s/p95≤15s **未达**。
   - Narrator 仍主导单回合延迟；当前矩阵 Judge 12 次，延迟长尾仍需 provider/模型侧或并发化处理，不能只靠本地编排优化。
   - 408/429/5xx、整体时限、取消传播专项已由 `tests/unit/llm/test_llm_error_paths.py`（49 项）锁定；偶发严格契约重试已在矩阵观察到（fixed-c 2 次 incomplete retry 恢复）。
   - 本批已为 World Builder 增加 provider JSON schema，并补回 `new_game.character` 完整契约；最新矩阵开场严格 live 通过，后续仍需监控 provider 截断。
   - 不输出 Key、模型地址真值、账号、Cookie、邀请码、原始 prompt 或原始响应。

3. **路线内容差异**
   - 90 回合 v2 与黄金路线已实现；后续继续降低 C/D 路线高相似度，增加世界专属兑现和失败结局差异。

## P1 Production Follow-up

生产隔离、备份、Stage 1、Redis/Squid/ACL 和基础 health 已完成。当前待办：

1. 确认回滚到 `a5a1f0f9`，或在新提交修复 Narrator 后继续；未确认前不重复 production choice。
2. 完成旧镜像回滚演练、重新部署最终提交、启用 `story_version=2` 并执行 v2 strict smoke。
3. 按服务器治理约定持久化 `br_netfilter`、bridge sysctl 和 ACL 重应用；禁止在活跃 Docker 主机卸载 `br_netfilter`。
4. 复核生产日志脱敏、备份恢复路径和重启后的 Redis/Squid/ACL/application health。

生产 strict live 必须同时满足 Narrator `ok`、无 provider fallback、无 gameplay recovery、契约完整和回合连续；HTTP 200 单独不算通过。

## P2 Maintainability

1. 拆 `database_postgres.py`：优先抽 session mutation、catalog 和 rewards repository，保持 `WebDatabaseProtocol` 不变。
2. 继续按触碰范围拆 `tests/web/test_web_api.py` 的 session/turn 主题，避免无关大改。
3. 为模型 URL 校验增加可插拔的固定解析/连接层，作为现有应用校验、Squid 和主机 ACL 之外的额外防线。
4. 扩展前端测试到完整账号流程、长文本和恢复后继续游玩；HTTP 409 单元测试与真实键盘/焦点证据已完成。
