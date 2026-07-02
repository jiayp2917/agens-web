# 2026-06-29 可玩版本阶段执行计划

本文合并 `plan20260629.md` 与 `plan20260629_2.md`，作为当前阶段路线文档。旧草案只保留在归档中，不再作为当前事实来源。

## 结论

当前项目不建议重做，也不建议继续主动扩大功能架构。正确路线是：

1. 先完成已知 P0 遗留问题的验收闭环。
2. 再进入游玩内容与玩法体验改造。
3. 除非发现阻塞性 bug，否则不再做账号、存档、模型配置、部署流程、数据库主结构或大规模路由拆分。
4. 玩法改造优先通过现有 `GameEngine`、规则、事件池、prompt、配置数据和小范围 helper 完成。

## 方案选择

| 方案 | 内容 | 结论 |
| --- | --- | --- |
| A | 合并成待办清单 | 最快，但仍容易混淆治理问题和玩法设计。 |
| B | 合并成阶段执行计划 | **采用。** 最适合当前目标，可直接拆给 Codex、Claude Code 和服务器线程。 |
| C | 升级成完整产品 PRD | 更完整但更重，等 20 回合主流程稳定后再做。 |

## 文档边界

- `docs/GAME_MODE_SPEC.md`：游戏规则规格。
- `docs/RUNTIME_FLOW.md`：运行链路和接口流程。
- `docs/ARCHITECTURE.md`：模块地图、后端/引擎/前端分层说明。
- `docs/NEXT_GOVERNANCE_BACKLOG.md`：活跃待办。
- 本文：阶段路线、执行顺序和跨线程分工。
- `docs/archive/`：历史草案和复盘，只作审计背景。

## P0：遗留问题闭环

目标：证明当前底座可以支撑后续玩法迭代。

2026-07-02 状态更新：

- 本地真实可见 Chrome 跟进验收已通过：`local-visible-20turn-20260701-final2` 完成普通账号注册/登录、系统默认模型开局、角色创建、20/20 choice non-fallback、存档/读档。
- 本地验收仍暴露 P1 质量风险：平均回合耗时约 48.2s、最大约 153.2s，且多回合依赖 narrator repair / mismatch suppression。
- 本地代码已加入脱敏性能观测：下一次真实 Chrome 20 回合证据会记录 narrator/judge 耗时、repair 耗时、prompt 字符数、history 数量、game state 字符数和 provider token 计数，用于判断慢因；这不是性能已修复的结论。
- 生产部署与迁移已完成：Alembic 已到 `20260622_0005`，`user_model_configs` 存在。
- 生产账号注册、登录、存档、读档、跨会话恢复已通过。
- production live model P0 已通过：服务器线程部署 `25ad3d15` 后，生产 start 和至少 1 次 choice 均为 non-fallback，choice 后 `turn_count=1`。历史 `model_config` 旧行遮蔽 env key 的失败保留为经验，后续每次生产部署或模型配置变更仍需复跑同一门禁。

必须完成：

- 本地 PostgreSQL 健康检查和自动化验证。
- 真实可见 Chrome 20 回合 non-fallback 验收。
- 验证用户模型配置：系统默认、个人 key、清除个人配置。
- 验证账号注册、登录、存档、读档。
- 检查 fallback、`game_turns` 连续性、叙事和状态一致性。
- 未来生产部署或模型配置变更后的 production live model 复验交给服务器线程，不在本地代码线程混做。

验收标准：

- 本地 20 回合能完成；当前最新本地证据为 `output/playwright/local-visible-20turn-20260701-final2.{json,ndjson,csv}`。
- 无 HTTP 200 但回合不推进。
- fallback 不被当作 live model 成功。
- 存读档恢复后状态一致。
- 生产 start 和 choice 都必须证明 non-fallback，HTTP 200 不算成功。
- 真实 Chrome 20 回合验收预计 15-45 分钟；若出现连续 fallback、单回合超时或重复不推进，停止并记录问题，不继续硬跑。

## P1：玩法稳定与内容改造

### P1.1 主流程稳定

目标：让 20 回合垂直切片先变得可玩、连贯、少重复。

优先处理：

- 减少重复闭关/突破循环。
- 增加 20 回合内阶段目标、奖励反馈和世界变化。
- 先用脱敏指标定位模型慢因：区分 prompt/history 增长、repair 二次调用、judge 额外调用、provider 响应慢或混合因素；拿到数据后再决定压缩历史、缩小 judge 触发面或调整模型配置。
- 收紧模型叙事与 `state_delta`：模型写获得道具、升层、受伤、结缘、称号或因果时，系统必须落账；否则要拒绝、改写或明确不落账原因。
- 模型只负责润色叙事和选项文案，不决定权威数值。
- 无效行动不能返回成功但不推进；要给明确反馈或转化为有效修炼结果。

### P1.2 内容玩法改造

目标：在不重做架构的前提下，把玩法从“可跑”提升到“有模拟修仙人生感”。

已确认方向：

