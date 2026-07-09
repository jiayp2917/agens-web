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

- 当前本地代码基线：已包含脱敏模型诊断、P1 可见反馈修复、2026-07-04 属性尺度清理、2026-07-07 P1 事件池/最终 delta 一致性切片、2026-07-08 编年史内容切片，以及 2026-07-09 真实浏览器内容审查/重复叙事去重/玩家可见兜底文案清理。
- 本地 PostgreSQL 测试库目标：`127.0.0.1:55432/agens_web_test`。
- 最新自动化门禁：2026-07-09 内容审查批次后 `compileall` passed，`tests\web` 74 passed，全量 `pytest -q` 555 passed，前端 build passed，`git diff --check` 仅 LF/CRLF warning。
- 用户级模型设置已落地：个人配置按 `user_id` 加密隔离，系统默认保留在 `model_config`，运行时按当前 session/user 解析模型配置，不再通过进程级 `AGNES_API_KEY` 注入用户 key。
- 角色创建属性池已按 `GAME_MODE_SPEC.md` §4.1 落地：手动 2-8/总和 30，随机 0-10/总和 30。
- 运行时属性尺度已审计并收敛为 0-10：`DEFAULT_ATTRIBUTES` 为 5，境界小层推进、`GameSession` delta/save、World Builder 入局、跨局奖励和 catalog 种子不再以 50/100 作为正常尺度；旧 0-100 仅作兼容迁移输入。
- 动态开局链路已改为 profile-aware opening payload：难度、天赋、灵根、家世、六维属性和随机/手选模式生成本局世界观、0-16 岁编年史、16 岁初始局势、外界情报和首次 A/B/C/D；模型未启用或失败时使用差异化本地 fallback，不再固定青玄宗/东荒云界模板。
- 境界、突破、寿元和可见文本一致性已进入规则约束：练气显示 1-9 层，筑基及以上显示初期/中期/后期/圆满；突破由规则先结算，模型只按结果叙事；寿元按境界区间和角色/事件动态修正；玩家可见文本清理 JSON、结构化标签、英文状态词和内部 mismatch 文案。
- 本地真实 Chrome 内容审查已通过：2026-07-09 `final2` 批次为 accepted local evidence。base、A、B、D 均完成 20/20 live turns；C 路线第 19 回合自然终局；mixed 长局第 49 回合自然终局。最终证据 `local-content-basic-cycle-final2-20260709`、`local-content-route-{a,b,c,d}-final2-20260709`、`local-content-mixed-60-final2-20260709` 均 fallback 0、P0/P1 0、玩家可见禁用词 0、明显重复 0，strict JSON/NDJSON/CSV 可解析。证据位于 `output/playwright/`，默认不提交。
- 生产 P0 已通过：服务器线程部署 `25ad3d15` 后，容器 healthy，Alembic `20260622_0005`，`user_model_configs` 存在，public/origin health 和 catalog 正常，日志敏感标记扫描为 0；一次性真实账号注册、登录、开局、选择、存档、读档、跨会话恢复均通过；生产 start 和至少 1 次 choice 均为 non-fallback，choice 后 `turn_count=1`。
- 最新本地代码已加入脱敏模型性能观测并完成 2026-07-09 内容审查复采：final D 平均约 14.4s、最大约 64.2s；mixed 长局平均约 9.3s、最大约 64.1s。响应慢没有完全闭环，且 narrator 结构化输出仍不稳定；mixed 长局 `narrator_incomplete_output_count=46/49`，主要靠规则 delta 与 choices recovery 维持推进。下一步重点是 provider/narrator 长尾、模型输出契约、judge 调用成本和终局页证据采集。
- 2026-07-07 防御性运行修复已完成：`GameSession.apply_delta()` 对 malformed nested `character/world/meta` delta fail closed；Web `fallback_prompt.active` 改为当前态，不再因历史 `model_failure` 长时间误亮，且 runner 重建时会从持久化事件恢复当前提示态；`/choice` 支持 A/B/C/D 与 `"1"`-`"4"` 简写，仍拒绝自由文本。
- 2026-07-07 P1 事件池/最终 delta 一致性切片已完成：每 4 回合阶段反馈改为稳妥/机遇/风险/气运四路线事件池；普通回合叙事一致性改为按“模型 delta 清洗 + 规则 delta 合并后的最终落账 delta”校验；功法新增、突破/延寿/传承/关键/高稀有道具新增会触发 Judge，普通小收获不全量触发 Judge。

