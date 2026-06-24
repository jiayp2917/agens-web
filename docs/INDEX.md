# 项目文档索引

后续智能体先读本文，再按任务读取对应文档。本仓库是 Web-only 项目。

## 当前权威文档

- `AGENTS.md`：项目硬约束、当前玩法契约、目录边界。
- `docs/RUNTIME_FLOW.md`：当前可运行 Alpha 链路。当前实现已切换到游戏模式：A/B/C/D 四按钮（稳妥/机遇/风险/气运），无 HP/MP，规则引擎权威结算。
- `docs/security.md`：外网 Alpha 安全边界、生产环境变量、反代要求。
- `docs/PROJECT_AUDIT.md`：结构边界、技术债、归档和瘦身方向。
- `docs/GAME_MODE_SPEC.md`：游戏模式 v5 规格——当前构建目标。代码随此规格切换到游戏模式。
- `docs/ARCHITECTURE.md`：项目模块架构说明（web/backend + src/agens_novel + web/frontend-react 三层模块地图与串联流程；面向开发者与想了解全局的读者）。
- `docs/UI_REFACTOR_PLAN.md`：已审核通过的编年史 UI 原型图、页面拆分、组件样式和重构验收标准。
- `docs/USER_TUTORIAL.md`：面向玩家的完整中文入门教程，从访客/账号选择到飞升/死亡全流程。
- `docs/ALPHA_REVIEW_AND_LESSONS.md`：Alpha 问题确认、已修内容、成功/失败经验、剩余风险和后续执行规则。
- `docs/PRODUCTION_V5_MIGRATION_CHECKLIST.md`：生产 v5 表缺失后的部署、备份、迁移和只读验收门槛。
- `docs/NEXT_GOVERNANCE_BACKLOG.md`：下一批治理 backlog，区分本地复杂度治理与需要明确授权的生产变更。
- `README.md`：最短启动说明和项目入口。
- `CHANGELOG.md`：按日期记录已落地变更。

## 辅助和历史文档

- `docs/archive/`：历史草稿和已归档计划，不作为当前状态来源。

## 按任务阅读

| 任务 | 优先阅读 |
| --- | --- |
| 当前运行链路 / 游玩流程 | `docs/RUNTIME_FLOW.md`、`web/backend/app.py` |
| 公网部署 / 密钥 / 安全 | `docs/security.md`、`deploy/production.env.example`、`deploy/docker-compose.yml` |
| 生产 v5 迁移 / 缺表修复 | `docs/PRODUCTION_V5_MIGRATION_CHECKLIST.md`、`docs/PROJECT_AUDIT.md` |
| 结构清理 / 技术债 | `docs/NEXT_GOVERNANCE_BACKLOG.md`、`docs/PROJECT_AUDIT.md`、`docs/INDEX.md` |
| Alpha 复盘 / 成功失败经验 | `docs/ALPHA_REVIEW_AND_LESSONS.md`、`CHANGELOG.md` |
| 游戏模式 v5 设计 | `docs/GAME_MODE_SPEC.md` |
| UI 重构 / 原型落地 | `docs/UI_REFACTOR_PLAN.md`、`docs/ui-prototypes/`、`web/frontend-react/src/pages/`、`web/frontend-react/src/styles.css` |
| UI 当前细修状态 / 截图验收 | `docs/PROJECT_AUDIT.md` 的 2026-06-24 状态、`docs/UI_REFACTOR_PLAN.md` 的落地状态 |
| 模块地图 / 接手项目 | `docs/ARCHITECTURE.md`、`docs/PROJECT_AUDIT.md`、`web/backend/app.py` |
| 新玩家教程 / 用户支持 | `docs/USER_TUTORIAL.md`、`web/frontend-react/src/components/TutorialDialog.tsx` |
| 历史待办核对 | `docs/archive/2026-06-20-claude-followups.md`、`docs/ALPHA_REVIEW_AND_LESSONS.md` |

## 当前执行边界

- 生产入口使用 React/Vite build 产物；旧 `web/frontend` 已删除，资产迁入 `web/frontend-react/public/assets`。
- 当前主线是游戏模式；引导模式、小说模式不是当前开放运行逻辑。
- PostgreSQL 生产 schema 以 Alembic 为准；SQLite 仍作为本地测试默认后端。
- API key、数据库密码、Session Secret、邀请码真实值不得写入仓库、前端包、文档或日志。
- 当前本机浏览器自动验收优先使用 Chrome DevTools MCP；Codex 内置浏览器存在环境闪退风险，不作为可靠验收入口。