- 完整局长、垂直切片目标、开场编年史、阶段反馈节奏和境界节奏以 `docs/GAME_MODE_SPEC.md` §3.5 为准。
- 属性系统改为六属性点池制，具体分配规则以 `docs/GAME_MODE_SPEC.md` §4.1 为准。
- 小境界不频繁作为选项；大境界突破作为阶段事件。
- 第一版不做显式资源栏，只保留状态型记录，如境界、年龄、寿元、称号、关系、关键机缘、伤势、因果和传承。
- 以上方向的具体规则与数值以 `docs/GAME_MODE_SPEC.md` 为准；本文只承载阶段目标，不复述规格。

内容来源规则：

- 使用抽象修仙套路库，只借鉴题材共性。
- 不直接使用真实小说人物、门派、剧情原文或专有设定。
- 可做类型化灵感，例如凡人出身、宗门弟子、世家旁支、秘境机缘、心魔劫、洞府传承。
- 特殊组合可以触发特殊世界模板，但模板必须是原创抽象设定。

## P2：文档与治理收口

目标：减少后续智能体误读旧草案。

要做：

- 保持 `docs/INDEX.md` 指向当前权威文档。
- 旧 plan 草案归档，不再作为当前事实。
- `docs/GAME_MODE_SPEC.md`、`docs/RUNTIME_FLOW.md`、`docs/NEXT_GOVERNANCE_BACKLOG.md` 保持同一口径。
- 固化本地 PostgreSQL 启动/恢复说明，避免 `TEST_DATABASE_URL` 缺失造成假绿或跳过。
- Playwright/Chrome 截图和 JSON 默认作为生成证据，不随便提交；需要长期保留时再归档。

## 跨线程分工

- 代码线程 `019ee0bd-4f73-7553-a8ac-9ab1d8bc7dad`：玩法主流程修复、内容规则改造、测试和代码文档同步。
- 服务器线程 `019ee2ee-823e-7441-bdaa-881782da7949`：生产部署、生产账号流、production live model、容器、Alembic、备份和回滚。
- 项目治理/本地验证线程：计划审核、本地 PostgreSQL、自动化测试、真实 Chrome 验收、交付质量复核。

## 可直接分发的任务提示词

### 本地验收

```text
请在 D:\chat\agens-web 做一次只读本地验收，不做代码修改、不读取或输出 secrets。检查本地 PostgreSQL 127.0.0.1:55432，使用 TEST_DATABASE_URL=postgresql+psycopg://agens_test@127.0.0.1:55432/agens_web_test。跑 compileall、pytest tests\web、pytest -q、frontend build、git diff --check。然后用真实可见 Chrome 验证普通账号登录、系统默认模型、个人模型配置、清除个人配置、角色创建、至少 20 回合、存档/读档、fallback、game_turns 连续性、叙事和状态一致性。fallback=true 不能算 live model 成功。输出通过项、失败项、证据路径和 P0/P1/P2 分级。
```

### 玩法主流程修复

```text
请在 D:\chat\agens-web 修复玩法主流程问题，但不要做功能架构级改造。保留现有 FastAPI、React、PostgreSQL、账号、存档、用户模型配置结构。目标是修复叙事和状态不一致、重复闭关/突破循环、无效行动成功但不推进、模型越权决定数值。增加测试覆盖状态落账、突破成功/失败、fallback/llm_error、game_turns 连续性、存读档恢复一致性。更新 README、CHANGELOG、docs/PROJECT_AUDIT.md、docs/NEXT_GOVERNANCE_BACKLOG.md。验证 compileall、pytest tests\web、pytest -q、frontend build、git diff --check。
```

### 生产验收

```text
请在服务器线程 019ee2ee-823e-7441-bdaa-881782da7949 执行 agens-web 生产验收规划与只读预检。不要读取或输出 secrets，不执行 sudo、重启、部署覆盖、生产数据库写入，除非用户单独批准。确认生产 health/catalog/container/Alembic/schema 状态；确认是否已部署 user_model_configs；检查是否具备 MODEL_CONFIG_SECRET 但不输出值；梳理迁移到 20260622_0005 的备份、Alembic upgrade、重启、回滚步骤；明确生产账号流和 production live model non-fallback 验收缺口。
```

### 玩法资料整理

```text
请只读整理 D:\chat\agens-web 当前游戏玩法内容，不改代码。梳理境界、寿元、属性、资源、道具、奖励、死亡、突破规则分别在哪里实现；A/B/C/D 如何影响状态；事件、local_story、fallback、Judge、state_delta 的关系；哪些内容硬编码，哪些可配置化；哪些地方导致重复闭关/突破循环；哪些地方导致模型叙事和状态落账断层。每条给文件路径或代码依据，最后给一个 20 回合垂直切片的最小改造建议。
```

## 验收标准

- 合并后只保留本文作为当前阶段计划。
- 旧 plan 不再出现在 `docs/` 根目录。
- 文档明确：先 P0 闭环，再 P1 玩法内容。
- 内容来源明确禁止真实小说复刻，只做抽象套路。
- 下一轮工作可以直接拆给代码线程、服务器线程和本地验证线程。