## 2026-07-06 子智能体只读审计

本次为只读审计：5 个 find→verify 维度（代码质量 / 冗余 / 废弃内容 / 死代码 / 治理）+ backlog 读取 + 计划与评审，共 13 个子智能体；每条发现都经独立 verifier 复核（均为 confirmed/partial，无被推翻的误报）。下方登记的代码层面发现已于同日执行（commits `cd57215..026cd69`）：god class 拆分、flow 耦合收敛、默认字面量与密钥 marker 统一、turn-record 冗余与 `_prompt_metrics` 收敛、死代码与孤儿资产清理、AGENTS 准则块与文档结构修复均已完成；`narrator/nodes.py` 解析器堆积、全仓库其余 bare-except、`save_artifact` 抽取等有意留作后续（见 `docs/NEXT_GOVERNANCE_BACKLOG.md` 同日"留后续项"小节）。完整执行摘要见 `CHANGELOG.md` 同日 "governance audit execution" 条目。

### ① 代码质量

| 发现 | 位置 | 级别 |
| --- | --- | --- |
| `WebGameService` 39 方法 god class（会话/存档/死亡奖励/模型配置/runner 缓存混合） | `web/backend/service.py:352-909` | high |
| 三个 `*Flow` 取 `engine: Any` 并调用 engine 私有成员；仅 `GameEngine.__init__` 实例化、零复用，纯间接 | `engine/turn_flow.py`、`start_flow.py`、`breakthrough_flow.py` | high |
| 默认 base_url/model 字面量在 11 处内联，未走 `Settings` | `settings.py:30-31` 等 11 处 | medium |
| 密钥脱敏 marker 在 engine（7 项）与 service（9 项）分叉；engine 会漏脱 `postgresql://` | `engine/game_engine.py:58`、`web/backend/service.py:51` | medium |
| `narrator/nodes.py` 539 行解析器堆积（7+ 私有 JSON 容错 helper，含手写括号深度状态机） | `agents/narrator/nodes.py:226-525` | medium |
| 14 处裸 `except Exception`；`service.py:883,891` 静默吞 DB 错误返回空 catalog/空档位且无日志 | `service.py:883,891` 等 14 处 | medium |
| `import logging` 放在 `service.py:940` 文件尾（带 `# noqa: E402`） | `web/backend/service.py:940-942` | low |
| A/B/C/D 映射在 3 处各自定义；world-reset 关键词硬编码 | `choices.py:12`、`service.py:904`、`game_engine.py:354,558-566` | low |

### ② 代码冗余

| 发现 | 位置 | 级别 |
| --- | --- | --- |
| turn-history append+compact 块在 3 处复制 | `turn_flow.py:365-379,389-399`、`breakthrough_flow.py:170-180` | medium |
| 第 4 处 `handle_local_story_action` 漏 chat_history append+compact → local-story 回合静默不入 narrator 历史 | `turn_flow.py:71-81` | medium |
| `call_agnes_llm` 头部 guard + 错误信封在 narrator/judge/world_builder 三处复制 | `agents/{narrator,judge,world_builder}/nodes.py` | medium |
| `save_artifact` audit dict 脚手架三处复制（80%+ 键同名，已开始分叉） | 同上 | medium |
| `_prompt_metrics` 在 narrator/judge 近乎逐字节重复 | `narrator/nodes.py:525-539`、`judge/nodes.py:218-233` | low |
| `start_flow` 的 confirm→fallback-or-end 模式重复 6 次 | `start_flow.py:76-95,165-217` | low |
| 三套 state-delta merge helper（两套浅合并可合一，`merge_rule_delta` 保留） | `turn_flow.py:434-444`、`breakthrough_flow.py:108-123`、`action_delta_policy.py:196-244` | low |
| `agents/common.py` 已 dedup load_settings/normalize_choices，却未覆盖上述三块样板 | `agents/common.py:23-71` | low |

