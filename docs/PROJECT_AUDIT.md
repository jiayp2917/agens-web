# Project Audit

## Scope

本审计描述 2026-07-12 本地 `master@019b941` 工作树（clean；在 `ea18398` 之上叠加 LLM 错误路径专项测试、`database_postgres` repository 拆分和 `test_web_api.py` 主题拆分，自动化门禁在该提交链复跑通过）。本批次新增真实模型矩阵证据：独立 `agens_web_live` PG 库 + headed Chrome 在 `019b941`(clean) 重跑 A/B/C/D 各 20 回合 + mixed 60 回合。旧 `master@ea5ab36` 的 dirty 工作树证据只作历史。未连接生产环境、未读取 secrets、未执行生产迁移或部署，旧生产证据不作为当前分支通过结论。

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
- 四套世界包绑定精确版本主线；Session/存档保存 key、version 和可变剧情进度，主线第 60 回合收束，20 回合不再提前结束。
- 第 60 回合主线收束会写入终局原因并结束 session；旧存档缺少剧情绑定时按原世界补绑，已有但不可用的精确版本显式拒绝。
- 已结束主线不重复结算结局；每四回合的阶段反馈继续写入主线 beat 和外界情报。
- 事件表的 `allowed_delta_types` 在 Judge 前后强制执行；模型世界重置叙事由规则侧压制。
- Web 选项索引与 `GameEngine` 字母输入共用同一 A/B/C/D 语义 helper，不再因去掉标签把风险路线误判为机遇。
- Agens Narrator 主调用使用 provider `json_schema` 三字段契约和专用 prompt；应用层确定性渲染为既有标签格式，旧模型仍走标签 prompt。兼容 parser/recovery 保留，但不能进入严格 live 成功。
- Narrator 温度为 0；普通回合模型不能修改规则权威的 `attributes` 或 `lifespan`。玩家可见选项残留英文时按原 A/B/C/D 槽位替换为中文同语义选项，不移动路线索引。
- 重复叙事检测与 Chrome 二元组相似度门槛对齐；替换时保留 NPC、伤势、道具、功法和地点等结构化结果。
- 突破失败状态阻止立即重试和自动升层；稳妥回合确定性清除阻断状态并保留无关伤势。本地故事路径按最终状态生成下一组选项。
- 突破模型 delta 不再控制境界、寿元、属性、道具、功法、伤势或突破旗标；成功/失败叙事会按最终权威境界再次校验。
- 严格 Narrator 输出出现重复/无效选项时最多重试一次，不启用普通 repair；provider schema 与兼容标签传输保持同一语义合同。
- 规则拥有的称号覆盖模型 delta 后，叙事必须明确包含最终结构化称号；模型声称另一个称号时一致性守卫会拒绝该叙事。

### P1 事务与并发

