# 项目结构审核与收束

本文是 Web-only 项目的结构边界、瘦身清单和技术债队列。本目录只做浏览器版本。

## 当前边界

- 产品入口是浏览器 Web UI + FastAPI 后端。
- 当前核心游戏逻辑继续复用 `src/agens_novel/`。
- 当前只开放游戏模式（v5 已实现 / 阶段 7/8 联调收尾中）：A/B/C/D 四按钮固定语义，A 稳妥 / B 机遇 / C 风险 / D 气运。
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
- 第二批最低风险复杂度收敛已完成：`web/backend/database_common.py` 承接 catalog seed 来源、catalog row JSON 准备和 player progress 摘要，`database_sqlite.py` / `database_postgres.py` 复用同一 helper，暂不改 schema、Alembic 历史或运行时后端选择。
- 第三批最低风险复杂度收敛已完成：`web/frontend-react/src/lib/chronicle.ts` 承接编年史正文清理、年龄/年份推导和当前纪年读取，`GamePage.tsx` 只保留渲染与交互编排。
- Chrome 真实浏览器 smoke 发现并修复了本地兜底场景的编年史纪年停滞：模型网络失败后点击“继续本局”，回合 1 现在显示 `玄元历 2 年 · 回合 1`，最新卡片也显示 `玄元历 2 年`。
- Chrome 移动 smoke 发现并修复了随机角色属性显示/语义不一致：随机属性可能高于手动上限 80，现已由 disabled range 改为只读 meter，`aria-valuenow` 与可见数值一致。

最近一次本地验证结果：

- `.\.venv\Scripts\python.exe -m compileall -q src tests web scripts migrations`：通过。
- `.\.venv\Scripts\python.exe -m pytest -q tests\web`：`49 passed, 1 skipped`，跳过项仍是未配置 `TEST_DATABASE_URL` 的 PostgreSQL smoke。
- `.\.venv\Scripts\python.exe -m pytest -q`：`425 passed, 1 skipped`。
- `cd D:\chat\agens-web\web\frontend-react; npm run build`：通过；`tests\web\test_frontend_contract.py` 单文件为 `16 passed`。
- `.\.venv\Scripts\python.exe -m pytest -q tests\web\test_frontend_contract.py tests\web\test_web_api.py::test_session_routes_map_service_errors`：`24 passed`。
- `curl.exe -i --max-time 10 https://game.jiayp2917.xyz/api/health`：HTTP 200，`{"status":"ok"}`。
- `curl.exe -i --max-time 10 https://game.jiayp2917.xyz/api/catalog/talents`：HTTP 200，公网可读 10 条 talent seed。
- Chrome DevTools MCP：桌面 1280x900 与移动 375x812 均可完成访客新游戏、角色创建、进入游戏、模型失败兜底、继续本局；修复后移动截图保存在 `D:\2917\agens-web-mobile-smoke-after-fix.png`。
- Chrome DevTools MCP：375x812 随机角色属性复核通过，六项属性均为只读 meter，`aria-valuenow` 与可见输出一致。
- Chrome DevTools MCP：桌面本地账号流通过，使用临时 SQLite 和本地一次性邀请码完成注册/登录、账号新局、保存 `slot_1`、读取 `slot_1`，`/api/saves` 返回 `slot_1` / `存档测试` / `turn_count=0`。
- Chrome DevTools MCP：2560x1440 emulation 通过首页、角色创建和初始游戏页布局检查，无横向溢出；角色创建三栏、开始按钮、游戏状态栏、故事面板和 A/B/C/D 均在视口内。截图证据：`D:\2917\agens-web-2k-game-smoke.png`。
- Chrome DevTools MCP：本地 live model smoke 通过，使用临时 SQLite 与仅检查“环境变量是否存在”的方式启动本地服务；访客开局后点击 A，`/api/sessions/{id}/choice` 返回 HTTP 200，`fallback_prompt.active=false`，页面推进到回合 1 并刷新叙事与 A/B/C/D 选项。

