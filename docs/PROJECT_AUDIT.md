# 项目结构审核与收束

本文是 Web-only 项目的结构边界、瘦身清单和技术债队列。本目录只做浏览器版本。

> **2026-06-25 更新**：已执行审计计划（`zesty-popping-graham.md`）的**方案 C**——删除 `database_sqlite.py`，数据库统一为 PostgreSQL。P0 安全修复、P1 死代码清理、P2 PG-only 合并、P3 部分去重均已完成，详见 `CHANGELOG.md`（2026-06-25）。下文双轨分析与「建议方案 A」为历史记录，方案 C 为实际落地结果。

> **2026-06-28 更新**：用户级模型配置治理已本地落地并提交 `44519d7`。`/api/settings/model` 为登录用户个人配置接口，`/api/admin/settings/model` 为系统默认配置接口；PostgreSQL 新增 `user_model_configs` 并以 `MODEL_CONFIG_SECRET` 加密存储 key。最新本地验证：`tests\web` 59 passed，全量 `pytest -q` 420 passed / 1 xfailed，前端 build 通过。

> **2026-06-26 更新**：本地 Web/API 测试已接入安全本地 PostgreSQL 测试库，`TEST_DATABASE_URL=postgresql+psycopg://agens_test@127.0.0.1:55432/agens_web_test` 时 `tests\web` 真实执行并通过 `50 passed`，全量 `pytest -q` 为 `415 passed`。当前事实口径为 PostgreSQL-only；下方 2026-06-24 的 SQLite smoke 仅是历史证据，不代表当前运行方式。

> **2026-06-27 更新**：本地主流程/UI 面板清理后的最新验证为 `compileall -q src tests web scripts migrations` 通过，`pytest -q tests\web` 为 `54 passed`，全量 `pytest -q` 为 `416 passed`，前端 `npm.cmd run build` 通过。本地自动化验证不代表 production live-model 成功；fallback 仍不能算 live-model 验收。

## 当前边界

- 产品入口是浏览器 Web UI + FastAPI 后端。
- 当前核心游戏逻辑继续复用 `src/agens_novel/`。
- 当前只开放游戏模式 v5 Alpha：A/B/C/D 四按钮固定语义，A 稳妥 / B 机遇 / C 风险 / D 气运。
- 引导模式、小说模式只作为禁用入口保留，不开放运行逻辑。
- 模型失败、无 key、无有效选项时，用户可选择本地故事兜底继续或结束本局。
- 境界顺序固定为：练气、筑基、金丹、元婴、化神、合体、大乘、渡劫、飞升。

## 2026-06-24 当前状态

- 本地 React 主入口仍是唯一产品入口；旧 `web/frontend` 不再存在。
- UI 重构已进入截图验收后的细修阶段：首页 QQ 群左侧标识已改为独立图片资产 `web/frontend-react/public/assets/xian-game-icon-256.png`；角色创建页“命数”区已选择并落地 `docs/ui-prototypes/fate-collapse-prototype.html` 的方案 A 摘要式折叠卡。
- 编年史年份显示已收束为“界面标题为权威”：后端事件记录补充当前年龄，前端清理叙事正文开头的 `玄历/玄元历...年` 前缀，避免标题与正文纪年冲突；Narrator 提示词同步要求正文不要自带年份前缀。
- 当前浏览器自动验收应使用 Chrome DevTools MCP 或外部 Chrome；Codex 内置浏览器在本机仍存在 WebView2/GPU/虚拟显示驱动相关闪退风险，不作为可靠验收工具。
- 本地未跟踪 `output/playwright/` 属于浏览器/截图运行产物，不是产品源码；提交前应单独决定删除或加入忽略规则。
- 第一批最低风险复杂度收敛已完成：`web/backend/app.py` 将 session 类 endpoint 重复的 `KeyError` / `PermissionError` / `ValueError` 转 HTTP 异常样板收束到 `service_call()`，保持原 404 / 403 / 400 行为不变。
- 第二批最低风险复杂度收敛已完成：`web/backend/database_common.py` 承接 catalog seed 来源、catalog row JSON 准备和 player progress 摘要。2026-06-25 Option C 后 `database_sqlite.py` 已删除，当前仅 `database_postgres.py` 继续复用这些 helper。
- 第三批最低风险复杂度收敛已完成：`web/frontend-react/src/lib/chronicle.ts` 承接编年史正文清理、年龄/年份推导和当前纪年读取，`GamePage.tsx` 只保留渲染与交互编排。
- 第四批最低风险复杂度收敛已完成：`WebGameService.choose()` 与 `WebGameService.act()` 共用 `_advance_turn()`，把 engine action、settled-turn 落账、session persist 和 response shaping 收束到同一路径；最小 Web API 流程同时覆盖 `/choice` 与 `/action`。
- 2026-06-26 本地 P0/P1 收口：`web/backend/app.py` 的 Pydantic 请求模型拆到 `web/backend/app_models.py`；`web/backend/database_postgres.py` 的 test-only auto-DDL 语句拆到 `web/backend/database_postgres_schema.py`；`web/backend/service.py` 的死亡总结计算拆到 `web/backend/service_summaries.py`；新增 `tests/unit/engine/test_flow_failure_paths.py` 覆盖 StartFlow / TurnFlow / BreakthroughFlow 模型失败 stop path。
- Chrome 真实浏览器 smoke 发现并修复了本地兜底场景的编年史纪年停滞：模型网络失败后点击“继续本局”，回合 1 现在显示 `玄元历 2 年 · 回合 1`，最新卡片也显示 `玄元历 2 年`。
- Chrome 移动 smoke 发现并修复了随机角色属性显示/语义不一致：随机属性可能高于手动上限 80，现已由 disabled range 改为只读 meter，`aria-valuenow` 与可见数值一致。