### ③ 废弃内容（文档/资产）

| 发现 | 位置 | 级别 |
| --- | --- | --- |
| `output/` 下 3 个已跟踪 PNG 无任何 .md/.py/.ts 引用，违反"证据不入库"规则 | `output/agens-web-local-pg-*.png`（cf0ddf4 加入） | low |
| CHANGELOG 旧条目称普通回合 `repair=True`（已被当日顶部条目反转；旧条目可选标注 superseded） | `CHANGELOG.md:438-440` | low |
| `breakthrough_flow.py` 是唯一仍 `repair=True` 的 narrator 路径，无文档说明此为有意保留 | `breakthrough_flow.py:102` | low |

> 会话目录 `C:/Users/29176/.claude/plans/zesty-popping-graham.md` 提议与已提交 `8da562b` 相反的方向（建议把普通回合 repair 翻 True）。该文件不在本仓库内，不计入仓库审计；作为会话产物建议归档或清除以防后续误用。

### ④ 死代码（verifier 已核实零调用）

| 发现 | 位置 | 级别 |
| --- | --- | --- |
| `generate_world_profile` + 包装 `_generate_world_profile` 全仓库零调用（env 门控是烟雾弹，整链已死） | `start_flow.py:221-251`、`game_engine.py:246-253` | medium |
| `generate_profile_opening` + 包装 `_generate_profile_opening` 同为零调用死链 | `start_flow.py:253`、`game_engine.py:255-257` | medium |
| 6 个 `render.py` 格式化函数（status_card/inventory/skills/map/quests/equipment）仅测试用 | `engine/render.py:51,81,101,123,134,193` | low |
| `display_choice_text`、`profile_concept`、`validate_local_story_graph`、`default_lifespan_for_realm`、`RealmSystem.public_realm_name`、`paths.save_path`、前端 `lib/util.randomBetween` 均零调用 | 见各文件 | low |
| 前端 `StatLine.tsx` 运行时零引用，但被 `tests/web/test_frontend_contract.py:209,220` 锁定，删除须同步改契约测试 | `components/StatLine.tsx` | low |

> verifier 更正：`_session_flags`/`_inventory_text` 并非死代码（`realm.py:136-137` 在用），不可随 `public_realm_name` 一并删。

### ⑤ 项目治理

| 发现 | 位置 | 级别 |
| --- | --- | --- |
| `INDEX.md`、`ROADMAP` 的 495/旧基线已在本次同步到 516/`p1-final` | `docs/INDEX.md`、`docs/PLAYABLE_GAMEPLAY_ROADMAP_20260629.md` | 已修 |
| `AGENTS.md` 含两份"通用编码准则"（L1-60 详版 + L145-161 精简版），措辞已轻微分叉 — **已于 2026-07-06 删除精简版（commit `026cd69`）** | `AGENTS.md:1-60,145-161` | low → 已修 |
| `AGENTS.md` 与 `CLAUDE.md` 的准则块近乎逐字重复，改一处需同步另一处 | `AGENTS.md`、`CLAUDE.md` | low |
| `GAME_MODE_SPEC.md` 把 `## 实现状态` 标题嵌进 `>` 引用块（结构非标准） | `docs/GAME_MODE_SPEC.md:20-35` | low |
| `INDEX`/`RUNTIME_FLOW` 的"当前状态"段混入 dated 证据/未来指针 | 见各文档 | low |

