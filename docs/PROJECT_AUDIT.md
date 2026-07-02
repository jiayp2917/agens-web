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
- 2026-06-30 本地自动化基线：`pg_isready` confirmed `127.0.0.1:55432`; `tests\web` 64 passed；带 `TEST_DATABASE_URL` 的全量 `pytest -q` 438 passed；前端 build 通过。
- 已修复本地可见 Chrome 发现的主流程问题：合法 A/B/C/D 选择不应 HTTP 200 但不推进；叙事/状态 mismatch 时保持 `game_turns` 连续；fallback 过渡回合会记录。
- 角色创建属性池已按 `GAME_MODE_SPEC.md` §4.1 落地：手动 2-8/总和 30，随机 0-10/总和 30。
- 2026-06-30 复核修复：随机角色创建会提交并使用前端展示的随机属性池；从随机切回手动会恢复合法手动池；空 Key 的首次模型配置不会生成遮蔽系统默认的用户配置。
- `tests/unit/engine/test_playable_gap_locks.py` 已转为通过型玩法 guard；原 4 个 P1 gap 已修复并由 T1-T4 锁定。
- 2026-06-30 本地真实 Chrome 跟进验收：普通账号注册/登录、系统默认 Agens 开局、角色创建、存档/读档通过；重复选项前缀与内部 mismatch 文案未再出现；第 7 回合 narrator incomplete output 进入 local story fallback，未通过 20 回合 live-model 验收。摘要证据位于 `output/playwright/agens-web-local-visible-validation-summary-20260630.json`，默认作为生成证据不提交。
- 本轮本地修复已针对上述第 7 回合失败类补 parser/choice recovery：narrator 可恢复 fenced/bare JSON、JSON-only payload、中文 A/B/C/D 选项行；有 live 叙事但选项格式坏时不再直接进入 local story，而是保留规则回合并补齐语义选项；编年史渲染会清理 stray markdown/JSON fence。2026-07-01 早期复验曾停在第 4 个 choice fallback；`local-visible-20turn-20260701-rerun4` 曾通过 20/20 non-fallback。子智能体复核后又补强两点：缺 `<state_update>` 不再伪装成空 delta，叙事/状态 mismatch 被压制后会回退通用 choices。中间复验 `local-visible-20turn-20260701-final` 在第 1 回合因 repair 输出多余 `}` 进入 fallback；窄修复该 provider drift 后，`local-visible-20turn-20260701-final2` 通过 20/20 non-fallback，注册/登录、系统默认开局、角色创建、存档/读档均通过。证据位于 `output/playwright/local-visible-20turn-20260701-final2.{json,ndjson,csv}` 与 `output/playwright/local-visible-20turn-20260701-final2-source.json`，默认不提交。
- 子智能体复核后补强的边界：有 choices/state 但无叙事正文仍判为 incomplete；repair 结果必须同时包含叙事、结构化状态和 choices 才接受；语义补齐 choices 只作为不断流的降级恢复，不等同完整模型输出质量；系统级物品获得类叙事必须有结构化 `inventory_add`，否则压制可见叙事并按基础规则结算。
- 2026-06-30 本地 headed sanity 复核通过：访客新游戏、角色创建、start、一回合 choice 均通过，未见 fallback banner。证据位于 `output/playwright/agens-web-local-sanity-20260630-*`，默认不提交。
- 2026-06-30 生产批次通过部署与账号流：Alembic 已到 `20260622_0005`，`user_model_configs` 存在，public/origin health、catalog、容器健康和日志敏感标记扫描通过；一次性真实账号注册、登录、存档、读档、跨会话恢复通过。production live model 当时未通过：start non-fallback，但一回合 choice 返回 `fallback_active=true` 且 `turn_count=0`。
- 2026-06-30 生产 fallback 根因已脱敏定位并本地修复：旧 `model_config` 系统行没有 `api_key_encrypted` 时遮蔽了容器 env 系统 key，导致 narrator runtime `key_set=false`。本地兼容逻辑已改为此类旧行不遮蔽 env key。
- 2026-07-02 服务器线程部署 `25ad3d15` 后完成生产 P0 脱敏验收：容器 healthy，Alembic `20260622_0005`，`user_model_configs` 存在，public/origin health 和 catalog 正常，日志敏感标记扫描为 0；一次性真实账号注册、登录、开局、选择、存档、读档、跨会话恢复均通过；生产 start 和至少 1 次 choice 均为 non-fallback，choice 后 `turn_count=1`。历史 choice fallback 不再是当前 P0 阻塞。

## 剩余 P0 风险

| 问题 | 当前状态 | 下一步 |
| --- | --- | --- |
| 生产 P0 回归风险 | 2026-07-02 生产 start+choice non-fallback 已通过。P0 当前不阻塞玩法迭代。 | 后续每次生产部署仍需由服务器线程复跑 health/catalog/account flow/start+choice non-fallback，且不输出 secrets。 |
| Chrome 验收与 pytest 共库并发 | `tests\web` 会逐测清空 `TEST_DATABASE_URL`，与可见 Chrome 共用库会造成 users/sessions/game_turns 突然归零的假象。 | Chrome 验收使用独立 DB，或确认无 pytest 并发后再跑。 |