最近一次本地验证结果：

- `.\.venv\Scripts\python.exe -m compileall -q src tests web scripts migrations`：通过。
- `.\.venv\Scripts\python.exe -m pytest -q tests\web`（设置本地 `TEST_DATABASE_URL`）：`54 passed`。
- `.\.venv\Scripts\python.exe -m pytest -q tests\unit\engine\test_flow_failure_paths.py tests\unit\engine\test_game_engine_turn.py tests\unit\engine\test_game_engine_setup.py tests\unit\engine\test_game_engine_state.py`：`56 passed`。
- `.\.venv\Scripts\python.exe -m pytest -q tests\unit\game\test_database_common.py tests\unit\game\test_game_turns_storage.py tests\web\test_web_api.py::test_postgres_database_url_smoke`：`13 passed`。
- `.\.venv\Scripts\python.exe -m pytest -q`（设置本地 `TEST_DATABASE_URL`）：`416 passed`。
- `cd D:\chat\agens-web\web\frontend-react; npm.cmd run build`：通过，1603 modules / 23.69 kB CSS / 189.87 kB JS。
- `.\.venv\Scripts\python.exe -m pytest -q tests\web\test_frontend_contract.py tests\web\test_web_api.py::test_session_routes_map_service_errors`：`24 passed`。
- `.\.venv\Scripts\python.exe -m pytest -q tests\web\test_web_api.py::test_web_api_minimum_game_flow tests\web\test_web_api.py::test_session_routes_map_service_errors`：`9 passed`，覆盖 `/choice` 与 `/action` 共用回合推进路径。
- 生产公网 health/catalog curl 属于服务器只读验证证据，不计入本地自动化验收；详见下方生产状态段。
- Chrome DevTools MCP：桌面 1280x900 与移动 375x812 均可完成访客新游戏、角色创建、进入游戏、模型失败兜底、继续本局；修复后移动截图保存在 `D:\2917\agens-web-mobile-smoke-after-fix.png`。
- Chrome DevTools MCP：375x812 随机角色属性复核通过，六项属性均为只读 meter，`aria-valuenow` 与可见输出一致。
- Chrome DevTools MCP（2026-06-24 历史证据）：桌面本地账号流当时使用临时 SQLite 和本地一次性邀请码完成注册/登录、账号新局、保存 `slot_1`、读取 `slot_1`，`/api/saves` 返回 `slot_1` / `存档测试` / `turn_count=0`。Option C 后的当前 PostgreSQL 复验见下方 2026-06-26 证据。
- Chrome DevTools MCP：2560x1440 emulation 通过首页、角色创建和初始游戏页布局检查，无横向溢出；角色创建三栏、开始按钮、游戏状态栏、故事面板和 A/B/C/D 均在视口内。截图证据：`D:\2917\agens-web-2k-game-smoke.png`。
- Chrome DevTools MCP（2026-06-24 历史证据）：本地 live model smoke 当时使用临时 SQLite 与仅检查“环境变量是否存在”的方式启动本地服务；访客开局后点击 A，`/api/sessions/{id}/choice` 返回 HTTP 200，`fallback_prompt.active=false`，页面推进到回合 1 并刷新叙事与 A/B/C/D 选项。Option C 后的当前 PostgreSQL live-model 复验见下方 2026-06-26 风险说明。
- Chrome against local PostgreSQL（2026-06-26 当前证据）：访客创建/开局/一回合、账号邀请码注册/登录/账号新局/保存 `slot_1`/读取 `slot_1` 均通过；2560x1440 与窄屏约 500px 均无横向溢出。截图证据：`D:\chat\agens-web\output\agens-web-local-pg-account-ui-20260626.png`、`D:\chat\agens-web\output\agens-web-local-pg-2k-20260626.png`、`D:\chat\agens-web\output\agens-web-local-pg-mobile-500w-20260626.png`。
- Local live-model（2026-06-26 当前证据）：访客一回合返回 HTTP 200，但耗时约 63 秒，且结构化叙事诊断不完整；这只能说明请求没有崩溃，不能作为模型质量和流畅游玩验收。
- P0 生产 v5 本地交付包已准备：`D:\chat\outputs\packages\agens-web\agens-web-11ae5e9-20260624-173644.zip`，commit `11ae5e9699277ce08b42a9331932354895922149`，SHA256 `526b8b6cbbc1abd60b1a03b1d73369778abf8c723d439579526532d9744017ad`；manifest 见 `D:\chat\outputs\packages\agens-web\agens-web-11ae5e9-20260624-173644.manifest.md`。包由 `git archive HEAD` 生成，未包含 `.env`、`production.env`、依赖目录、缓存或本地前端 `dist`。