## 2026-07-06 复核审计（post-execution）

第一轮审计的代码层面发现在 commits `cd57215..026cd69` 执行后，代码面貌已变（死代码删除、`WebGameService` 拆分、flow 耦合收敛）。本次基于执行后的**当前代码**再做一轮 6 维度 finder + 3 verifier 对抗式复核审计，**未修改任何代码**，仅更新文档与遗留项登记。

### 新确证的死代码（已于 2026-07-06 commit `f7fa7e8` 删除，verifier 全仓库 grep 复核）

| 符号 | 位置 | 状态 |
| --- | --- | --- |
| `GameEngine.expand()` | `engine/game_engine.py:379` | 零调用（任何位置） |
| `GameEngine.get_log()` + `format_log()` | `game_engine.py:418` + `render.py:51` | 仅测试 + `engine/README.md:20` doc row |
| `local_story_available()` | `engine/local_story.py:295` | 零调用 |
| `validate_local_story_graph()` | `engine/local_story.py:402` | 仅测试 |
| `ensure_runtime_dirs()` + `CHECKPOINT_DIR` | `paths.py:28,21` | 仅 `tests/conftest.py` |
| `MODEL_FAILURE_PROMPT` import | `game_engine.py:38` | 未用 import（常量本身亦零引用） |

以上 7 项符号 + `MODEL_FAILURE_PROMPT` 常量定义均已删除（含同步删除/迁移对应测试与 conftest 用法）。`service.py` 改为直接从 `model_fallback_policy` 导入 `MODEL_FAILURE_CONTINUE`（原本依赖 `game_engine` 的脆弱 re-export）。

### 复核推翻 / 降级的发现（避免误登记为待办）

- **三套 state-delta merge helper**（`merge_rule_delta` / `_merge_state_delta` / `_merge_breakthrough_delta`）：verifier 确认三者语义有意不同（rule 权威 + key 白名单 + list-append / 通用浅合并 / 突破失败 drop realm），**不应合并**。撤回旧 backlog "合并两套浅合并"提议。
- **`normalize_choices` 两套实现**（`agents/common.py:55` vs `engine/choices.py:39`）：agents 版严格 list 契约是 load-bearing，合并会引入 `json.loads` 字符串解析的行为变化。**保留分离**；仅 `agents/common.py:9-10` docstring 与 `docs/ARCHITECTURE.md:82` 有 drift（声称"复用 engine choice 清理"但实际没有）。
- **A/B/C/D letter→index 映射**（`game_engine.py:343` vs `service.py:709`）：服务不同输入面（自由文本 vs 按钮 payload），**不强合并**；可选 `dict(zip(CHOICE_LABELS, range(4)))` minor cleanup。
- **world-reset 关键词**（`game_engine.py:554` vs `judge.md` / `catalog_seed.py`）：prompt 散文 ≠ code 常量，catalog 是 coincidental 用词，**false positive**。
- **`_choose_model_failure` 总返回 `MODEL_FAILURE_CONTINUE`**：intentional——END 通过 `POST /api/sessions/{id}/end` + `<FallbackBanner>` "结束本局" 按钮可达（`ARCHITECTURE.md:309-316` + `tests/web/test_web_api.py:699` 覆盖）。**不是 bug**。
- **`call_agnes_llm` 三处定义**：judge + world_builder 已于 commit `0ade2db` 抽取为 `common.call_agnes_llm_common`（共享 prelude + 单次非流式 call + epilogue）；narrator 因 streaming + repair 特殊化保留自有实现。

### 保留的有效治理项（2026-07-06 处理状态）