## 剩余 P1 技术债

| 问题 | 风险 | 处理方向 |
| --- | --- | --- |
| live model 响应慢且结构化输出不稳 | 2026-07-01 `final2` 已通过 20/20 non-fallback，但平均回合耗时约 48.2s、最大约 153.2s；后端日志显示多回合依赖 narrator repair，且有 read timeout/retry 与叙事/状态 mismatch 被拒绝的 P1 质量风险。 | 继续优化提示词、超时、重试/降级提示、流式反馈、结构化输出稳定性和模型内容质量；fallback 仍不能算 live-model 成功。 |
| 叙事与状态仍可能不一致 | 本轮已隐藏内部 mismatch 文案；普通编年史物品叙事不强制进 inventory，但系统级“获得/得到/收下/拿到”物品收益缺少结构化 delta 会被压制。状态年龄与编年史年龄仍需统一。 | 继续收紧权威状态字段、Judge、`apply_delta()` 和年龄来源；系统级收益要结构化或自然改写。 |
| 编年史输出格式污染 | 早期跟进验收中出现可见 stray markdown fence ` ```json`；当前代码已在 parser 与 chronicle display 两侧清理常见 fence，`final2` 未因该问题停止。 | 继续在真实 Chrome 验收中观察是否仍出现 fence/JSON 标记。 |
| 游玩内容弱 | 金灵根路线发散到雷法/水法，目标感和阶段奖励不够稳定。 | 先设计主线目标、阶段事件、奖励落账，再迭代内容。 |
| 状态展示不足 | 气运增长到 23 缺解释，轻伤、雷果等叙事结果没有稳定状态/物品展示。 | 明确属性成长上限/展示规则；轻伤、道具、功法等要落账或改写成非确定收益。 |
| `GameEngine` 仍偏大 | 仍承担回合、突破、兜底、模型失败等多职责。 | 只按主流程需要拆模型失败、本地故事、突破 helper，避免大拆。 |
| `WebGameService` 边界仍需收束 | API 编排、持久化和错误映射仍集中。 | 继续抽私有 helper，暂不优先大拆 router。 |
| `database_postgres.py` 仍偏大 | SQL、row shaping、测试 DDL 历史包袱仍多。 | 继续抽 catalog/progress/turn helper，不改 schema。 |
| 前端样式仍有集中风险 | 后续 UI 迭代容易互相影响。 | 按页面/组件逐步拆样式，配合 Chrome 截图验收。 |

## 剩余 P2 工作

- 继续固化本地 PostgreSQL 启动/恢复说明；当前已有 `scripts/start_local_pg.ps1`，还缺 stale `postmaster.pid` 恢复文档。
- 决定 `output/playwright/`、截图和 JSON 证据的归档/忽略策略；默认不提交临时验证产物。已新增 strict JSON/NDJSON/CSV evidence writer，`scripts/local_visible_playtest.cjs` 已接入它。
- 生产侧继续做日志脱敏、限流、Cookie/Origin、备份恢复演练和索引评审。
- 历史文档只保留在 `docs/archive/` 和 `CHANGELOG.md`，当前文档只写当前事实和下一步。

## 2026-06-30 成功与失败经验

成功经验：
- 本地、生产、代码修改必须拆开验收；本地 20 回合 non-fallback 不能替代生产 non-fallback。
- 生产变更前先做包 hash、敏感文件名扫描、app/PG 备份、`MODEL_CONFIG_SECRET` present/missing 检查，再部署和迁移。
- 生产报告只输出状态、revision、表名、HTTP 状态、fallback 布尔和备份路径，不输出账号、cookie、邀请码、数据库 URL 或模型 key。
- 账号注册/登录/存档/读档和 live model 是两条不同门禁，不能混成一个“生产通过”。
- 2026-07-02 生产 P0 通过的关键是部署后同时验证账号流和 start/choice non-fallback；HTTP 200、容器 healthy 或账号流单独通过都不足以替代 live-model 验收。

失败教训：
- 服务健康和账号流通过不代表 live model 成功；`fallback_active=true` 且 `turn_count=0` 仍是阻断问题。
- 验收脚本自身可能失败，必须区分脚本 bug 和产品 bug；脚本要尽量短、可复核、输出脱敏摘要。
- 浏览器证据必须机器可读；损坏 JSON 会削弱后续自动审计可信度。
- UI 问题（如 `A：A：...` 重复前缀）需要真实浏览器看页面，单靠 API 不会暴露。

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

- 当前运行链路看 `docs/RUNTIME_FLOW.md`。
- 游戏规则规格看 `docs/GAME_MODE_SPEC.md`。
- 模块地图看 `docs/ARCHITECTURE.md`。
- 下一步工作看 `docs/NEXT_GOVERNANCE_BACKLOG.md`。
- 生产迁移看 `docs/PRODUCTION_V5_MIGRATION_CHECKLIST.md`。
- 历史复盘和 UI 原型看 `docs/archive/2026-06-governance/`。