未完成确认：

- 服务器线程 `019ee2ee-823e-7441-bdaa-881782da7949` 已完成部署前只读预检：包 hash 可见且匹配，公网 health/catalog、内部 origin health、容器健康、staging/backup 路径候选均确认；未执行备份、部署、迁移、重启、删除、sudo 或 secrets 读取。该结果只说明“可以进入待批准部署窗口”，不代表生产通过。
- 用户批准后的 2026-06-24 P0 生产 v5 部署批次未通过：包上传与服务器 SHA256 校验通过，PostgreSQL 备份 `/srv/jiayp/backups/postgres/postgres-20260624-180554.sql.gz` 和 app 备份 `/srv/jiayp/backups/agens-web/agens-web-app-20260624-180650.tar.gz` 均已生成并通过可读性检查；`/srv/jiayp/apps/agens-web` 已替换为新包源码，旧目录保留在 `/srv/jiayp/apps/agens-web.pre-v5-20260624-180650`。随后 Docker build 在 `pip install -r requirements.txt` 阶段因无法解析 `langchain-core>=0.3.0` 停止；未执行 Alembic、未重启容器、未回滚。失败后只读确认旧运行容器仍 healthy，公网 health/catalog 正常，生产 Alembic 仍为 `20260621_0002`。
- 停止点只读诊断显示：当前源码仍包含 `langchain-core>=0.3.0`，Docker runtime 为 `python:3.12-slim`，临时 `python:3.12-slim` 容器可以看到 `langchain-core` 且包含 `0.3.0` 到 `1.4.8`；因此更可能是构建当时的 pip 索引/网络临时异常，而不是依赖约束或 Python 3.12 本身错误。
- build-only 重试已通过 host-network fallback，生成镜像 `sha256:f2d2b86e3de0c9aff5131ed238c84eb435cb0d31983e5e4629b8b75add4d6c15`；随后的生产迁移/重启批次已将 Alembic 升级到 `20260622_0004` 并确认 `game_runs` / `game_turns` / `player_progress` 存在，但新容器因 `deploy/docker-entrypoint.sh` 在镜像内为 CRLF 行尾导致 `env: 'sh\r': No such file or directory`，进入 `Restarting (127)`，公网 health 一度为 HTTP 502。
- 已批准的 entrypoint CRLF hotfix 已通过：服务器仅替换 `.gitattributes`、`Dockerfile`、`deploy/docker-entrypoint.sh`，窄备份在 `/srv/jiayp/backups/agens-web/entrypoint-crlf-hotfix-20260624-185815/`；新镜像 `sha256:445367f496bf3b1acb8b091442f775b9c74240251cc19efdfab2d45562dbc791` 运行 healthy，origin/public health HTTP 200，public catalog talents 10 条，Alembic `20260622_0004` 与三张 v5 表仍存在，日志敏感标记扫描为 0，访客开局和一回合均 HTTP 200。
- 本地已针对该启动失败做源头硬化：`.gitattributes` 强制 shell 脚本和 Dockerfile 为 LF，Dockerfile 复制 entrypoint 后执行 `sed -i 's/\r$//'`，防止后续构建再次带入 CRLF。
- 375px 历史链路、2026-06-26 PostgreSQL 本地账号链路、2K 和窄屏布局均已验证；本地 live-model 请求仍存在约 63 秒延迟和结构化输出不完整风险。生产账号链路仍未验收，因为没有安全非 secret 测试账号路径；生产 live model 成功也未验收，因为访客 smoke 返回 `fallback_prompt_active=true`，只能证明 fallback 游玩链路恢复。
- 当前未完成项集中在生产账号链路、生产 live model 成功验收、公开 Alpha 观察、备份/恢复演练、PostgreSQL 测试库启动脚本固化、后续复杂度治理和模型质量/性能治理。

## 目标架构

| 层级 | 边界 | 主要目录 |
| --- | --- | --- |
| Web 交互层 | 浏览器展示、点击、设置、存读档入口，不直接改游戏状态。 | `web/frontend-react/` |
| API 层 | 会话、开局、回合、存读档、设置、认证和脱敏日志。 | `web/backend/` |
| 游戏核心层 | Agent 调用、规则校验、状态落账、境界、战斗、本地故事兜底。 | `src/agens_novel/` |
| 数据层 | 用户、会话、存档、chat_history、模型配置摘要。 | PostgreSQL 单后端（Option C 后 SQLite 已移除） |

