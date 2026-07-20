# Project Audit

## Scope

本审计覆盖 2026-07-14 的 `master@99e7915` 提交链，以及截至 2026-07-20 `master@f302d37` 的发布收口复核。`9b3a86e` 的玩法、数据库和 Chrome 90/20 回合结果仅是历史证据；当前候选的完整本地门禁和混合路线 Chrome 已重新验证，90 回合黄金路线证据准确绑定其行为等价的前一 clean 提交 `c79d05c`。生产曾执行隔离、备份和 Stage 1，但 strict choice 触发 fallback；服务器重启后出站 ACL 未恢复，故当前运行健康不等于发布验收通过。

## Current Architecture

- 前端：React 18 + Vite + TypeScript；Vitest/RTL 覆盖关键交互。
- API：FastAPI，路由按 auth/catalog/session/settings 拆分。
- 游戏：`GameEngine` 门面 + StartFlow/TurnFlow/BreakthroughFlow/ModelFallbackPolicy。
- Agent：项目内 `SequentialAgentGraph`，不是 LangGraph。
- 数据：PostgreSQL-only，Alembic head `20260710_0008_runtime_consistency`。
- 内容：v1 60 回合旧档兼容；v2 九阶段 90 回合，新局默认 v2。
- 部署：生产 Redis 共享限流 + 内部 Squid + 应用专用 egress ACL；本地纯单测可使用内存限流。
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
- 四套世界包绑定精确版本主线；Session/存档保存 key、version 和可变剧情进度。v1 在第 60 回合收束，v2 按九阶段推进到第 90 回合，20 回合不提前结束。
- v2 黄金路线使用正式选择、事件和 `RealmSystem` 在第 87 回合飞升；低资质或其他路线允许死亡、失败或停留较低境界。旧存档缺少剧情绑定时按原世界补绑，已有但不可用的精确版本显式拒绝。
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

## 2026-07-14 Current Verification

本节覆盖玩法候选 `9b3a86e` 与最终代码 `HEAD 99e7915`。本地 PostgreSQL 自动化和 Chrome 使用隔离时段；`tests\web` 清库时没有浏览器并发。浏览器证据仅保留在 Git 忽略的 `output/playwright/`，不包含 credential 或生产配置。

- 自动化：compileall、Ruff、Ruff C901、mypy 通过；`tests\web -n0` 为 94 passed；串行非 live 全量为 804 passed、1 deselected、0 skipped、0 failed；Vitest 12 passed，React build 通过。
- 规则级黄金路线：`scripts/validate_90_turns.py --seed agens-golden-169 --max-turns 90` 在第 87 回合飞升。`AGENS_VALIDATION_SEED` 仅允许非生产高资质 v2 验证，生产检测到该变量会拒绝启动。
- Headed Chrome 90 回合：`local-visible-golden90-9b3a86e-20260714.json` 为 `passed_terminal`，第 87 回合 `finale=true`；87/87 choice strict live，fallback 0、repair 0、contract recovery 0、P0/P1 0、可见禁用词 0、精确重复 0；第 45 回合存读档和刷新后继续成功。
- Headed Chrome 20 回合：`local-visible-mixed20-9b3a86e-20260714.json` 为 `passed`；20/20 choice strict live，双击只提交一次，第 10 回合存读档和刷新后继续成功，fallback/repair/P0/P1 0。
- 性能：90 回合 p50 9.159s、p95 18.573s、max 19.752s；20 回合 p50 10.240s。`choice p50 <= 5s` 仍明确延期；生产 strict choice 阻塞另见下一节。
- 真实 Chrome 暴露的两类验收问题已修复：世界/制度中的境界文本不再误报为玩家状态；成功突破叙事若写错旧阶段或目标境界，会在玩家可见前改写为准确的权威过渡。
- `99e7915` 额外通过 compileall、Ruff、C901、mypy 和 deployment-contract 测试；其 ACL 顺序固定为“完整安装并插入链 -> 开启 bridge filtering”。

## 2026-07-14 Production Gate

- 从 `99e7915` 提交对象生成并扫描候选包和生产包；生产包未包含测试、运行证据、敏感路径或凭据样式。
- 服务器隔离通过 Docker/Compose、镜像硬化、PostgreSQL、Redis 跨实例限流与故障 503、Squid 允许/拒绝矩阵、同桥私网阻断、直接公网阻断和代理 provider 连通性。
- PostgreSQL、应用、Compose 和环境配置备份完成；生产 Stage 1 部署新镜像并保持 Alembic `20260710_0008`，Redis、Squid、应用、origin 和公网 health 均正常，egress ACL 位于 `DOCKER-USER` 首位。
- v1 strict smoke 的 start 为 non-fallback，但首个 choice 的两次 Narrator 输出均在正文保留英文，触发 incomplete output 和本地 fallback。该结果不算 live-model 成功，流程按硬门禁停止。
- 尚未执行旧镜像回滚演练、`story_version=2` 切换、v2 smoke 和 ACL/sysctl 持久化。当前生产运行健康但未获发布验收；恢复方向等待在“回滚到 `a5a1f0f9`”与“新提交修复后继续”之间确认。