本轮（commits `f7fa7e8`..`397a412`）已处理：死代码 7 项清理、`call_agnes_llm` 抽 common（judge + world_builder）、`import logging` 迁到 `service.py` 文件头、`normalize_choices` docstring drift 修复、CHANGELOG `repair=True` 旧条目标注 superseded、AGENTS↔CLAUDE 仓库内准则块加 source-of-truth 维护说明。bare-except 8 处经评估**保留**为 intentional defensive seam（已 `log.exception` / graceful fallback，收窄风险 > 收益）。

仍登记在 `docs/NEXT_GOVERNANCE_BACKLOG.md` "留后续项"小节的待办：`narrator/nodes.py` 539 行解析器堆积（高风险，独立批次，需 20 回合采样数据先证明是根因）、`start_flow` confirm→fallback 重复（低优先）、A/B/C/D 映射可选 zip cleanup、retire/demote 决策固化。

## 2026-07-06 narrator 20 回合延迟采样（chrome-devtools 浏览器采样）

为验证 `narrator/nodes.py` 解析器/契约是否为延迟根因，用 chrome-devtools 模拟真实用户跑 20 回合（env `AGENS_API_KEY` 系统 key，guest session，开局本地 fallback；narrator 在 choice 回合 live）。完整严格 JSON 证据：`output/playwright/narrator-sample-20260706.json`（本地，默认 .gitignore）。

### 数据（20 回合，关键列；单位 ms，hc=history_count）

| turn | total | narrator | repair | repaired | hc | pt/ct |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 9831 | 9759 | 0 | - | 1 | 2884/245 |
| 2 | 12589 | 12469 | 0 | - | 3 | 2943/190 |
| 3 | 10892 | 10844 | 0 | - | 5 | 2946/195 |
| 4 | 29455 | 29406 | 0 | - | 7 | 3048/383 |
| 5 | 36750 | 8343 | 28365 | ✓ | 9 | 3256/67 |
| 6 | 39768 | 8775 | 30941 | ✓ | 11 | 3428/108 |
| 7 | 44846 | 8434 | 36353 | ✓ | 13 | 3592/70 |
| 8 | 9961 | 9910 | 0 | - | 15 | 3758/251 |
| 9 | 10830 | 10777 | 0 | - | 17 | 3911/302 |
| 10 | 32543 | 9289 | 23212 | ✓ | 19 | 4092/101 |
| 11 | 34267 | 9931 | 24268 | ✓ | 20 | 4095/111 |
| 12 | 21522 | 8573 | 12900 | ✓ | 20 | 4170/66 |
| 13 | 65577 | 16846 | 48680 | ✓ | 20 | 4234/53 |
| 14 | 32921 | 21374 | 11497 | ✓ | 20 | 4280/85 |
| 15 | 46738 | 10903 | 35795 | ✓ | 20 | 4337/137 |
| 16 | 24727 | 8945 | 15725 | ✓ | 20 | 4403/104 |
| 17 | 42895 | 15820 | 27025 | ✓ | 20 | 4406/75 |
| 18 | 47869 | 24211 | 23592 | ✓ | 20 | 4465/100 |
| 19 | 19547 | 8996 | 10509 | ✓ | 20 | 4551/84 |
| 20 | 34016 | 24300 | 9665 | ✓ | 20 | 4554/103 |

（judge elapsed 全 0，非延迟源，未列）

### 汇总

- 平均回合 **~30.4s**（max 65.6s @turn13，min 9.8s @turn1）—— 比 `local-visible-p1-final-20260706` 的 ~25.9s 更高。
- **repair 率 70%（14/20）**，repair 总 338.5s，**占总延迟 56%**。
- narrator 首次调用平均 ~13.4s（8-29s），repair 平均 ~24s（10-49s）。
- **history_count 回合 11 达 20（cap），之后（turn 10-20）repair 率 ~100%**。
- prompt_chars 5174→7667、prompt_tokens 2884→4554 稳定增长，非主导因素。

### 结论（数据驱动）

