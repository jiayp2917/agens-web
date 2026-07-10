# 2026-06-29 可玩版本阶段执行计划

本文是当前阶段路线文档。旧 `plan20260629*` 草案已清理，不再作为当前事实来源；历史变更看 `CHANGELOG.md`，当前执行看本文和 `docs/NEXT_GOVERNANCE_BACKLOG.md`。

## 结论

当前项目不建议重做，也不建议继续主动扩大功能架构。正确路线是：

1. 2026-07-10 本地代码已修复 SSRF、状态一致性、事务、幂等和 fallback P0/P1；当前还需要 Docker、真实 Chrome、live-model 和生产迁移门禁。
2. 门禁完成后再继续 P1：模型效率、20 回合内容体验、叙事与权威状态落账。
3. 不再扩大账号、存档、模型配置和数据库主结构；后续只按已登记风险做小批次修复。
4. 玩法改造优先通过现有 `GameEngine` 门面、flow、规则、事件池、prompt 和配置数据完成。

## 文档边界

- `docs/GAME_MODE_SPEC.md`：游戏规则规格。
- `docs/RUNTIME_FLOW.md`：运行链路和接口流程。
- `docs/ARCHITECTURE.md`：模块地图、后端/引擎/前端分层说明。
- `docs/NEXT_GOVERNANCE_BACKLOG.md`：活跃待办和门禁。
- 本文：阶段路线、执行顺序和跨线程分工。
- `CHANGELOG.md`：历史变更记录，不作为当前状态唯一来源。

## P0：验收闭环状态

目标：证明当前底座可以支撑后续玩法迭代。

当前状态：本地代码实现已闭环，完整发布门禁未闭环。

- 已实现：SSRF 防护、严格 Judge/突破/终局、fallback 本地故事结算、固定 A/B/C/D、存档终局原因、访客 PG 持久化、CAS/幂等/事务、路由拆分、静态质量零错误、锁文件和容器加固。
- 已验证：本地 PostgreSQL migration 和定向自动化；最终全量门禁以当前批次 `CHANGELOG.md` 为准。
- 未验证：本批真实 Chrome、真实 LLM、Docker build 和生产 `20260710_0008` 升级。
- 旧 2026-07-09 Chrome 与旧生产结果只作为 `CHANGELOG.md` 历史证据，不能接受当前未部署代码。

后续触发条件：

- 生产部署 `20260710_0008`、模型配置变更、provider 变更或运行时模型调用链改动后，必须复跑 production start+choice non-fallback。
- 玩法节奏、状态落账、选项约束、模型效率或重大 UI 流程变更后，必须复跑本地真实 Chrome 20 回合。
- fallback 不能算 live-model 成功，HTTP 200 也不能单独算成功。

## P1：模型效率专项

目标：先用数据定位慢因，再改 prompt/history/repair/judge/provider。

现状（2026-07-09 `final2` 内容审查）：ordinary-turn repair 仍为 0，但 narrator 结构化输出仍不稳；mixed 长局 `narrator_incomplete_output_count=46/49`、`judge_count=4`，D 路线最大约 64.2s、mixed 最大约 64.1s。整体耗时没有完全闭环，当前慢因转向 **provider/narrator 长尾、模型输出契约和 judge 调用成本**。

下一步：

- 后续涉及模型效率或 narrator 契约改动时，用当前脱敏诊断复跑真实 Chrome 内容审查采样。
- 采集平均/最大 choice 耗时、narrator 耗时、judge 耗时、repair attempt、repaired output、prompt 字符数、history 数量、game-state 字符数、token usage、fallback、`game_turns` 连续性。
- 如果慢因是 prompt/history 增长，压缩历史为摘要 + 最近少量原文；当前 narrator prompt 软上限切片（开场上下文 + 省略占位 + 最近 6 条）已通过 Chrome 20 回合复采，repair 保持 0/20，但耗时仍高。
- repair 当前不是本批慢因；narrator parser/契约仍是高风险独立批次，需保持测试预算。
- judge 本次为 5 次；继续评估触发条件和超时成本，但不要为了省耗时跳过突破、寿元、伤势、关键道具、功法、称号、关系等权威状态审核。
- 如果慢因是 provider，记录性能差异并继续保留用户个人模型配置能力。

## P1：玩法稳定与内容改造

目标：让 20 回合垂直切片从“能跑”提升到“有模拟修仙人生感”。

优先处理：

