# Project Audit

## Scope

本审计描述 2026-07-11 本地工作树。未连接生产环境、未读取 secrets、未执行生产迁移或部署。旧生产证据不作为当前分支通过结论。

## Current Architecture

- 前端：React 18 + Vite + TypeScript；Vitest/RTL 覆盖关键交互。
- API：FastAPI，路由按 auth/catalog/session/settings 拆分。
- 游戏：`GameEngine` 门面 + StartFlow/TurnFlow/BreakthroughFlow/ModelFallbackPolicy。
- Agent：项目内 `SequentialAgentGraph`，不是 LangGraph。
- 数据：PostgreSQL-only，Alembic head `20260710_0008_runtime_consistency`。
- 依赖：Python 使用 `uv.lock`，前端使用 `package-lock.json`。

## Closed Findings

### P0 SSRF

已增加统一模型 URL 安全模块，并在保存配置和每次调用前验证：

- HTTPS only；
- 官方域名或服务器 allowlist；
- 拒绝 credentials/query/fragment/IP literal；
- 全量 A/AAAA 解析，任一非公网地址即拒绝；
- HTTPX 不跟随重定向、不继承环境代理；
- 408/429/5xx 进入重试，增加整体调用时限和取消传播。

### P1 游戏一致性

- Judge `approved` 只接受 JSON bool。
- 失败突破不能被 Judge 改成升境界；突破/飞升先记录再终局。
- 普通回合只有在规则和 Judge 接受后提交 choices。
- fallback 自动进入本地故事，无“继续本局”死按钮。
- 本地故事调用 `settle_turn()`，推进年龄、寿元和阶段反馈。
- A/B/C/D 语义由后端槽位强制，D 始终为气运。
- `GameSession.error` 随存档保存和恢复。

### P1 事务与并发

- 访客 session PostgreSQL 持久化并设置 TTL/token hash。
- 登录/注册后删除访客局，不迁移。
- mutation 请求强制 `request_id` 和 `expected_version`。
- 每 session 锁 + PostgreSQL CAS + 幂等结果表。
- 回合、snapshot、run、奖励、进度、遗泽和 save slot 原子提交。
- 邀请码消费与用户创建原子化；首管理员创建加 advisory transaction lock。
- 终局奖励、成就和遗泽有业务唯一约束。
- `/api/health` 检查 PostgreSQL。

### P2 复杂度与质量

- `create_app()` 已收敛为应用工厂和 router 注册。
- `GameSession.apply_delta()` 按角色数值/身份/属性/集合、世界和 meta 拆分。
- Narrator/choices 手写括号扫描优先改用标准 JSON decoder 或独立扫描状态。
- World response、SSE、turn flow、achievement、fate profile 和 turn settlement 已按职责拆分。
- Ruff 普通规则、Ruff C901 和 mypy 当前均为零错误。
- CI 不再 `continue-on-error`，覆盖 Python/PG/React/lock/Docker 配置门禁。

### 前端视觉一致性

- 角色创建栏、游戏状态栏、编年史面板和设置/存档弹窗共用本地 SVG 九宫双线内收角；同轮廓 mask 会裁切实际宣纸背景，角部不再保留矩形底色。
- 首页/存档/设置/BGM 使用 44 px 交互区和 40 px 可见双环按钮；本地 SVG 保持统一描边重量，移动端 BGM 进入随页面流动的 sticky 工具栏。
- A/B/C/D 使用固定圆标、文本和箭头列，并覆盖 default、hover、pressed、focus-visible、disabled、loading 六态；状态变化不改变按钮尺寸。
- 寿元条、细滚动条、菱形分隔线、当前编年史淡墨条纹及固定字号 token 已按批准素材收敛；未替换字体文件、未改业务结构或文案。

## Database State

当前 18 张应用表：

```text
users, invite_codes,
sessions, session_mutations, saves,
model_config, user_model_configs,
catalog_talents, catalog_family_backgrounds, catalog_spirit_roots,
catalog_difficulties, catalog_story_seeds,
game_runs, game_turns, player_progress,
run_achievements, account_rewards, legacy_bonuses
```