**narrator 输出契约失效是当前延迟主因**。narrator 频繁返回不完整输出（触发 repair），repair 占 56% 总延迟；history 增长（hc≥19）后加剧（repair 率从 hc<9 的 0% 升到 hc≥19 的 ~100%）。

杠杆排序：

1. **history 压缩**（最高杠杆）—— hc cap 20 后 narrator 上下文质量下降 → repair 频发。第一批代码切片已把 narrator prompt 压缩为“开场上下文 + 省略占位 + 最近 6 条”，并通过 `local-visible-history-softcap-c1d8628-20260707` 复采：repair 0/20，prompt 约 6.3k-6.7k，但平均/最大耗时仍偏高。
2. **narrator 输出契约/解析器重构**（次高，高风险）—— `nodes.py` 539 行解析器堆积 + 契约松导致 parse 失败/repair。重构留独立批次，但本采样证明它确是根因。
3. **repair 是契约失效的后果，不是独立杠杆** —— 降 repair 要靠契约/解析器/history。
4. judge elapsed 全 0（非源）；provider narrator 首次 ~13.4s（可接受）。

**注**：本采样 repair 率（70%）与 `local-visible-p1-final-20260706`（0/20）差异大，可能因模型 key/版本/配置不同。后续 narrator 重构批次必须以本基线（或更新的实时采样）为准，不复用 p1-final 数字。

## 剩余 P0 风险

| 问题 | 当前状态 | 下一步 |
| --- | --- | --- |
| 生产 P0 回归风险 | 2026-07-02 生产 start+choice non-fallback 已通过。P0 当前不阻塞玩法迭代。 | 后续每次生产部署、模型配置变更或 provider 变更仍需由服务器线程复跑 health/catalog/account flow/start+choice non-fallback，且不输出 secrets。 |
| Chrome 验收与 pytest 共库并发 | `tests\web` 会逐测清空 `TEST_DATABASE_URL`，与可见 Chrome 共用库会造成 users/sessions/game_turns 突然归零的假象。 | Chrome 验收使用独立 DB，或确认无 pytest 并发后再跑。 |

## 剩余 P1 技术债