- 访客 session PostgreSQL 持久化并设置 TTL/token hash。
- 登录/注册后删除访客局，不迁移。
- mutation 请求强制 `request_id` 和 `expected_version`。
- 每 session 锁 + PostgreSQL CAS + 幂等结果表。
- 回合、snapshot、run、奖励、进度、遗泽和 save slot 原子提交。
- 读旧档会在同一事务删除存档回合之后的 `game_turns` 并同步 active run，继续游玩不再撞 `(run_id, turn_no)`；已结算终局禁止原地覆盖历史。
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
- 寿元条、细滚动条、简洁分隔线、当前编年史淡墨条纹及固定字号 token 已按批准素材收敛；未替换字体文件、未改业务结构或文案。

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
- mypy `src + web`：76 source files，0 errors。
- 空库 Alembic 从 base 升级到 `20260710_0008`，确认 18 张应用表后删除临时库。
- 代表性 0007 已有库可把 session-owned `game_turns` 回填为 active `game_runs` 后建立外键。
- 孤儿 `game_turns` 和三类重复业务记录会让 0008 事务回滚，revision 保持在 0007，不留下部分 schema。
- 干净数据库可从 0008 downgrade 到 0007 后重新升级；guest session 或 active run 会阻止 downgrade。
- `scripts/verify_pg_backup_restore.py` 实际完成临时源库 `pg_dump`、目标库 `pg_restore`，恢复 revision `20260710_0008`、18 张应用表，以及 user/session/save/run/turn/mutation/achievement/reward/legacy/progress 业务关系图；孤儿 turn 为 0，最后清理临时库和 dump。
- `compileall` passed。
- PostgreSQL `tests\web -n0`：94 passed，0 skipped。
- 全量非 live pytest（`TEST_DATABASE_URL` 已配置）：740 passed，0 skipped，0 failed。
- 模型错误路径专项验证 `tests/unit/llm/test_llm_error_paths.py`：49 项，覆盖 408/425/429/500/502/503/504 状态分类、401/403 鉴权、3xx 重定向拒绝、整体超时、`RetryExhausted` 与可重试状态耗尽、外部取消传播，以及此前零覆盖的 `is_retryable_model_request_failure` 分类器。
- Vitest：12 passed；React production build passed；npm audit：0 vulnerabilities。
- 真实 Chrome fallback smoke 通过：注册、访客局删除、个人模型设置保存/清除且 Key 输入清空、双击 start/choice 单请求、fallback 无“继续本局”、A/B/C/D 年龄推进、save/load、终局原因、375 和 2K 无横向溢出。
- 真实 Chrome UI 视觉检查覆盖 1440x900、1920x1080、2560x1440 和 390x844；角色创建、游戏页、桌面/移动弹窗及六态夹具均已截图核对。证据不进入 Git。
- Chrome smoke 后数据库事实：guest sessions 0、save 1、game_turns 2、completed run 1、user model config 清除后 0。
- 最新工作树证据 `goal-plan-final-r3-768-20260712.json` 绑定 HEAD、dirty 标记、工作树 fingerprint、脚本哈希和独立数据库标签：20 个主回合 + 3 个读档后回合共 23/23 live，turn count 1-23 连续。
- 最新证据为 fallback 0、contract recovery 0、repair 0、incomplete retry 0、可见禁词 0、P0/P1 0；Judge 1 次，外界情报变化 9 次。第 20 主回合结束并读档后为 53 岁、筑基初期、寿元 147/200。
- 768x900 无横向溢出；真实 HTTP 409 键盘触发、可见提示、权威 session 刷新和焦点恢复通过；双击防重、页面刷新、存档/读档及读档后继续 3 回合通过。
- 最新 choice 平均 8.98s、p50 8.80s、p95 10.32s、最大 16.64s。更早的 A/B/C/D 各 20 回合和 mixed 60 回合矩阵属于前一工作树 fingerprint，只作为 `CHANGELOG.md` 中的历史证据，不冒充当前工作树完整矩阵。
- 2026-07-12 真实模型矩阵（`master@019b941` clean + 独立 `agens_web_live` PG 库 + headed Chrome，`AGENS_START_MODEL_WORLD=1` 强制 live 开场）：A/B/C/D 各 20 回合 + mixed 60 回合，证据绑定 HEAD `019b941f`、dirty=False、`agens_web_live` 库标签与脚本哈希（`output/playwright/matrix-*` 证据集，gitignored）。140/140 choice 回合严格 live 通过（Narrator `ok`、provider JSON schema envelope ok、0 fallback、0 contract recovery、0 repair、save/load 通过）。全 live 回合 choice **p50=9069ms、p95=17529ms、max=26234ms**（目标 p50≤5s/p95≤15s 均未达）。延迟拆分：Narrator 主导 ~8.5–9.4s/回合（每回合必调，占 90%+），residual（持久化+网络+页面渲染+规则结算+Judge 摊销）仅 ~0.1–1.3s，证明瓶颈在 provider 单次调用延迟而非本地编排；Judge 间歇触发（0–6 次/局，~5.3–8.6s/次），触发回合被推到 17–26s，对应 p95/max 尖峰。开场 World Builder 7 次尝试中 2 次 `incomplete_output` 回退确定性开场（两次失败 `completion_tokens` 均为 1673，疑似截断），重跑均成功，属瞬态；开场不走 provider JSON schema（靠解析），Narrator 因强制 schema 而 140/140 稳定。fixed-c 出现 2 次 Narrator incomplete retry（已恢复，非 fallback）。mixed-60 跑满 60 回合但 `game_over` 未触发，规则终局样本本批未捕获。