## Agent 职责

- World Builder：只负责角色创建后的世界开局、开场叙事和开场 A/B/C。
- Narrator：只负责每回合叙事、结构化状态建议和下一轮 A/B/C。
- Judge：只负责审核状态变化是否合理；不负责生成剧情，也不直接改状态。
- LLM client：只负责 OpenAI 兼容 HTTP 调用、超时/错误和脱敏日志，不承载游戏规则。

## 目标调用链

```text
Browser UI
  -> FastAPI
  -> WebGameService / WebRunner
  -> GameEngine
  -> World Builder / Narrator / Judge
  -> GameSession.apply_delta
  -> PostgreSQL sessions / saves / game_turns
  -> FastAPI response
  -> Browser UI
```

关键约束：

- Web 前端只能通过 API 调用游戏逻辑。
- `GameEngine` 是唯一游戏逻辑入口。
- 结构化状态只通过 `GameSession.apply_delta()`、境界系统和突破逻辑生效。
- Web 产品入口不再展示状态/背包/功法/地图/任务/境界工具面板；对应运行时状态字段仅保留给规则、奖励、兜底和旧存档兼容使用，前端不得自行伪造。

## 瘦身清单

已删除或替换：

- 移动端源码和打包配置
- 设备验证相关文档
- 移动端 UI 测试
- 移动端运行产物说明
- 本项目不再使用的 BGM 适配层
- 旧纯 HTML/CSS/JS 前端 `web/frontend/`
- 游戏模式 combat 子系统：`src/agens_novel/game/combat.py` 与 `config/prompts/system/combat_narrator.md`（v5 已切换到事件判定）
- 旧的 `src/agens_novel/persistence/` 空壳（早期 save_manager 已下线）
- 早期 Web-only 路线文档 `docs/WEB_ITERATION_PLAN.md`
- Android APK 打包 skill `.agents/skills/build-apk/`（非本仓库职能）
- 冗余 `.venv311/` 虚拟环境（与 `.venv/` 共存）
- `web/frontend-react/.tmp/` 一次性 Playwright smoke 脚本
- 孤立 `__pycache__/*.pyc`（combat / persistence / test_combat / test_bgm 来源已删）

保留：

- `src/agens_novel/`
- `config/prompts/system/`
- 核心规则测试
- Agent、LLM、状态、存档相关测试
- Web 后端和前端测试

## 技术债队列

| 优先级 | 问题 | 处理方向 |
| --- | --- | --- |
| P1 | `game_engine.py` 体量过大，承担回合、突破、兜底、存档、模型异常等多类职责。 | 先稳定 Web 服务接口，后续拆出模型失败处理、本地故事 runner、突破流程和存读档调度。 |
| P1 | 叙事与规则状态仍可能不同步，表现为文字获得道具/功法或升层但权威 `GameSession` 未落账。 | 收紧 Narrator delta、Judge 修正、`apply_delta()` 和 Web 状态响应。 |
| P1 | 模型返回文本但缺少结构化选项时，容易进入兜底或阻断流程。 | 保持格式修复重试，并在 API 响应中区分请求失败、输出不完整、审核失败和本地兜底。 |
| P2 | 本地故事兜底只达到最小可玩。 | 改成数据文件化故事节点，逐步扩展多套故事。 |
| P2 | Web 多用户会引入会话隔离和密钥安全问题。 | API 层统一鉴权、限流、脱敏日志和 per-user session 存储。 |
| P2 | FastAPI 路由仍集中在单文件内，但重复 service 异常映射已完成第一步收束。 | 下一步如继续拆路由，应先保持 `service_call()` / 鉴权依赖语义不变，再拆 `auth_router`、`catalog_router`、`session_router`、`settings_router`。 |
| P2（已解决）| ~~SQLite / PostgreSQL 双轨 DDL、SQL 方言和事务边界重复~~ | 方案 C（2026-06-25）删除 SQLite 后端后双轨重复消除；catalog row / progress summary 共享 helper 仍保留在 `database_common.py` |
| P0 | 生产 v5 服务已恢复：Alembic `20260622_0004`、三张 v5 表存在、容器 healthy、origin/public health 200、catalog 10 条、访客开局和一回合 200。但生产账号流未验收，production live model 未验收（访客 smoke 为 fallback）。 | 用安全非 secret 测试账号补验注册/登录/存读档；在不输出 secrets 的前提下补验 production live model，fallback 不能算成功。继续公开 Alpha 日志脱敏、限流、Cookie/Origin 和备份观察。 |
| P2 | PostgreSQL 设计和 Alembic 迁移已经补齐 Alpha 必需表，但生产仍需索引评审、备份恢复和回滚演练。 | 设置 `TEST_DATABASE_URL` 跑空库迁移和账号游玩链路；生产运行时 `AGENS_ENV=production` 自动拒绝 `AGENS_PG_AUTO_DDL=1`；安排维护窗口做回滚演练。 |
| P2 | 访客局只在单进程内存中，容器重启、多 worker 或多副本会丢失。 | Alpha 阶段明确提示；正式多人部署前引入共享会话存储或只允许账号局跨进程恢复。 |
| P2 | 匿名访客仍可能消耗模型额度。 | 增加访客日限额、IP/设备限额、模型预算保护和边缘层限流。 |
| P2 | 本地 PostgreSQL 测试库需要明确启动/清理脚本，避免后续 agent 因缺少 `TEST_DATABASE_URL` 误判为跳过或假绿。2026-06-27 验证前曾遇到 `.tmp\pg-test-20260626-55432` stale `postmaster.pid`，需先确认无 PG 进程再移除并 `pg_ctl start`。 | 将当前 `.tmp` 独立 PG 测试库启动/恢复方式固化为脚本或文档；默认不写真实密码。 |
| P3 | 测试目录需继续从旧产品分类迁移到 Web 分类。 | 保留核心测试，新增 API 和浏览器测试，删除旧 UI 契约测试。 |
| P2 | React 局部组件仍偏重，后续 UI 迭代容易互相影响；`GamePage` 编年史计算已先抽到 `lib/chronicle.ts`。 | P2 已拆分认证、首页、角色创建、游戏页、设置/存档弹窗、模型设置面板、存档槽列表、BGM 和终局页组件；下一步按需继续抽 `CharacterCreatePage` 与 `styles.css`。 |