| 问题 | 风险 | 处理方向 |
| --- | --- | --- |
| live model 响应慢 | 2026-07-09 `final2` 内容审查中，D 路线平均约 14.4s、最大约 64.2s；mixed 长局平均约 9.3s、最大约 64.1s。历史 `local-visible-history-softcap-c1d8628-20260707` 仅作对比。 | 继续优化 narrator 输出契约、judge 超时/触发成本，并评估 provider 性能；不要把某一批平均值下降误判为长尾达标。 |
| narrator repair / judge 依赖 | Ordinary-turn repair 仍为 0，但 narrator 结构化输出依赖规则兜底明显：mixed 长局 `narrator_incomplete_output_count=46/49`、`judge_count=4`。 | 保持不接受缺叙事/缺可用选项；继续收紧模型契约，让模型返回完整结构，而不是长期依赖规则 delta 和 choice recovery。 |
| 20 回合内容体验不足 | 2026-07-09 `final2` 已用真实 Chrome 覆盖 base、A/B/C/D 路线和 mixed 长局，玩家可见兜底文案、明显重复和 P0/P1 内容审查项为 0；但事件深度、路线长期差异和终局页证据采集仍需继续做。 | 继续丰富事件池、阶段目标和路线差异，减少重复闭关/突破循环，并用内容审查证据确认。 |
| 叙事与权威状态落账 | 本轮把属性成长叙事改为按最终落账 delta 校验，并补了功法/关键道具 Judge 触发；突破和可见文本清洗已有覆盖。 | 继续扩展普通回合称号、关系、伤势、寿元、karma 的结构化落账/自然改写/压制测试。 |
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
- 观测数据不是性能修复；本轮证明 repair 可降为 0，但总耗时仍高，说明必须区分 repair、provider、narrator、judge 各自成本。
- 数据库结构治理要先查实际 PG metadata、Alembic 和运行时写入路径，再决定是否改约束；中文注释这类元数据变更应走 Alembic，并用测试确认真实落库。
- PostgreSQL 的 `text` 不是默认性能问题；优化优先级应来自慢查询、索引、分页和大字段读取模式，而不是批量改 `varchar(n)`。
- 本地服务启动要先恢复 PostgreSQL，再分别启动后端和 Vite；`tests\web`、全量 pytest 和真实 Chrome 验收不要并发共用同一个测试库，避免 FK/table/invite-code 噪声被误判成产品状态丢失。
- 本地页面验证前要确认后端和 Vite 进程不是早于最新代码提交启动；若进程启动时间早于提交时间，先重启服务再判断页面是否仍有旧问题。
- 动态开局已经解决“静态模板感”的底座问题，但不等于 20 回合内容体验已达标；后续仍要围绕阶段反馈、事件池、状态落账和模型效率继续小步迭代。
- 模型输出边界必须防御式处理：`state_delta.character/world/meta` 这类嵌套结构即使格式错误，也应记录并忽略，而不是让一次坏模型输出打断整回合。
- Web 可见状态必须来自“当前态”而不是历史事件扫描；`fallback_prompt.active` 这类 UI 提示要有明确恢复/清除语义，并能在 runner 重建后从持久化事件恢复。
- API 输入兼容应贴近引擎真实契约：允许 `choice_index`、A/B/C/D 和 `"1"`-`"4"` 这类明确选项，但继续拒绝自由文本和越界值，避免测试脚本、前端和后端各自理解一套选择格式。
- 多轮真实浏览器内容审查比单局 20 回合更适合暴露玩家体验问题；base、A/B/C/D 路线、mixed 长局和异常专项应分开记录，才能区分技术可跑通、路线差异、重复叙事和异常交互。
- UI 全文、外界情报、时间线、选项和 API 指标要一起进入 strict JSON/NDJSON/CSV；玩家可见文本本身是一等验收证据，不能只看 fallback、repair、耗时。
- 重复叙事去重不能吞掉权威状态变化；如果文本声称寿元、属性、境界、伤势、功法、关键道具等变化，必须先确认最终 delta 承接或自然改写，再决定是否替换重复文本。

失败教训：

- 服务健康和账号流通过不代表 live model 成功；`fallback_active=true` 且 `turn_count=0` 仍是阻断问题。
- 验收脚本自身可能失败，必须区分脚本 bug 和产品 bug；脚本要尽量短、可复核、输出脱敏摘要。
- 浏览器证据必须机器可读；损坏 JSON 会削弱后续自动审计可信度。
- UI 问题需要真实浏览器看页面，单靠 API 不会暴露。
- 历史草案留在当前文档树会诱导后续智能体误读；清理后只保留权威文档和 changelog。
- `game_turns.run_id` 的名字容易被误读成终局 `game_runs(id)` 外键；当前运行时它等于 `session_id`，贸然加外键会阻断局中回合落库，后续若要强关系必须先做语义迁移。
- 只看历史 `model_failure` 事件会把已经恢复的 live 回合继续误报成 fallback；凡是“当前提示/当前故障”都不要用“历史是否出现过某事件”替代状态机。
- 结构化 delta 不能假设模型永远返回 dict；列表、字符串或空值进入权威状态路径时，如果没有边界校验，就会把模型格式问题升级成产品崩溃。
- P0/P1 内容审查为 0 不等于 narrator 契约已解决；`narrator_incomplete_output_count` 仍高时，只能说明规则 delta 和 choices recovery 暂时兜住了玩家流程，不能把它当成模型输出质量达标。
- 自然终局不是失败，但终局页 UI 快照缺失仍是证据缺口；API 已证明 terminal state 时，报告要把“流程通过”和“终局页采集不足”分开写。

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
