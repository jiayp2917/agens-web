# 项目文档索引

后续智能体先读本文，再按任务读取对应文档。本仓库是 Web-only 项目。

## 当前权威文档

- `AGENTS.md`：项目硬约束、当前玩法契约、目录边界。
- `docs/RUNTIME_FLOW.md`：当前可运行 Alpha 链路。当前实现仍是引导模式：A/B/C 模型选项 + D 自由输入。
- `docs/security.md`：外网 Alpha 安全边界、生产环境变量、反代要求。
- `docs/PROJECT_AUDIT.md`：结构边界、技术债、归档和瘦身方向。
- `docs/GAME_MODE_SPEC.md`：游戏模式 v5 草案。它是下一阶段规格，不代表当前代码已切换。
- `README.md`：最短启动说明和项目入口。
- `CHANGELOG.md`：按日期记录已落地变更。

## 辅助和历史文档

- `docs/WEB_ITERATION_PLAN.md`：早期 Web-only 迭代计划，保留作路线背景。
- `docs/FOLLOWUPS.md`：旧 Claude Code 待办清单，部分内容已过期，不能直接当当前事实。
- `docs/ALPHA_REVIEW_AND_LESSONS.md`：Alpha 复盘和经验记录。
- `docs/archive/`：历史草稿和已归档计划，不作为当前状态来源。

## 按任务阅读

| 任务 | 优先阅读 |
| --- | --- |
| 当前运行链路 / 游玩流程 | `docs/RUNTIME_FLOW.md`、`web/backend/app.py` |
| 公网部署 / 密钥 / 安全 | `docs/security.md`、`deploy/production.env.example`、`deploy/docker-compose.yml` |
| 结构清理 / 技术债 | `docs/PROJECT_AUDIT.md`、`docs/INDEX.md` |
| 游戏模式 v5 设计 | `docs/GAME_MODE_SPEC.md` |
| 历史待办核对 | `docs/FOLLOWUPS.md`、`docs/ALPHA_REVIEW_AND_LESSONS.md` |

## 当前执行边界

- 生产入口优先使用 React/Vite build 产物；旧 `web/frontend` 只作为 fallback，后续待归档。
- 当前主线仍是引导模式 Alpha；小说模式、游戏模式不是当前开放运行逻辑。
- PostgreSQL 生产 schema 以 Alembic 为准；SQLite 仍作为本地测试默认后端。
- API key、数据库密码、Session Secret、邀请码真实值不得写入仓库、前端包、文档或日志。