未完成确认：

- 服务器只读验证已确认公网 health / catalog 和 `agens-web` 容器 healthy；但生产库仍停在 Alembic `20260621_0002`，`game_runs` / `game_turns` / `player_progress` 三张 v5 表缺失。下一次生产验收前必须按部署流程交付新包并执行迁移。
- 375px、桌面和 2560x1440 视口的本地浏览器链路已验证；桌面本地账号注册/登录/存读档已验证；成功 live model 回合已在本地验证。生产 v5 迁移、生产账号链路和生产真实回合仍需继续验收。
- 当前工作区仍有 UI/年份修复相关未提交改动；合入前需要二次确认是否一并提交。

## 目标架构

| 层级 | 边界 | 主要目录 |
| --- | --- | --- |
| Web 交互层 | 浏览器展示、点击、设置、存读档入口，不直接改游戏状态。 | `web/frontend-react/` |
| API 层 | 会话、开局、回合、存读档、设置、认证和脱敏日志。 | `web/backend/` |
| 游戏核心层 | Agent 调用、规则校验、状态落账、境界、战斗、本地故事兜底。 | `src/agens_novel/` |
| 数据层 | 用户、会话、存档、chat_history、模型配置摘要。 | SQLite 起步，后续可迁移 PostgreSQL |

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
  -> SQLite or PostgreSQL sessions / saves / game_turns
  -> FastAPI response
  -> Browser UI