## 验证入口

```powershell
.\.venv\Scripts\python.exe -m compileall -q src tests web
$env:TEST_DATABASE_URL = "postgresql+psycopg://agens_test@127.0.0.1:55432/agens_web_test"
.\.venv\Scripts\python.exe -m pytest -q tests/web
.\.venv\Scripts\python.exe -m pytest -q
```

## 2026-06-22 Alpha 收口审计

- 当前生产入口使用 `web/frontend-react/dist`；旧 `web/frontend` 已删除，React public assets 位于 `web/frontend-react/public/assets`。
- PostgreSQL 生产 schema 必须由 Alembic 创建。`database_postgres.py` 的 `AGENS_PG_AUTO_DDL` 只允许作为显式兼容开关，不作为生产默认路径。
- Alembic 初始和桥接迁移覆盖运行时会访问的 catalog、死亡奖励和 v5 回合表：`catalog_*`、`run_achievements`、`account_rewards`、`legacy_bonuses`、`game_runs`、`game_turns`、`player_progress`。
- React 主入口 P2 已拆分：认证、首页、角色创建、游戏页、设置存档弹窗、模型设置面板、存档槽列表、BGM 和终局页各自独立组件，归口 `pages/` 与 `components/`。
- 文档分层以 `docs/INDEX.md` 为准：`RUNTIME_FLOW.md` 描述当前运行流程，`GAME_MODE_SPEC.md` 描述游戏模式 v5 规格和实现状态。
- Alpha 复盘和成功/失败经验以 `docs/ALPHA_REVIEW_AND_LESSONS.md` 为准。后续上线报告必须区分本地测试、PostgreSQL smoke、Docker Compose、反代和公网验证。

## 2026-06-23 内测收尾：UI 紧凑 + 寿元语义 + 颜色体系 + 死代码清理

- 首页去冗余：删除 eyebrow 段和 A/B/C/D 描述段；品牌 `jiayp2917` → `jiayp`；删除 `.brand::after` 玉色绿点；`.home-preview` 高度从 470px 降到 360px。1080p 桌面端首屏内可见（无强滚动）。
- 角色创建下拉切换到 6 色（白/绿/蓝/紫/橙/红）体系 + 同色色点：`util.ts` 保留 `rarityToColor`，前端不再把颜色字作为尾随文本展示。
- 游戏页选项按钮压缩：`.choice-list button` 76px → 60px，徽标 32px → 28px；移动端 58px → 56px；叙事面板阅读权重高于按钮。
- 寿元语义修正：`GamePage` 读 `character.remaining_lifespan`（fallback `lifespan - age`，`Math.min` 兜底）；面板摘要改为 `{remainingLifespan}/{lifespanMax} 年`，与 `StatLine` 一致。
- 死代码清理：combat 子系统（`src/agens_novel/game/combat.py` 与 `combat_narrator.md`）、`persistence/` 空壳、`WEB_ITERATION_PLAN.md`、`build-apk/` skill、`web/frontend-react/.tmp/` smoke 脚本、`.venv311/` 冗余虚拟环境、孤立 `__pycache__/*.pyc`、累计 uvicorn 日志全部删除；10 处 `combat` / `persistence` 陈旧注释替换为规则引擎 / 存档语义。
- 契约测试 `tests/web/test_frontend_contract.py` 新增：首页 eyebrow 段删除、品牌精简、6 色字面量、`character.remaining_lifespan` 读取、`{remainingLifespan}/{lifespanMax}` 显示。验证：`compileall -q src tests web` 干净；`pytest -q` 466 passed；`npm run build` 1590 modules / 15.18 kB css / 179.71 kB js。

