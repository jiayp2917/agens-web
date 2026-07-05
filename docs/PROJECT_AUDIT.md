# 项目结构审核与收束

本文只记录 `agens-web` 当前结构边界、已完成清理和剩余技术债。历史批次细节进入 `CHANGELOG.md`；不要把旧草案、旧原型或旧验收记录当作当前事实。

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
- 2026-06 历史草案、旧 Alpha 复盘和 UI 原型资产已从 `docs/archive/` 清理；当前状态只看权威文档，历史变更看 `CHANGELOG.md`。

## 当前已验证事实

- 当前本地代码基线：已包含脱敏模型诊断、P1 可见反馈修复和 2026-07-04 属性尺度清理。
- 本地 PostgreSQL 测试库目标：`127.0.0.1:55432/agens_web_test`。
- 最新自动化门禁已通过：`compileall`、`tests\web` 68 passed、全量 `pytest -q` 480 passed、前端 build、`git diff --check`。
- 用户级模型设置已落地：个人配置按 `user_id` 加密隔离，系统默认保留在 `model_config`，运行时按当前 session/user 解析模型配置，不再通过进程级 `AGNES_API_KEY` 注入用户 key。
- 角色创建属性池已按 `GAME_MODE_SPEC.md` §4.1 落地：手动 2-8/总和 30，随机 0-10/总和 30。
- 运行时属性尺度已审计并收敛为 0-10：`DEFAULT_ATTRIBUTES` 为 5，境界小层推进、`GameSession` delta/save、World Builder 入局、跨局奖励和 catalog 种子不再以 50/100 作为正常尺度；旧 0-100 仅作兼容迁移输入。
- 本地真实 Chrome P0 验收已通过：`local-visible-20turn-20260701-final2` 完成注册/登录、系统默认开局、角色创建、20/20 choice non-fallback、存档/读档。证据位于 `output/playwright/`，默认不提交。
- 生产 P0 已通过：服务器线程部署 `25ad3d15` 后，容器 healthy，Alembic `20260622_0005`，`user_model_configs` 存在，public/origin health 和 catalog 正常，日志敏感标记扫描为 0；一次性真实账号注册、登录、开局、选择、存档、读档、跨会话恢复均通过；生产 start 和至少 1 次 choice 均为 non-fallback，choice 后 `turn_count=1`。
- 最新本地代码已加入脱敏模型性能观测：`model_result` 只暴露布尔/数值诊断，不输出 raw model/base_url/key；下一步需要 Chrome 20 回合采样定位慢因。

## 剩余 P0 风险

| 问题 | 当前状态 | 下一步 |
| --- | --- | --- |
| 生产 P0 回归风险 | 2026-07-02 生产 start+choice non-fallback 已通过。P0 当前不阻塞玩法迭代。 | 后续每次生产部署、模型配置变更或 provider 变更仍需由服务器线程复跑 health/catalog/account flow/start+choice non-fallback，且不输出 secrets。 |
| Chrome 验收与 pytest 共库并发 | `tests\web` 会逐测清空 `TEST_DATABASE_URL`，与可见 Chrome 共用库会造成 users/sessions/game_turns 突然归零的假象。 | Chrome 验收使用独立 DB，或确认无 pytest 并发后再跑。 |

## 剩余 P1 技术债

| 问题 | 风险 | 处理方向 |
| --- | --- | --- |
| live model 响应慢 | 最新已验收 Chrome run 平均回合耗时约 48.2s、最大约 153.2s。 | 用当前脱敏诊断跑 20 回合采样，再决定压缩 history、收窄 judge、减少 repair 或调整 provider。 |
| narrator repair / judge 依赖 | 多回合依赖修复和 mismatch suppression，说明结构化输出质量仍不稳。 | 收紧 narrator 输出契约和 parser；只在权威状态变更场景触发 judge。 |
| 20 回合内容体验不足 | 目标感、阶段奖励、世界变化和路线差异仍弱。 | 加 0-16 岁开场编年史、3-5 回合反馈、四类事件池，减少重复闭关/突破循环。 |
| 叙事与权威状态落账 | 关键道具、功法、属性、称号、关系、伤势、寿元、境界变化仍可能文字有而系统无。 | 结构化落账、自然改写或压制可见叙事；模型不得决定权威数值。 |
| `GameEngine` 偏大 | 回合、突破、兜底、模型失败等职责集中。 | 只按主流程需要拆模型失败、本地故事、突破 helper，避免大拆。 |
| `WebGameService` 边界需收束 | API 编排、持久化和错误映射仍集中。 | 抽私有 helper，不优先大拆 router。 |
| `database_postgres.py` 偏大 | SQL、row shaping、测试 DDL 历史包袱仍多。 | 抽 catalog/progress/turn helper，不改 schema。 |
| 前端样式集中 | 后续 UI 迭代容易互相影响。 | 按页面/组件逐步拆样式，配合 Chrome 截图验收。 |