迁移 `20260710_0008_runtime_consistency` 对无法关联的历史 turn fail closed，不静默删除数据。生产执行前仍必须先做只读孤儿检查和备份。

## Security State

- 用户/系统模型 Key 使用 Fernet 密文和 masked metadata。
- 缺少 `MODEL_CONFIG_SECRET` 时 fail closed。
- 个人 Key 不写进 `os.environ`，不同用户 runner 不共享 Key。
- body-size middleware 覆盖 Content-Length 和 chunked body。
- 生产模式统一识别 `prod|production`。
- Docker 配置已改为非 root、read-only、cap drop、no-new-privileges、tmpfs 和资源限制。
- Alembic 使用一次性 migration service，应用副本不再启动时迁移。

## Cleanup

- 删除 `scripts/run_with_key.ps1`，避免命令行参数进入 PowerShell 历史。
- 删除未引用的 `web/frontend-react/public/assets/ascension_gate.png`。
- 删除旧 migration entrypoint `deploy/docker-entrypoint.sh`。
- 原 `output/` 已移到 `D:\chat\agens-web-artifacts\20260710`。
- 归档包含 723 个文件、599,683,815 字节、`MANIFEST.sha256` 和 `INVENTORY.txt`。

## Validation State

当前已完成：

- `pg_isready`：`127.0.0.1:55432` accepting connections。
- Ruff 普通检查：0。
- Ruff C901：0。
- mypy `src + web/backend`：0。
- 空库 Alembic 从 base 升级到 `20260710_0008`，确认 18 张应用表后删除临时库。
- `compileall` passed。
- Ruff 普通检查 0；C901 0；mypy 74 source files 0 errors。
- PostgreSQL `tests\web -n0`：92 passed。
- 全量非 live pytest：594 passed。
- Vitest：9 passed；React production build passed；npm audit：0 vulnerabilities。
- 真实 Chrome fallback smoke 通过：注册、访客局删除、个人模型设置保存/清除且 Key 输入清空、双击 start/choice 单请求、fallback 无“继续本局”、A/B/C/D 年龄推进、save/load、终局原因、375 和 2K 无横向溢出。
- 真实 Chrome UI 视觉检查覆盖 1440x900、1920x1080、2560x1440 和 390x844；角色创建、游戏页、桌面/移动弹窗及六态夹具均已截图核对。证据不进入 Git。
- Chrome smoke 后数据库事实：guest sessions 0、save 1、game_turns 2、completed run 1、user model config 清除后 0。

## Residual Risks

| 风险 | 级别 | 说明 |
| --- | --- | --- |
| DNS 校验与连接之间存在 rebinding TOCTOU | P1 | 应在公网部署层增加出站 ACL/代理，阻止私网和 metadata 地址 |
| 本机无 Docker CLI | P1 | Docker build/compose config 只能在 CI 或具备 Docker 的本地环境补验 |
| 未跑 20 回合/真实模型 Chrome | P1 | 本批只完成 fallback smoke；没有验证真实 provider、长尾、20 回合内容质量或 live non-fallback |
| 本批未跑真实 LLM | P1 | `llm_real` 默认排除；fallback 不能算 live success |
| 生产未部署 `0008` | P1 | 当前只证明本地迁移；生产需单独备份、孤儿检查、迁移和 smoke |
| `database_postgres.py` 仍偏大 | P2 | 事务边界已集中，但 SQL/row shaping 仍可按 catalog/session/reward 拆模块 |
| `tests/web/test_web_api.py` 仍偏大 | P2 | 后续按 auth/settings/session/save/turn 拆文件，不应和玩法改动混做 |
| 应用内 RateLimiter 为单进程 | P2 | 多副本公网应使用反代/Redis 分布式限流 |
| 初始 `/api/auth/me` 访客探测返回 401 | P2 | UI 正常处理，但 Chrome console 会记录一次预期资源错误；可后续评估匿名 me 返回 200/null |

## Acceptance Boundary

- 本地自动化通过不等于生产通过。
- HTTP 200 不等于 live-model 成功。
- `fallback=true` 或 `fallback_prompt.active=true` 一律不算 live-model 成功。
- 当前工作树的生产部署、数据库升级和真实账号验收必须由独立生产任务完成。
