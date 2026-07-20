# Next Governance Backlog

本文件只列当前未完成项。已完成工作和历史证据进入 `CHANGELOG.md`；当前本地结果进入 `PROJECT_AUDIT.md`。

## P0

当前复核未发现新的 P0，但当前未提交内容补丁导致 16 个引擎测试失败，生产也未通过 strict choice 或重启后的 ACL 持久化验收；不得按已发布版本对外宣称完成。

## P1 Local Acceptance

1. **当前内容补丁回归与编年史质量**
   - 当前未提交的 `breakthrough_flow.py` helper 缩进使 `_judge_breakthrough_delta` 等后续方法脱离类，三个引擎测试文件共 16 failed；先修复类边界和质量守卫，再运行全量本地门禁。
   - clean `f4c7333` 的 90 回合 headed Chrome 在第 65 回合发现突破复用上一回合叙事，导致无新增可见编年史条目；普通回合去重未覆盖突破路径。规则兜底文案中的“旁证/卷册/本阶段/沿稳妥之路”等调度词也不得继续作为玩家可见叙事。
   - 时间跨度只能使用规则拥有的 `elapsed_years`；Narrator 不得虚构“数十年/数十载”。通用替代文案仍需在 60 回合内保持足够差异，且不能吞掉与权威寿元 delta 一致的合法时间。

2. **Narrator 英文正文可靠性与当前候选复验**
   - `35fe2dc` 已落地全中文 schema/prompt/retry/诊断收紧，但尚未随可发布的最终候选通过全量门禁或生产重验。
   - 修复内容补丁后，必须以 `AGENS_VALIDATION_SEED=agens-golden-169` 重跑独立数据库的 90 回合 headed Chrome：严格 live、无 fallback/recovery/可见禁词/重复条目，并在 90 回合内 `finale=true`；另跑 20 回合混合、双击、刷新与存读档。
   - 生产 v1 strict smoke 中，start non-fallback，但首个 choice 的两次 Narrator 输出均因正文英文残留被判 incomplete，最终进入 fallback。新本地候选通过后才可重做 v1 strict choice、旧镜像回滚演练、v2 切换和 v2 strict smoke。

3. **模型延迟与异常响应**
   - 当前 fingerprint `ac14d076` + `agens_web_test` headed Chrome 矩阵 164/164 choice 严格 live；choice p50=9495ms、p95=18025ms、max=44636ms。目标 p50≤5s/p95≤15s **未达**。
   - Narrator 仍主导单回合延迟；当前矩阵 Judge 12 次，延迟长尾仍需 provider/模型侧或并发化处理，不能只靠本地编排优化。
   - 408/429/5xx、整体时限、取消传播专项已由 `tests/unit/llm/test_llm_error_paths.py`（49 项）锁定；偶发严格契约重试已在矩阵观察到（fixed-c 2 次 incomplete retry 恢复）。
   - 本批已为 World Builder 增加 provider JSON schema，并补回 `new_game.character` 完整契约；最新矩阵开场严格 live 通过，后续仍需监控 provider 截断。
   - 不输出 Key、模型地址真值、账号、Cookie、邀请码、原始 prompt 或原始响应。

4. **路线内容差异**
   - 90 回合 v2 与黄金路线已实现；后续继续降低 C/D 路线高相似度，增加世界专属兑现和失败结局差异。

## P1 Production Follow-up

生产隔离、备份、Stage 1、Redis/Squid 和基础 health 曾完成；2026-07-20 重启后 ACL 与 bridge filtering 未恢复。当前待办：

1. 在本地最终候选完成全量门禁和两局 Chrome 验收前，不部署、不重试 production choice。
2. 生成候选包、重新备份并以 v1 执行 strict start + choice、存读档、幂等和 409 smoke；失败则按既有 v1 恢复路径停止，不回退 schema。
3. 在 v1 通过且尚无业务 v2 存档时演练旧镜像回滚，重新部署最终镜像后切换 v2 并完成 v2 strict smoke。
4. 安装 `f4c7333` 的持久化资产，先做 service restart，再做受控主机重启；复核 Redis/Squid/application health、`br_netfilter`、bridge filtering 与 `DOCKER-USER` 首位 ACL。禁止在活跃 Docker 主机卸载 `br_netfilter`。

生产 strict live 必须同时满足 Narrator `ok`、无 provider fallback、无 gameplay recovery、契约完整和回合连续；HTTP 200 单独不算通过。

## P2 Maintainability

1. 拆 `database_postgres.py`：优先抽 session mutation、catalog 和 rewards repository，保持 `WebDatabaseProtocol` 不变。
2. 继续按触碰范围拆 `tests/web/test_web_api.py` 的 session/turn 主题，避免无关大改。
3. 为模型 URL 校验增加可插拔的固定解析/连接层，作为现有应用校验、Squid 和主机 ACL 之外的额外防线。
4. 扩展前端测试到完整账号流程、长文本和恢复后继续游玩；HTTP 409 单元测试与真实键盘/焦点证据已完成。