## 剩余 P2 工作

- 继续固化本地 PostgreSQL 启动/恢复说明；当前已有 `scripts/start_local_pg.ps1`，仍需保持 stale `postmaster.pid`、端口占用、日志权限的处理说明。
- `output/playwright/`、截图、JSON、NDJSON、CSV 证据默认忽略，不提交临时验证产物。
- 生产侧继续做日志脱敏、限流、Cookie/Origin、备份恢复演练和索引评审。
- 当前文档只写当前事实和下一步；历史细节保留在 `CHANGELOG.md`。

## 成功与失败经验

成功经验：

- 本地、生产、代码修改必须拆开验收；本地 20 回合 non-fallback 不能替代生产 non-fallback。
- 生产变更前先做包 hash、敏感文件名扫描、app/PG 备份、`MODEL_CONFIG_SECRET` present/missing 检查，再部署和迁移。
- 生产报告只输出状态、revision、表名、HTTP 状态、fallback 布尔和备份路径，不输出账号、cookie、邀请码、数据库 URL 或模型 key。
- 账号注册/登录/存档/读档和 live model 是两条不同门禁，不能混成一个“生产通过”。
- 观测数据不是性能修复；必须用 Chrome 采样证明慢因后再改。
- 数据库结构治理要先查实际 PG metadata、Alembic 和运行时写入路径，再决定是否改约束；中文注释这类元数据变更应走 Alembic，并用测试确认真实落库。
- PostgreSQL 的 `text` 不是默认性能问题；优化优先级应来自慢查询、索引、分页和大字段读取模式，而不是批量改 `varchar(n)`。

失败教训：

- 服务健康和账号流通过不代表 live model 成功；`fallback_active=true` 且 `turn_count=0` 仍是阻断问题。
- 验收脚本自身可能失败，必须区分脚本 bug 和产品 bug；脚本要尽量短、可复核、输出脱敏摘要。
- 浏览器证据必须机器可读；损坏 JSON 会削弱后续自动审计可信度。
- UI 问题需要真实浏览器看页面，单靠 API 不会暴露。
- 历史草案留在当前文档树会诱导后续智能体误读；清理后只保留权威文档和 changelog。
- `game_turns.run_id` 的名字容易被误读成终局 `game_runs(id)` 外键；当前运行时它等于 `session_id`，贸然加外键会阻断局中回合落库，后续若要强关系必须先做语义迁移。

## 验证入口

```powershell
cd D:\chat\agens-web
F:\pg\bin\pg_isready.exe -h 127.0.0.1 -p 55432
.\scripts\start_local_pg.ps1
$env:TEST_DATABASE_URL = "postgresql+psycopg://agens_test@127.0.0.1:55432/agens_web_test"
.\.venv\Scripts\python.exe -m compileall -q src tests web scripts migrations
.\.venv\Scripts\python.exe -m pytest -q tests\web
.\.venv\Scripts\python.exe -m pytest -q
cd web\frontend-react
npm.cmd run build
```

## 文档边界

- 当前入口看 `docs/INDEX.md`。
- 当前运行链路看 `docs/RUNTIME_FLOW.md`。
- 游戏规则规格看 `docs/GAME_MODE_SPEC.md`。
- 模块地图看 `docs/ARCHITECTURE.md`。
- 下一步工作看 `docs/NEXT_GOVERNANCE_BACKLOG.md`。
- 生产复验看 `docs/PRODUCTION_V5_MIGRATION_CHECKLIST.md`。
- 历史变更看 `CHANGELOG.md`。