## 2026-07-20 Content Patch And Local Acceptance

- `35fe2dc` 已收紧 Narrator 的 schema、标签 prompt、单次 incomplete retry 与脱敏诊断，要求正文和四个选项为全中文；`f4c7333` 已加入受版本控制的 `br_netfilter` 与 egress ACL 持久化资产。`f302d37` 修复了内容补丁的 `BreakthroughFlow` 类边界，并将突破与普通回合的叙事去重、精确时长校验、通用替代文本和持久化叙事 hash 纳入同一质量守卫。
- `f302d37` 工作树 clean。本地通过 compileall、Ruff、Ruff C901、mypy、`tests\\web -n0`（94 passed）、串行非 live pytest（804 passed、1 deselected、0 skipped、0 failed）、Vitest（13 passed）、React build 和 npm audit。固定种子规则验证在第 87 回合飞升。
- `release-c79d05c-golden90-20260720.json` 绑定独立 PostgreSQL 和 clean `c79d05c`：87/87 choice strict live，第 87 回合终局；fallback、repair、contract recovery、可见禁词、精确重复和 P0/P1 均为 0，存读档、刷新、双击与持久化 turn 连续性/重复审计均通过。p50/p95/max 为 8.892s/44.968s/69.984s。`f302d37` 相对 `c79d05c` 仅将两个局部类型推断变量改名以通过 mypy，不改变运行分支；证据仍以实际执行 commit 为准。
- `release-f302d37-mixed20-20260720.json` 精确绑定当前提交：20 个主回合加读档后 3 回合均 strict live；fallback、repair、contract recovery、可见禁词、精确重复和 P0/P1 均为 0，存读档、刷新、双击与 23 条持久化回合连续性/重复审计均通过。p50/p95/max 为 8.930s/48.215s/60.877s。
- 当前本机未找到 Docker CLI，故当前提交的 Compose config 和镜像构建门禁未执行；这不是测试通过。生产未在本轮发生写操作、模型重试或部署。
- 服务器重启后的只读预检仍显示应用、PostgreSQL、Redis、Squid、origin/public health 和 Alembic `20260710_0008` 正常，运行镜像仍为历史 v1；但 `br_netfilter` 未加载、bridge filtering 不可用、`AGENS_WEB_EGRESS` 链不存在且未安装持久化 systemd 服务。`f4c7333` 的持久化资产尚未部署。
- 结论：此前内容补丁回归和本地 Chrome 阻塞已关闭，无新增 P0；生产发布仍被当前候选的 Docker 门禁、v1 strict smoke、旧镜像回滚演练、v2 smoke 和 ACL 持久化/重启验收阻塞。不得将本地全绿或当前服务器 health 写成生产发布完成。

## Residual Risks

| 风险 | 级别 | 说明 |
| --- | --- | --- |
| 生产 strict choice 未通过 | P1 | Narrator 正文连续两次保留英文，严格契约拒绝后进入 fallback；需修复提示/安全改写策略并重新执行 v1/v2 smoke |
| 当前候选 Docker 门禁未执行 | P1 | 本机没有可用 Docker CLI，当前 `f302d37` 尚未完成 Compose config 与镜像构建；生产部署前必须补齐，历史服务器 Stage 1 不可替代 |
| ACL/sysctl 当前未持久化 | P1 | 重启后 `br_netfilter`、bridge filtering、`AGENS_WEB_EGRESS` 和 systemd 持久化服务均不存在；恢复过程禁止卸载 `br_netfilter` |
| live 响应仍高于 5 秒目标 | P1 | 当前 fingerprint 的 164 个严格 live 回合 choice p50=9.495s、p95=18.025s、max=44.636s（目标 p50≤5s/p95≤15s 均未达）。Narrator 仍是主要延迟来源，需 provider/模型侧或并发化处理 |
| 内容路线仍有相似度风险 | P2 | 最新 A/B/C/D 硬门禁通过，但 C/D 峰值相似度约 0.743/0.769，后续应继续增加事件兑现和路线专属内容 |
| `database_postgres.py` 仍偏大 | P2 | catalog/rewards/session_mutation 已抽到独立 repository（1332→727 行）；run/turn/progress 跟踪为剩余的最大 SQL 块，可在文件再增长时提取 |
| `tests/web/test_web_api.py` 仍偏大 | P2 | model settings/auth/production-hardening/save-load 已拆出（2040→~1419 行）；session/turn 主题仍与 gameplay flow 混在原文件，待后续批次连同 helper 迁 conftest 一起拆 |
| 初始 `/api/auth/me` 访客探测返回 401 | P2 | UI 正常处理，但 Chrome console 会记录一次预期资源错误；可后续评估匿名 me 返回 200/null |

## Acceptance Boundary

- 本地自动化通过不等于生产通过。
- HTTP 200 不等于 live-model 成功。
- `fallback=true`、`fallback_prompt.active=true`、`contract_recovery=true` 或 Narrator 非 `ok` 一律不算 live-model 成功。
- 生产 Stage 1 健康不等于发布通过；必须补齐 non-fallback choice、回滚演练、v2 smoke 和持久化门禁。