## 2026-06-27 精确 UI 面板清理

- 首页、角色创建页和游玩页的 `jiayp` 品牌统一使用 `page-brand` 坐标与字号，避免三页左上角位置漂移。
- 角色创建“命数”区保留摘要式折叠卡，但点击当前展开项可以收起；选中态改为圆点内黑点；列表按白、绿、蓝、紫、橙、红排序；玩家可见标签不再追加颜色字。
- 游戏页删除旧工具面板入口：状态、背包、功法、地图、任务、境界 tab，以及 `位置` 摘要和任意面板输出块。核心境界、背包、位置、任务、地图等运行时状态没有删除，只是不再作为 Web 工具面板展示。
- Web 响应中的 `panels` 缩减为 `status_bar`，`GameEngine.get_status/get_inventory/get_skills/get_map/get_quests/get_realm_info/get_equipment_info` 等 Web 面板查询方法下线。
- 编年史展示改为 `年龄：正文` 行式故事展示，弱化旧时间轴卡片视觉。
- 三条故事线入库仍是后续设计：第一版建议复用 `catalog_story_seeds` 承载三条主线，开局绑定其中一条，Narrator 和本地 fallback 围绕主线生成变体；本轮不改 schema、不新增 Alembic、不改 API。

## 2026-06-23 UI 截图二次修复与只读复盘

- 首页：标题保持单行，删除标题下方红点；入口按钮文字按整颗按钮居中，图标左侧辅助；QQ群左侧圆形标识从 `Q` 改为“仙”。
- 角色创建页：命数列表选中标识前置；天赋、灵根、家世改为可收缩区块，列表内部滚动，避免家世内容被 2K 高度挤出；去掉撞色的提示胶囊，改为普通说明文本。
- 终局摘要：`凡人长寿` 成就从“寿元上限 >= 80”改为“实际年龄 >= 80”；注册用户 `/death_summary` 优先基于当前 session 重算摘要，旧数据库成就只作为兜底，避免 16 岁角色显示“撑过八十载”。
- 只读复盘线程 `019ee96e-5685-7223-8796-55c1c7b52205` 结论：P0/P1 仍是 UI 批次验收、生产 Alembic/PG smoke、真实浏览器/公网游玩链路；冗余清理优先缓存、构建产物、历史归档；技术债集中在 React 大样式文件、后端服务边界、生产验收缺口和源码字符串测试假绿。
- 背景素材暂未替换；新首页/角色页背景提示词已补入 `docs/UI_REFACTOR_PLAN.md`。

## 2026-06-24 UI 批次收尾

- 首页 QQ 群左侧标识从文字“仙”升级为独立图片资产，来源为用户提供的 `xian-game-icon-256.png`，放入 React public assets 后通过统一 `assetUrl()` 引用。
- 角色创建页“命数”折叠采用方案 A：摘要卡显示标题、说明、当前选择、颜色点和箭头；一次只展开一个分组，默认展开天赋；展开列表内部滚动，避免撑高整页。
- 编年史年份冲突修复：后端事件增加当前年龄；前端按事件年龄或回合推导卡片年份，并清理正文开头纪年；当前规则是“开局为玄元历 1 年，第一回合后最新记录为玄元历 2 年”。
- 自动浏览器验收工具边界更新：优先使用 Chrome DevTools MCP；Codex 内置浏览器仍记录为本机环境问题，不再作为验收阻断。

## 2026-06-24 安全小重构 handoff

- 边界：只处理 FastAPI route 层重复异常映射，不拆 router、不改 API schema、不改数据库或玩法。
- 改动：`web/backend/app.py` 新增局部 `service_call()`，替换 session/start/choice/action/save/load/end/death_summary 中重复的 `try/except (KeyError, PermissionError, ValueError)`。
- 行为：仍保持 `KeyError -> 404`、`PermissionError -> 403`、`ValueError -> 400`，其他异常继续走既有安全 500 响应。
- 验证：`compileall -q src tests web scripts migrations` 通过；`pytest -q tests\web` 为 `41 passed, 1 skipped`；`pytest -q` 为 `414 passed, 1 skipped`。跳过项仍是未配置 `TEST_DATABASE_URL` 的 PostgreSQL smoke。
- 下一批低风险候选：优先抽 `database_sqlite.py` / `database_postgres.py` 的共享 row/JSON/save/run-turn helper；暂不直接替换 ORM 或改 Alembic 历史。

