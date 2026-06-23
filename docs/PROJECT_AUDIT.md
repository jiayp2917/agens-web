# 项目结构审核与收束

本文是 Web-only 项目的结构边界、瘦身清单和技术债队列。本目录只做浏览器版本。

## 当前边界

- 产品入口是浏览器 Web UI + FastAPI 后端。
- 当前核心游戏逻辑继续复用 `src/agens_novel/`。
- 当前只开放游戏模式（v5 已实现 / 阶段 7/8 联调收尾中）：A/B/C/D 四按钮固定语义，A 稳妥 / B 机遇 / C 风险 / D 气运。
- 引导模式、小说模式只作为禁用入口保留，不开放运行逻辑。
- 模型失败、无 key、无有效选项时，用户可选择本地故事兜底继续或结束本局。
- 境界顺序固定为：练气、筑基、金丹、元婴、化神、合体、大乘、渡劫、飞升。

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
| P2 | PostgreSQL 设计和 Alembic 迁移已经补齐 Alpha 必需表，但仍需确认服务器生产库已升级到 `20260622_0004_ddl_disallow_production` 及之后，并继续做索引评审、备份恢复和回滚演练。 | 设置 `TEST_DATABASE_URL` 跑空库迁移和账号游玩链路；服务器确认 `game_runs`、`game_turns`、`player_progress` 存在；生产运行时 `APP_ENV=production` 自动拒绝 `AGENS_PG_AUTO_DDL=1`。 |
| P2 | 访客局只在单进程内存中，容器重启、多 worker 或多副本会丢失。 | Alpha 阶段明确提示；正式多人部署前引入共享会话存储或只允许账号局跨进程恢复。 |
| P2 | 匿名访客仍可能消耗模型额度。 | 增加访客日限额、IP/设备限额、模型预算保护和边缘层限流。 |
| P3 | 测试目录需继续从旧产品分类迁移到 Web 分类。 | 保留核心测试，新增 API 和浏览器测试，删除旧 UI 契约测试。 |
| P2 | React 局部组件仍偏重，后续 UI 迭代容易互相影响。 | P2 已拆分认证、首页、角色创建、游戏页、设置/存档弹窗、模型设置面板、存档槽列表、BGM 和终局页组件；下一步按需继续抽 `CharacterCreatePage` 与 `styles.css`。 |

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