- 减少重复闭关/突破循环。
- 增加 20 回合内阶段目标、奖励反馈和世界变化。
- 0-16 岁开场编年史已接入动态开局链路；后续作为回归项维护。
- 四类事件池（稳健、机缘、风险、气运）已先接入每 4 回合阶段反馈；后续继续丰富池内容和路线差异。
- 每 3-5 回合给阶段反馈；当前实现为每 4 回合 `world.lore_add`。
- 收紧模型叙事与 `state_delta`：关键道具、功法、属性成长、称号、关系、伤势、寿元、境界变化必须落账；否则拒绝、改写或降为非权威叙事。本轮已覆盖属性成长按最终落账 delta 校验、功法与敏感道具 Judge 触发。
- 模型只负责润色叙事和选项文案，不决定权威数值。
- 无效行动不能返回成功但不推进；要给明确反馈或转化为有效修炼结果。

内容来源规则：

- 使用抽象修仙套路库，只借鉴题材共性。
- 不直接使用真实小说人物、门派、剧情原文或专有设定。
- 可做类型化灵感，例如凡人出身、宗门弟子、世家旁支、秘境机缘、心魔劫、洞府传承。
- 特殊组合可以触发特殊世界模板，但模板必须是原创抽象设定。

## P1：复杂度治理

目标：只治理会影响当前主流程的复杂度，不做“为了干净”的大拆。

优先文件：

- `tests/web/test_web_api.py`：按账号、模型设置、会话、存读档、回合持久化拆测试主题。
- `web/backend/service.py`：抽会话推进、模型配置解析、存档持久化 helper，不改 API 行为。
- `web/backend/database_postgres.py`：抽 row shaping 和重复 SQL helper，不改 schema。
- `src/agens_novel/engine/game_engine.py`：围绕 fallback、breakthrough、local story、model failure 小切片治理。

## P2：文档与治理收口

- 保持 `docs/INDEX.md` 指向当前权威文档。
- 保持 `docs/GAME_MODE_SPEC.md`、`docs/RUNTIME_FLOW.md`、`docs/NEXT_GOVERNANCE_BACKLOG.md` 同一口径。
- 固化本地 PostgreSQL 启动/恢复说明，避免 `TEST_DATABASE_URL` 缺失造成假绿或跳过。
- Playwright/Chrome 截图、JSON、NDJSON、CSV 默认作为生成证据，不随便提交。
- 历史草案、复盘和旧 UI 原型已清理；不再从 `docs/archive/` 读取当前事实。

## 跨线程分工

- 代码线程 `019ee0bd-4f73-7553-a8ac-9ab1d8bc7dad`：玩法主流程修复、内容规则改造、测试和代码文档同步。
- 服务器线程 `019ee2ee-823e-7441-bdaa-881782da7949`：生产部署、生产账号流、production live model、容器、Alembic、备份和回滚。
- 项目治理/本地验证线程：计划审核、本地 PostgreSQL、自动化测试、真实 Chrome 验收、交付质量复核。

## 可直接分发的任务提示词

### 模型效率采样

```text
请在 D:\chat\agens-web 做一次真实可见 Chrome 20 回合模型效率采样，不改代码、不读取或输出 secrets。使用本地 PostgreSQL，确认没有 pytest 并发清库。基于最新脱敏诊断记录 average/max choice latency、narrator/judge elapsed、repair_attempt_count、repaired_output_count、prompt chars、game_state chars、history count、token usage、fallback count、game_turns 连续性、存读档结果和证据路径。fallback=true 不能算 live model 成功。最后判断慢因更可能来自 prompt/history、repair、judge、provider 还是混合因素，并给出下一步最小修复建议。
```

### 玩法主流程修复

```text
请在 D:\chat\agens-web 继续修复玩法主流程问题，但不要做功能架构级改造。保留现有 FastAPI、React、PostgreSQL、账号、存档、用户模型配置结构。当前 0-16 岁开场编年史、每 4 回合四路线阶段反馈事件池、属性成长最终落账校验和功法/关键道具 Judge 触发已有首批实现；下一步目标是用真实 Chrome 20 回合验证体验，继续减少重复闭关/突破循环，丰富稳健/机缘/风险/气运事件池，并扩展称号、关系、伤势、寿元、karma 等普通回合权威落账测试。补充测试并跑 compileall、pytest tests\web、pytest -q、frontend build、git diff --check。
```