## 2026-06-24 数据层共享 helper handoff

- 边界：只降低 SQLite / PostgreSQL 双轨的重复 row shaping，不改表结构、不改迁移、不改 `DATABASE_BACKEND` 选择、不读取生产配置。
- 改动：`web/backend/database_common.py` 新增 `catalog_seed_sources()`、`prepare_catalog_row()`、`player_progress_summary()`；`database_sqlite.py` 和 `database_postgres.py` 复用这些 helper 处理 catalog seed、catalog insert 和玩家进度摘要。
- 行为：catalog JSON 字段编码、PostgreSQL `created_at` 默认、SQLite seed 时间戳和缺省 player progress 响应保持原语义。
- 验证：`pytest -q tests\unit\game\test_database_common.py tests\unit\game\test_game_turns_storage.py` 为 `12 passed`；`compileall -q src tests web scripts migrations` 通过；`pytest -q tests\web` 为 `41 passed, 1 skipped`；`pytest -q` 为 `417 passed, 1 skipped`；`npm run build` 通过。
- 剩余风险：`TEST_DATABASE_URL` 未配置导致 PostgreSQL smoke 仍跳过；生产 Alembic/table 状态需以服务器只读验证线程为准；下一批复杂度治理优先抽 `GamePage` 编年史纯函数或补充 route exception mapping 测试。

## 2026-06-24 前端编年史 helper handoff

- 边界：只抽离 `GamePage` 内的编年史纯计算，不改 DOM 结构、不改 CSS、不改 API 请求和玩法状态。
- 改动：新增 `web/frontend-react/src/lib/chronicle.ts`，集中 `cleanChronicleText()`、`buildChronicleRecords()`、`getCurrentChronicleYear()`；`ChronicleItem` 从该模块引用 `ChronicleRecord` 类型；`GamePage` 调用 helper 后继续渲染同一时间线。
- 行为：保留最近 8 条可读事件、正文纪年前缀清理、按事件年份 / 回合 / 推导回合 / 年龄候选取最大正数生成 `玄元历 N 年`、空事件兜底文案和最新标记。
- 验证：`npm run build` 通过；`pytest -q tests\web\test_frontend_contract.py` 为 `16 passed`；Chrome smoke 覆盖桌面与 375px 移动访客兜底流程。
- 剩余风险：真实浏览器 smoke 已覆盖访客流和兜底流，但注册账号存读档、2K 高度截图、长期模型可用链路仍需单独验收。

## 2026-06-24 route service-error mapping handoff

- 边界：只补测试，不改路由实现和 API schema。
- 改动：`tests/web/test_web_api.py` 新增 `test_session_routes_map_service_errors`，覆盖 session/death_summary 路由中 `KeyError -> 404`、`PermissionError -> 403`、`ValueError -> 400`。
- 验证：`pytest -q tests\web\test_web_api.py::test_session_routes_map_service_errors` 为 `8 passed`；合并前端契约测试后 `24 passed`。
- 剩余风险：这覆盖 route 层异常映射，不代表所有服务内部错误分支都有业务级断言。

## 2026-06-24 本地复杂度治理 (P1)

- 边界：只在本仓库内做复杂度收束和文档一致性维护，不重启服务、不做服务器/SSH/Cloudflare/Caddy/Tunnel/DNS/firewall/生产数据库/生产账号/生产 live model 验证，也不做浏览器/Chrome/Playwright 验证。
- 改动：
  - `GameEngine._run_breakthrough_narrator()` 收束 `attempt_breakthrough()` 中 `run_turn_sync` 调用 + try/except 分支，异常 fallback 使用 `source="breakthrough_narrator_exception"`。外部行为和回调 payload 不变；`if result.get("llm_error")` 与 `source="breakthrough_narrator_error"` fallback **仍在 `attempt_breakthrough()` 内联**，是下一批 P1 候选。
  - `WebGameService._require_non_guest_runner(action=...)` 收束 `save`/`load` 重复的 `is_guest_user_id → PermissionError("访客…")` 守卫；其余 6 处 runner 解析保持 `self._runner(session_id, user_id=user_id)` 直接调用。中间版的 `_with_runner()` 薄别名因为没有额外语义，在同一批次中移除。
  - `web/backend/database_common.encode_game_turn_json()` 收束 `database_sqlite.record_game_turn` 与 `database_postgres.record_game_turn` 中 `choices` / `state_delta` / `state_after` 的 JSON 编码；SQL、schema、Alembic revision 均未变更。
  - `CharacterCreatePage.tsx` 折叠三处 `<CatalogGroup>` 块为 `fateGroups` 数据驱动循环；`character-create.css` 合并重复的 `.character-page` 规则。
- 同步清理：
  - 删除 `web/backend/database_common.GAME_TURN_JSON_FIELDS` 常量（仓库内无任何调用点，属于治理批次新增后遗留的未使用常量）。
