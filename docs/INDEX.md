# 项目文档索引

后续智能体先读本文，再按任务读取对应文档。本仓库是 Web-only 项目：浏览器 UI + FastAPI 后端 + PostgreSQL，移动端、旧 CLI/REPL、旧 `web/frontend` 都不是当前维护入口。

## 当前状态

- 当前主线：游戏模式 v5 Alpha，A/B/C/D 四按钮固定语义（A 稳妥 / B 机遇 / C 风险 / D 气运），无自由文本主入口，无 HP/MP 常驻 UI。
- 数据库路线：PostgreSQL-only，本地测试和生产都以 Alembic schema 为准；SQLite 已删除，仅作为历史记录保留在 `CHANGELOG.md`。
- 模型设置：注册用户可配置个人模型；访客不可配置；无个人配置时使用系统 Agens 默认。用户 key 只允许后端加密存储和脱敏展示。
- 最新本地代码基线：`6cdcfcc` 已加入脱敏模型性能观测；`compileall` 通过，`tests\web` 66 passed，全量 `pytest -q` 469 passed，前端 build 通过，`git diff --check` 通过。
- 最新本地真实 Chrome 验收：2026-07-01 `local-visible-20turn-20260701-final2` 通过；普通账号注册/登录、系统默认模型开局、角色创建、20/20 choice non-fallback、存档/读档均通过。证据位于 `output/playwright/local-visible-20turn-20260701-final2.{json,ndjson,csv}` 和 `output/playwright/local-visible-20turn-20260701-final2-source.json`，默认不提交。
- 最新生产批次：服务器线程部署 `25ad3d15` 后，Alembic 为 `20260622_0005`，`user_model_configs` 存在，public/origin health、catalog、容器健康、日志敏感标记扫描、一次性真实账号注册/登录/存档/读档/跨会话恢复均通过；生产 start 和至少 1 次 choice 均为 non-fallback，choice 后 `turn_count=1`。
- 当前剩余重点：P1 游玩质量和治理，包括 live 响应慢、narrator repair/judge 依赖、20 回合节奏、重复闭关/突破循环、叙事/权威状态落账，以及 `tests/web/test_web_api.py`、`web/backend/service.py`、`web/backend/database_postgres.py`、`src/agens_novel/engine/game_engine.py` 的小步复杂度治理。

## 当前权威文档

- `README.md`：项目入口、启动和当前状态摘要。
- `AGENTS.md`：项目硬约束、玩法契约、代码治理规则。
- `CLAUDE.md`：Claude/Claude Code 接手本项目时的边界说明。
- `docs/RUNTIME_FLOW.md`：当前运行链路、API 流程、本地启动和模型配置流。
- `docs/GAME_MODE_SPEC.md`：游戏模式 v5 的产品与规则规格。
- `docs/PLAYABLE_GAMEPLAY_ROADMAP_20260629.md`：当前阶段路线；P0 当前批次已闭环，下一步进入 P1 玩法质量和模型效率。
- `docs/ARCHITECTURE.md`：模块地图和后端/引擎/前端分层说明。
- `docs/security.md`：密钥、账号、生产环境和公网 Alpha 安全边界。
- `docs/PROJECT_AUDIT.md`：当前结构边界、已清理内容、剩余技术债。
- `docs/NEXT_GOVERNANCE_BACKLOG.md`：下一批 P0/P1/P2 工作队列。
- `docs/USER_TUTORIAL.md`：面向玩家的中文入门说明。
- `docs/PRODUCTION_V5_MIGRATION_CHECKLIST.md`：生产复验门禁和只读验收清单。
- `CHANGELOG.md`：按日期保留历史变更，不作为当前状态唯一来源。

## 历史内容策略

- 旧 `docs/archive/` 草案、复盘和原型资产已清理，不再作为当前事实或执行计划来源。
- 需要追溯历史时优先看 `CHANGELOG.md`；需要当前状态时只看上方权威文档。
- 文档更新必须区分当前事实、历史证据、未来计划和 TODO，避免把旧计划写成当前状态。

## 按任务阅读

| 任务 | 优先阅读 |
| --- | --- |
| 当前运行链路 / 本地启动 | `docs/RUNTIME_FLOW.md`、`README.md` |
| 游戏规则 / 游玩内容设计 | `docs/GAME_MODE_SPEC.md`、`docs/USER_TUTORIAL.md` |
| 阶段计划 / 玩法迭代执行 | `docs/PLAYABLE_GAMEPLAY_ROADMAP_20260629.md`、`docs/NEXT_GOVERNANCE_BACKLOG.md` |
| 模块地图 / 接手项目 | `docs/ARCHITECTURE.md`、`docs/PROJECT_AUDIT.md` |
| 代码复杂度治理 | `docs/PROJECT_AUDIT.md`、`docs/NEXT_GOVERNANCE_BACKLOG.md` |
| 公网部署 / 密钥 / 安全 | `docs/security.md`、`docs/PRODUCTION_V5_MIGRATION_CHECKLIST.md` |
| 生产账号流 / live model 复核 | `docs/PRODUCTION_V5_MIGRATION_CHECKLIST.md`、服务器线程 `019ee2ee-823e-7441-bdaa-881782da7949` |
| UI 后续细修 | `docs/PROJECT_AUDIT.md`、`web/frontend-react/src/` |
| 历史核对 | `CHANGELOG.md` |

## 执行边界

- fallback 不能算 live-model 成功，即使 HTTP 200。
- 本地自动化测试不等于生产验收；生产验证归服务器线程处理。
- API key、数据库密码、Session Secret、邀请码真实值不得写入仓库、前端包、文档或日志。
- 真实 Chrome 验收不要和 `tests\web` 共用同一个数据库并发运行；Web 测试会清空测试库。