## Residual Risks

| 风险 | 级别 | 说明 |
| --- | --- | --- |
| DNS 校验与连接之间存在 rebinding TOCTOU | P1 | 应在公网部署层增加出站 ACL/代理，阻止私网和 metadata 地址 |
| 本机无 Docker CLI | P1 | Docker build/compose config 只能在 CI 或具备 Docker 的本地环境补验 |
| live 响应仍高于 5 秒目标 | P1 | 2026-07-12 矩阵全 live 回合 choice p50=9.07s、p95=17.5s、max=26.2s（目标 p50≤5s/p95≤15s 均未达）。Narrator 主导 ~8.5–9.4s/回合，residual 仅 ~0.1–1.3s，瓶颈在 provider 单次调用延迟而非本地编排；Judge 触发回合推高 p95/max。降延迟需 provider/模型侧或并发化，非本地编排能单独解决 |
| 最新工作树矩阵已重跑，规则终局样本未捕获 | P1 | 2026-07-12 已在 `019b941`(clean) + 独立 `agens_web_live` 库重跑 A/B/C/D 各 20 + mixed 60，140/140 choice live；mixed-60 跑满 60 回合未触发 `game_over`，规则终局长局样本本批未捕获，待内容侧确认 60 回合主线收束触发条件 |
| 开场 World Builder 偶发回退 | P1 | 矩阵 7 次开场中 2 次 `incomplete_output`（两次失败 `completion_tokens` 一致为 1673，疑似截断）回退确定性开场；重跑均成功，瞬态。开场不走 provider JSON schema（靠解析），Narrator 因强制 schema 而 140/140 稳定。可评估为开场启用 provider JSON schema 或放宽开场契约重试 |
| 标准 90 回合目标未实现 | P1 | 当前四套内容版本在第 60 回合收束；90 回合是长期产品目标，不是当前完成事实 |
| 生产未部署 `0008` | P1 | 当前只证明本地迁移；生产需单独备份、孤儿检查、迁移和 smoke |
| `database_postgres.py` 仍偏大 | P2 | catalog/rewards/session_mutation 已抽到独立 repository（1332→727 行）；run/turn/progress 跟踪为剩余的最大 SQL 块，可在文件再增长时提取 |
| `tests/web/test_web_api.py` 仍偏大 | P2 | model settings/auth/production-hardening/save-load 已拆出（2040→~1419 行）；session/turn 主题仍与 gameplay flow 混在原文件，待后续批次连同 helper 迁 conftest 一起拆 |
| 应用内 RateLimiter 为单进程 | P2 | 多副本公网应使用反代/Redis 分布式限流 |
| 初始 `/api/auth/me` 访客探测返回 401 | P2 | UI 正常处理，但 Chrome console 会记录一次预期资源错误；可后续评估匿名 me 返回 200/null |
| `test_notice_board_description_is_not_treated_as_claimed_reward` 非确定性 | P2 | pre-existing flaky：仅当回合 1 随机推进 stage 时，`_narrative_conflicts_with_stage_delta`（turn_flow.py:418-420）把含「练气N层」任务等级描述的叙事误判为玩家境界声明，用规则编年史覆盖 narrator 叙事。5 次孤立运行为 3 通过 / 2 失败。属叙事一致性产品行为，修复需谨慎（正则/上下文消歧或产品判定），与模型错误路径批次无关 |

## Acceptance Boundary

- 本地自动化通过不等于生产通过。
- HTTP 200 不等于 live-model 成功。
- `fallback=true`、`fallback_prompt.active=true`、`contract_recovery=true` 或 Narrator 非 `ok` 一律不算 live-model 成功。
- 当前工作树的生产部署、数据库升级和真实账号验收必须由独立生产任务完成。