```

关键约束：

- Web 前端只能通过 API 调用游戏逻辑。
- `GameEngine` 是唯一游戏逻辑入口。
- 结构化状态只通过 `GameSession.apply_delta()`、境界系统和突破逻辑生效。
- 背包、功法、地图、任务等面板只能读取 Session/Engine 输出，不自行伪造。

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
| P1 | 叙事与状态仍可能不同步，表现为文字获得/升层但背包、功法、状态未落账。 | 收紧 Narrator delta、Judge 修正、`apply_delta()` 和 Web 状态响应。 |
| P1 | 模型返回文本但缺少结构化选项时，容易进入兜底或阻断流程。 | 保持格式修复重试，并在 API 响应中区分请求失败、输出不完整、审核失败和本地兜底。 |
| P2 | 本地故事兜底只达到最小可玩。 | 改成数据文件化故事节点，逐步扩展多套故事。 |
| P2 | Web 多用户会引入会话隔离和密钥安全问题。 | API 层统一鉴权、限流、脱敏日志和 per-user session 存储。 |
| P2 | FastAPI 路由仍集中在单文件内，但重复 service 异常映射已完成第一步收束。 | 下一步如继续拆路由，应先保持 `service_call()` / 鉴权依赖语义不变，再拆 `auth_router`、`catalog_router`、`session_router`、`settings_router`。 |
| P2 | SQLite / PostgreSQL 双轨仍有 DDL、SQL 方言和事务边界重复；catalog row / progress summary 已先收束为共享 helper。 | 继续用小批次抽公共 row shaping、save summary、run-turn 读取 helper；暂不引入新 ORM 抽象，也不改已部署 Alembic revision。 |
| P0 | 服务器生产库仍停在 Alembic `20260621_0002`，缺少 `game_runs`、`game_turns`、`player_progress`，与当前 v5 代码/本地测试不一致。 | 下一次生产动作必须先打包当前代码、备份、执行 Alembic 迁移到 head，再只读确认 revision 和三张表存在；未完成前不要把公网 v5 表能力视为已验收。 |
| P2 | PostgreSQL 设计和 Alembic 迁移已经补齐 Alpha 必需表，但生产仍需索引评审、备份恢复和回滚演练。 | 设置 `TEST_DATABASE_URL` 跑空库迁移和账号游玩链路；生产运行时 `APP_ENV=production` 自动拒绝 `AGENS_PG_AUTO_DDL=1`；安排维护窗口做回滚演练。 |
| P2 | 访客局只在单进程内存中，容器重启、多 worker 或多副本会丢失。 | Alpha 阶段明确提示；正式多人部署前引入共享会话存储或只允许账号局跨进程恢复。 |
| P2 | 匿名访客仍可能消耗模型额度。 | 增加访客日限额、IP/设备限额、模型预算保护和边缘层限流。 |
| P3 | 测试目录需继续从旧产品分类迁移到 Web 分类。 | 保留核心测试，新增 API 和浏览器测试，删除旧 UI 契约测试。 |
| P2 | React 局部组件仍偏重，后续 UI 迭代容易互相影响；`GamePage` 编年史计算已先抽到 `lib/chronicle.ts`。 | P2 已拆分认证、首页、角色创建、游戏页、设置/存档弹窗、模型设置面板、存档槽列表、BGM 和终局页组件；下一步按需继续抽 `CharacterCreatePage` 与 `styles.css`。 |

## 验证入口

```powershell
.\.venv\Scripts\python.exe -m compileall -q src tests web
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
- 角色创建下拉切换到 6 色（白/绿/蓝/紫/橙/红）字 + 同色色点：`util.ts` 新增 `rarityToColor` + `colorLabel`，`styles.css` 新增 `.rarity-white/-green/-blue/-orange` 并复用既有 `.rarity-purple/-red`。
- 游戏页选项按钮压缩：`.choice-list button` 76px → 60px，徽标 32px → 28px；移动端 58px → 56px；叙事面板阅读权重高于按钮。
- 寿元语义修正：`GamePage` 读 `character.remaining_lifespan`（fallback `lifespan - age`，`Math.min` 兜底）；面板摘要改为 `{remainingLifespan}/{lifespanMax} 年`，与 `StatLine` 一致。
- 死代码清理：combat 子系统（`src/agens_novel/game/combat.py` 与 `combat_narrator.md`）、`persistence/` 空壳、`WEB_ITERATION_PLAN.md`、`build-apk/` skill、`web/frontend-react/.tmp/` smoke 脚本、`.venv311/` 冗余虚拟环境、孤立 `__pycache__/*.pyc`、累计 uvicorn 日志全部删除；10 处 `combat` / `persistence` 陈旧注释替换为规则引擎 / 存档语义。
- 契约测试 `tests/web/test_frontend_contract.py` 新增：首页 eyebrow 段删除、品牌精简、6 色字面量、`character.remaining_lifespan` 读取、`{remainingLifespan}/{lifespanMax}` 显示。验证：`compileall -q src tests web` 干净；`pytest -q` 466 passed；`npm run build` 1590 modules / 15.18 kB css / 179.71 kB js。

## 2026-06-23 UI 截图二次修复与只读复盘

- 首页：标题保持单行，删除标题下方红点；入口按钮文字按整颗按钮居中，图标左侧辅助；QQ群左侧圆形标识从 `Q` 改为“仙”。
- 角色创建页：命数列表选中标识前置；天赋、灵根、家世改为可收缩区块，列表内部滚动，避免家世内容被 2K 高度挤出；去掉撞色的提示胶囊，改为普通说明文本。
- 终局摘要：`凡人长寿` 成就从“寿元上限 >= 80”改为“实际年龄 >= 80”；注册用户 `/death_summary` 优先基于当前 session 重算摘要，旧数据库成就只作为兜底，避免 16 岁角色显示“撑过八十载”。
- 只读复盘线程 `019ee96e-5685-7223-8796-55c1c7b52205` 结论：P0/P1 仍是 UI 批次验收、生产 Alembic/PG smoke、真实浏览器/公网游玩链路；冗余清理优先缓存、构建产物、历史归档；技术债集中在 React 大样式文件、后端服务边界、SQLite/PostgreSQL 双轨和源码字符串测试假绿。
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
