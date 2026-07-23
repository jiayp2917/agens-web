# Next Governance Backlog

本文件只列当前未完成项。已完成工作和历史证据进入 `CHANGELOG.md`；当前本地结果进入 `PROJECT_AUDIT.md`。

## P0

本轮仅重新验证本地工作树，未连接、修改或复核生产环境。当前本地复核未发现新的 P0；本地通过不构成生产发布结论。

## P1 Local Acceptance

1. **双模型正式对照仍未完成**
   - 独立本地 probe：Agens 7/7 strict，选择 `json_schema`；DeepSeek 6/7 strict，`json_schema` 不支持，选择 `json_object`。两者都已归一到同一内部 envelope、白名单和 strict 统计，未强迫使用相同 wire format。
   - Agens v2 20 回合 smoke 为 20/20 strict，fallback、repair、retry 均为 0。DeepSeek 同一 smoke 在首回合后出现 fallback，仅 1/20 strict，已停止该 provider 的真实调用，不能进入 v3 正式局。
   - Agens v3 三局批处理未在评估时限内产生汇总，已停止且不计通过。未完成 DeepSeek 修复、Agens v3 完整局、冻结九快照盲审前，不得报告模型优劣、能力百分比或内容质量排名。

2. **路线内容差异与失败风险验收**
   - v3 九阶段世界事件、两条命数承诺、最近五项 motif 去重、路线后果和 `post_arc` 已实现；默认仍为 `story_version=2`，旧存档按精确版本继续解析。
   - 规则级 200 种子矩阵（9,600 条）方向门槛通过：高风险相对普通负面结果 `+24.625pp`（95% CI `+22.208pp` 至 `+26.875pp`）、C 相对 A `+44.688pp`（`+43.021pp` 至 `+46.438pp`）、低资质相对高资质 `+16.438pp`（`+13.625pp` 至 `+19.250pp`）。结果为飞升 398、死亡 3226、主线失败 1289、主线成功 4687、未收束 0。
   - 这证明规则方向和收束能力，不证明真实玩家体验或模型内容质量。后续从自然种子中选取飞升、死亡/寿终和主线失败分支，在内置 Chrome 逐项验收；模型不得决定死亡或终局。
   - 无 Key 本地开场模板已修复“牵动，其”等病句，最新 Chrome fallback 局从 16 岁推进到 17 岁且寿元同步变化。该切片不替代 v3 长局、移动端长文本和真实模型内容验收。

3. **性能与异常响应**
   - 408/429/5xx、整体时限和取消传播已有回归测试。`choice p50 <= 5s` 仍是观察指标，不是本批阻塞门槛；下一次通过严格 live smoke 收集同一 provider/network 的新基线，不能使用历史 fingerprint 的延迟数字代替。

## P1 Production Follow-up

本批不执行任何服务器、生产数据库、Docker 或部署操作。需要单独授权并重新取证的工作包括：Compose/image 门禁、strict start/choice、备份恢复与回滚演练、v2 切换、Redis/Squid/egress ACL 和重启后的持久化复验。届时 HTTP 200 不能替代 Narrator `ok`、契约完整、无 provider fallback、无 gameplay recovery 和回合连续性。

## P2 Maintainability

1. 继续按触碰范围拆 `tests/web/test_web_api.py` 的 session/turn 主题，避免无关大改。
2. 为模型 URL 校验增加可插拔的固定解析/连接层，作为现有应用校验、Squid 和主机 ACL 之外的额外防线。
3. 扩展前端测试到完整账号流程、长文本和恢复后继续游玩；HTTP 409 单元测试与真实键盘/焦点证据已完成。
4. 将产品服务与评估基础设施解耦：产品层只依赖默认空实现的评估钩子，评估配置和启动由独立应用工厂组装；同时消除确认存在的运行时依赖环。
5. 为 `scripts/local_visible_playtest.cjs` 建立脱敏证据回放夹具后，分离浏览器驱动、持久化回合审计、玩家可见内容审计、报告构造和纯函数裁决，保持 CLI、证据字段与退出码兼容。
6. 按单一边界治理 `story_catalog`、开局、模型提示/传输/解析、普通回合、`GameSession` 与 `WebGameService`；每一步保持 v1/v2/v3 存档、固定种子、单次规则结算、模型重试、事件顺序、幂等和 HTTP 409 语义。
