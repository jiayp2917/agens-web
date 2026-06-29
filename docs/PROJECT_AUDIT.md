# 项目结构审核与收束

本文只记录 `agens-web` 当前结构边界、已完成清理和剩余技术债。历史批次细节进入 `CHANGELOG.md` 和 `docs/archive/`，不要把归档内容当作当前事实。

## 当前边界

- 产品入口：React/Vite 浏览器 UI + FastAPI 后端。
- 游戏核心：继续复用 `src/agens_novel/`，`GameEngine` 仍是唯一游戏逻辑入口。
- 当前玩法：游戏模式 v5 Alpha，A/B/C/D 固定语义，A 稳妥 / B 机遇 / C 风险 / D 气运。
- 禁用入口：引导模式、小说模式可作为 UI 提示保留，但不是开放运行逻辑。
- 数据库：PostgreSQL-only。本地测试和生产都以 Alembic 为 schema authority；SQLite 后端已删除。
- 模型设置：注册用户个人配置 + 系统 Agens 默认兜底。`/api/settings/model` 是登录用户接口，`/api/admin/settings/model` 是管理员系统默认接口。
- 密钥规则：模型 API key 只允许后端读取、加密存储和脱敏展示；不得进入前端包、日志、存档、session snapshot 或文档。

## 当前模块地图

| 层级 | 职责 | 主要目录 |
| --- | --- | --- |
| Web UI | 首页、角色创建、游玩页、设置、存读档、教程、终局页。 | `web/frontend-react/` |
| API 层 | 鉴权、会话、开局、回合、存读档、模型设置、响应脱敏。 | `web/backend/` |
| 游戏核心 | Agent 调用、规则校验、状态落账、突破、兜底故事。 | `src/agens_novel/` |
| 数据层 | 用户、session、save、game_turns、progress、模型配置。 | PostgreSQL + Alembic |

## 已完成清理

- 删除移动端源码、移动端打包配置、设备验证文档和 Android APK 打包 skill。
- 删除旧纯 HTML/CSS/JS 前端 `web/frontend/`，React/Vite 是唯一前端入口。
- 删除 `database_sqlite.py`，项目统一为 PostgreSQL-only。
- 删除旧 combat 子系统、早期 persistence 空壳、孤立 `__pycache__/*.pyc`、冗余 `.venv311/`、旧 smoke 临时脚本和过期 Web 路线文档。
- `web/backend/app.py` 已抽出请求模型；`database_postgres.py` 的 test-only auto-DDL 已拆到 schema helper；`service.py` 的部分总结/回合推进路径已收束。
- React 主入口已拆分为认证、首页、角色创建、游戏页、设置/存档弹窗、模型设置面板、存档槽列表、BGM 和终局页等组件。
- 文档已把旧 Alpha 复盘、UI 原型计划和原型图归档到 `docs/archive/2026-06-governance/`。

## 当前已验证事实

- 本地 PostgreSQL 测试库目标：`127.0.0.1:55432/agens_web_test`。
- 用户级模型设置治理本地提交：`44519d7`。
- 本地自动化基线：`tests\web` 59 passed，全量 `pytest -q` 420 passed / 1 xfailed，前端 build 通过。
- 已修复本地可见 Chrome 发现的主流程问题：合法 A/B/C/D 选择不应 HTTP 200 但不推进；叙事/状态 mismatch 时保持 `game_turns` 连续；fallback 过渡回合会记录。
- 本地 Chrome 旧证据覆盖过账号注册/登录/存档/读档、2K 和窄屏布局，但仍需要在模型设置治理后重新做 20 回合真实玩家验收。

## 剩余 P0 风险

| 问题 | 当前状态 | 下一步 |
| --- | --- | --- |
| 生产未部署用户级模型配置 | 本地已有 Alembic `20260622_0005`，生产仍需单独部署。 | 服务器线程确认 `MODEL_CONFIG_SECRET`、备份、迁移、重启和只读验收。 |
| 生产账号流未验收 | 注册/登录/存档/读档缺安全测试路径。 | 使用非 secret 一次性测试账号或经批准的测试路径补验。 |
| production live model 未验收 | fallback 不算成功，HTTP 200 不等于 live model 成功。 | 服务器线程证明 start 和 choice 均非 fallback，且不输出 secrets。 |
| 本地真实玩家流程未重新验收 | 模型设置和主流程修复后还没完成 20 回合可见 Chrome 验收。 | 本地 PG + 真实 Chrome 跑账号流、模型设置、20 回合、存读档。 |

## 剩余 P1 技术债

| 问题 | 风险 | 处理方向 |
| --- | --- | --- |
| 游玩内容弱 | 重复闭关/突破循环、目标感弱、奖励反馈弱。 | 先设计主线目标、阶段事件、奖励落账，再迭代内容。 |
| live model 响应慢 | 历史本地一回合约 63 秒，真实玩家会感到卡顿。 | 优化提示词、超时、重试/降级提示和结构化输出修复。 |
| 叙事与状态仍可能不一致 | 模型说获得道具/升层，但权威 `GameSession` 未落账。 | 收紧 `state_delta`、Judge、`apply_delta()` 和 mismatch 测试。 |
| `GameEngine` 仍偏大 | 仍承担回合、突破、兜底、模型失败等多职责。 | 只按主流程需要拆模型失败、本地故事、突破 helper，避免大拆。 |
| `WebGameService` 边界仍需收束 | API 编排、持久化和错误映射仍集中。 | 继续抽私有 helper，暂不优先大拆 router。 |
| `database_postgres.py` 仍偏大 | SQL、row shaping、测试 DDL 历史包袱仍多。 | 继续抽 catalog/progress/turn helper，不改 schema。 |
| 前端样式仍有集中风险 | 后续 UI 迭代容易互相影响。 | 按页面/组件逐步拆样式，配合 Chrome 截图验收。 |

## 剩余 P2 工作

- 固化本地 PostgreSQL 启动/恢复脚本，避免 `TEST_DATABASE_URL` 缺失导致假绿或跳过。
- 决定 `output/playwright/`、截图和 JSON 证据的归档/忽略策略；默认不提交临时验证产物。
- 生产侧继续做日志脱敏、限流、Cookie/Origin、备份恢复演练和索引评审。
- 历史文档只保留在 `docs/archive/` 和 `CHANGELOG.md`，当前文档只写当前事实和下一步。

## 验证入口

```powershell
cd D:\chat\agens-web
F:\pg\bin\pg_isready.exe -h 127.0.0.1 -p 55432
$env:TEST_DATABASE_URL = "postgresql+psycopg://agens_test@127.0.0.1:55432/agens_web_test"
.\.venv\Scripts\python.exe -m compileall -q src tests web scripts migrations
.\.venv\Scripts\python.exe -m pytest -q tests\web
.\.venv\Scripts\python.exe -m pytest -q
cd web\frontend-react
npm.cmd run build
```

## 文档边界

- 当前运行链路看 `docs/RUNTIME_FLOW.md`。
- 游戏规则规格看 `docs/GAME_MODE_SPEC.md`。
- 模块地图看 `docs/ARCHITECTURE.md`。
- 下一步工作看 `docs/NEXT_GOVERNANCE_BACKLOG.md`。
- 生产迁移看 `docs/PRODUCTION_V5_MIGRATION_CHECKLIST.md`。
- 历史复盘和 UI 原型看 `docs/archive/2026-06-governance/`。