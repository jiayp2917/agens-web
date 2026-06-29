# 项目文档索引

后续智能体先读本文，再按任务读取对应文档。本仓库是 Web-only 项目：浏览器 UI + FastAPI 后端 + PostgreSQL，移动端、旧 CLI/REPL、旧 `web/frontend` 都不是当前维护入口。

## 当前状态

- 当前主线：游戏模式 v5 Alpha，A/B/C/D 四按钮固定语义（A 稳妥 / B 机遇 / C 风险 / D 气运），无自由文本主入口，无 HP/MP 常驻 UI。
- 数据库路线：PostgreSQL-only，本地测试和生产都以 Alembic schema 为准；SQLite 已删除，仅作为历史记录出现在 `CHANGELOG.md` 或归档文档中。
- 模型设置：注册用户可配置个人模型；访客不可配置；无个人配置时使用系统 Agens 默认。用户 key 只允许加密存储和脱敏展示。
- 最新本地自动化基线：用户级模型设置治理已在本地提交 `44519d7`，`tests\web` 59 passed，全量 `pytest -q` 420 passed / 1 xfailed，前端 build 通过。
- 尚未完成：生产部署 Alembic `20260622_0005`、生产账号注册/登录/存档/读档、production live model 非 fallback 验收、可见 Chrome 20 回合真实玩家验收。

## 当前权威文档

- `README.md`：项目入口、启动和当前状态摘要。
- `AGENTS.md`：项目硬约束、玩法契约、代码治理规则。
- `CLAUDE.md`：Claude/Claude Code 接手本项目时的边界说明。
- `docs/RUNTIME_FLOW.md`：当前运行链路、API 流程、本地启动和模型配置流。
- `docs/GAME_MODE_SPEC.md`：游戏模式 v5 的产品与规则规格。
- `docs/ARCHITECTURE.md`：模块地图和后端/引擎/前端分层说明。
- `docs/security.md`：密钥、账号、生产环境和公网 Alpha 安全边界。
- `docs/PROJECT_AUDIT.md`：当前结构边界、已清理内容、剩余技术债。
- `docs/NEXT_GOVERNANCE_BACKLOG.md`：下一批 P0/P1/P2 工作队列。
- `docs/USER_TUTORIAL.md`：面向玩家的中文入门说明。
- `docs/PRODUCTION_V5_MIGRATION_CHECKLIST.md`：生产迁移和只读验收清单；生产闭环前保留。
- `CHANGELOG.md`：按日期保留历史变更，不作为当前状态唯一来源。

## 归档内容

- `docs/archive/`：历史草稿、旧 UI 计划、旧 Alpha 复盘和原型截图。只作审计背景，不作为当前事实来源。
- `docs/archive/2026-06-governance/ALPHA_REVIEW_AND_LESSONS.md`：Alpha 历史复盘。
- `docs/archive/2026-06-governance/UI_REFACTOR_PLAN.md`：已落地 UI 原型计划。
- `docs/archive/2026-06-governance/ui-prototypes/`：历史 UI 原型图和 HTML。

## 按任务阅读

| 任务 | 优先阅读 |
| --- | --- |
| 当前运行链路 / 本地启动 | `docs/RUNTIME_FLOW.md`、`README.md` |
| 游戏规则 / 游玩内容设计 | `docs/GAME_MODE_SPEC.md`、`docs/USER_TUTORIAL.md` |
| 模块地图 / 接手项目 | `docs/ARCHITECTURE.md`、`docs/PROJECT_AUDIT.md` |
| 代码复杂度治理 | `docs/PROJECT_AUDIT.md`、`docs/NEXT_GOVERNANCE_BACKLOG.md` |
| 公网部署 / 密钥 / 安全 | `docs/security.md`、`docs/PRODUCTION_V5_MIGRATION_CHECKLIST.md` |
| 生产账号流 / live model 验收 | `docs/PRODUCTION_V5_MIGRATION_CHECKLIST.md`、服务器线程 `019ee2ee-823e-7441-bdaa-881782da7949` |
| UI 后续细修 | `docs/PROJECT_AUDIT.md`、`web/frontend-react/src/`、历史原型归档 |
| 历史核对 | `CHANGELOG.md`、`docs/archive/` |

## 执行边界

- fallback 不能算 live-model 成功，即使 HTTP 200。
- 本地自动化测试不等于生产验收；生产验证归服务器线程处理。
- API key、数据库密码、Session Secret、邀请码真实值不得写入仓库、前端包、文档或日志。
- 文档更新时必须区分当前事实、历史证据、未来计划和 TODO，不要把旧计划写成当前状态。