- 验证：`compileall -q src tests web scripts migrations` 通过；`pytest -q tests\web` 为 `49 passed, 1 skipped`；`pytest -q` 为 `425 passed, 1 skipped`；`pytest -q tests/unit/engine/...` + `tests/unit/game/test_database_common.py` 为 `56 passed`；`npm.cmd run build` 通过（1602 modules / 24.34 kB CSS / 190.37 kB JS）。
- 显式声明：本批次**不**代表生产账号流或 production live model 已验收；P0 生产动作仍由 `docs/PRODUCTION_V5_MIGRATION_CHECKLIST.md` 与 `docs/NEXT_GOVERNANCE_BACKLOG.md` P0 段记录，需要服务器线程处理。
- 剩余风险：上一轮基线中 production account flow 与 production live model 仍未验收；`GameEngine.handle_action` / `new_game` / `_generate_profile_opening` 的模型失败分支 + `attempt_breakthrough` 的 `llm_error` 分支仍是下一批 P1 候选；React 样式文件拆分仍为 P2。
# 2026-06-27 Production Model Hotfix Status

- Model runtime configuration is `AGNES_*`:
  `AGNES_API_KEY`, `AGNES_BASE_URL`, `AGNES_MODEL`, and
  `AGNES_REQUEST_TIMEOUT_SECONDS`. Service/runtime controls remain `AGENS_*`.
- Code commits already landed:
  - `dc05e9f4` enables `repair_incomplete_output=True` in turn and
    breakthrough narrator flows and aligns docs/examples/tests to `AGNES_*`.
  - `2ea29972` removes the BuildKit-only Dockerfile cache mount so the host can
    use the legacy Docker builder.
- Production env was backed up and corrected without printing secret values.
  The effective recovery used a hotfix image path based on the existing
  `jiayp-agens-web:local` image because the full rebuild path was blocked.
- Last successful production smoke before interruption: both local-origin and
  public-origin guest start/choice returned `fallback_active=False`,
  `model_failures=0`, and `choices_count=4`.
- Resume-time recheck on 2026-06-27 could not freshly confirm production:
  TCP/SSH to `192.168.1.250:22` failed. Treat the smoke above as
  last-successful evidence, not a current-state confirmation.
- Still not accepted: production account registration/login/save/load, backup
  restore drill, and a fresh production live-model smoke after SSH reachability
  is restored.

# 2026-06-27 Local Main-Flow Governance Batch

- Scope: local code, docs, and tests only. No SSH, sudo, deployment, production
  DB mutation, production restart, secret reading, or production account flow.
- Player-path fix: `/api/sessions/{id}/choice` now accepts only
  `choice_index` or A/B/C/D letters. Free-text `choice` payloads return 400,
  keeping the v5 fixed-choice contract aligned with the React UI.
- Main-flow fix from local visible-Chrome evidence:
  - Premature breakthrough-intent choices no longer short-circuit into the
    ineligible breakthrough path and return 200 with unchanged `turn_count`.
    When realm rules reject breakthrough, the selected button now continues as
    an ordinary settled turn.
  - Narrative/state mismatch rejection no longer creates a missing turn row.
    The untrusted model narrative/state is discarded, base rule settlement is
    applied, and `game_turns` remains contiguous.
- Complexity reduction: `WebGameService.death_summary()` now delegates to
  live-summary and stored-summary helpers. Public API response shape,
  PostgreSQL schema, and Alembic revisions are unchanged.
- Test coverage: `tests/web/test_web_api.py` now covers rejection of free-text
  `/choice` payloads, successful A-letter choice submission, ineligible
  breakthrough choices advancing/recording a turn, and mismatch rejection
  preserving contiguous turn numbers.
- Follow-up fix: accepted local-story fallback now records the transition turn
  with `local_story_fallback=true`, preventing registered-user `game_turns`
  gaps when the narrator returns no usable choices.
- Local validation after this fix: `compileall -q src tests web scripts
  migrations`, targeted engine/web regressions, `pytest -q tests\web` -> `54
  passed`, full `pytest -q` -> `416 passed`, and frontend `npm.cmd run build`.
- Boundary note: this local batch does not prove production live-model success.
  Fallback still does not count as live-model acceptance; production account
  registration/login/save/load remains a server-thread item.

## 2026-06-28 Model Settings Governance Status

- P0 model-settings product rule is implemented locally: registered-user personal config plus system Agens fallback. Guests receive 401 on `/api/settings/model`.
- Admin system default management is isolated at `/api/admin/settings/model`.
- PostgreSQL now has `user_model_configs` and encrypted key material; `MODEL_CONFIG_SECRET` is mandatory for production decryption/encryption.
- Local validation covers API isolation, no raw key response, encrypted PG storage, fail-closed missing-secret behavior, and frontend settings access. Production deployment and live-model acceptance remain separate server-thread work.
