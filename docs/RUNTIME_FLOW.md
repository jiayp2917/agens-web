# Web 运行流程

本文只记录当前运行链路。玩法规则以 `GAME_MODE_SPEC.md` 为准，历史证据以
`CHANGELOG.md` 为准。

## 1. 运行边界

- React/Vite 浏览器 UI 只调用 API，不直接修改 `GameSession`。
- `GameEngine` 是玩法门面，外部仍调用 `start_from_profile()`、`handle_action()` 和 `attempt_breakthrough()`。
- PostgreSQL 是唯一数据库；生产 schema 只由 Alembic 管理。
- 注册用户模型配置按 `user_id` 隔离；系统默认配置使用独立 admin API。
- fallback 可继续本地故事，但不是 live-model 成功。

## 2. 本地启动

```powershell
cd D:\chat\agens-web
.\scripts\start_local_pg.ps1
$env:DATABASE_URL = "postgresql+psycopg://agens_test@127.0.0.1:55432/agens_web_test"
$env:AGENS_PG_AUTO_DDL = "1"
$env:SESSION_COOKIE_SECURE = "0"
$env:PYTHONPATH = "D:\chat\agens-web\src"
.\.venv\Scripts\python.exe -m uvicorn web.backend.app:app --host 127.0.0.1 --port 8000 --reload
```

```powershell
cd D:\chat\agens-web\web\frontend-react
npm.cmd run dev -- --host 127.0.0.1 --port 5173
```

浏览器访问 `http://127.0.0.1:5173/static/`。

## 3. 认证与访客会话

1. `POST /api/auth/register` 在一个事务内消费邀请码并创建用户；首管理员创建使用 PostgreSQL advisory transaction lock。
2. `POST /api/auth/login` 验证账号并设置 HttpOnly `agens_session` Cookie。
3. 未登录 `POST /api/sessions` 时，后端生成 HttpOnly `agens_guest` Cookie，并把访客 session 写入 PostgreSQL。
4. 访客 session 以 token hash 绑定，默认 24 小时过期，可跨后端进程恢复。
5. 登录或注册成功后，后端删除当前访客 session，清除访客 Cookie；前端清除活动 session 并回到账号态，不迁移访客局。

## 4. 模型设置

- `GET /api/settings/model`：返回当前用户有效配置摘要及 `source: user|system`。
- `POST /api/settings/model`：保存当前用户个人配置。
- `DELETE /api/settings/model`：删除个人配置并回到系统默认。
- `GET/POST /api/admin/settings/model`：管理员维护系统默认配置。
- API 只返回 provider、base URL、model、`api_key_set` 和 masked 状态，不返回原始 Key。
- PostgreSQL 只保存加密 Key；缺少 `MODEL_CONFIG_SECRET` 时解密 fail closed。
- 用户 Key 通过当前 session 的 runner 显式传入模型调用，不写进进程级 `os.environ`。

保存配置与每次请求都会校验模型 Base URL：

1. 只允许 HTTPS。
2. 拒绝用户信息、query、fragment 和 IP 字面量。
3. 官方域名内置允许；自定义域名必须在 `AGENS_MODEL_BASE_URL_ALLOWLIST`。
4. 请求前解析全部 A/AAAA，任何 loopback、private、link-local、reserved 或 multicast 地址都拒绝。
5. HTTPX 使用 `follow_redirects=False`、`trust_env=False` 和整体调用时限。

## 5. 创建会话与开局

```text
POST /api/sessions
  -> WebGameService.create_session()
  -> service_sessions.create_session()
  -> WebRunner(GameEngine)
  -> PostgreSQL sessions snapshot version=0
```

角色创建调用：

```text
POST /api/sessions/{id}/start
  request_id + expected_version + profile
  -> 每会话 RLock
  -> 幂等结果查询
  -> 个人/系统模型配置解析
  -> profile 校验与遗泽应用
  -> GameEngine.start_from_profile()
  -> StartFlow / World Builder 或 profile-aware fallback
  -> 同一事务写 session snapshot、active game_run、遗泽消费、幂等结果
  -> version + 1
```

`WebGameService` 只保留路由稳定门面、runner 管理与事务协调：开局和会话生命周期委托给
`service_sessions.py`，A/B/C/D 回合委托给 `service_turns.py`，存读档和结束委托给
`service_saves.py`。普通产品运行使用默认空 `EvaluationHooks`；评估 resolver、ledger 和
canonical hook 仅由隔离评估应用工厂注入。

六维属性由后端重新校验：手动单项 2-8、总和 30；随机单项 0-10、总和 30。运行时尺度统一为 0-10，5 为中性值。

## 6. 普通回合

前端固定使用 A/B/C/D 槽位。后端按槽位重新附加权威语义，模型文本中的错误路线标签不会覆盖：

```text
A -> 稳妥
B -> 机遇
C -> 风险
D -> 气运
```

```text
POST /api/sessions/{id}/choice
  request_id + expected_version + choice/choice_index
  -> 会话锁 + 幂等查询 + 版本检查
  -> TurnFlow.handle_action()
  -> ChoiceIntentV1 -> turn_rules.settle_turn() -> RuleTurnOutcomeV1
     计算时间、年龄、属性、寿元、事件和终局
  -> story_catalog 推进精确版本绑定的长期主线
  -> NarratorEnvelopeV1 生成短叙事与四个选项；Agens 可用 JSON Schema，其他 provider
     由 adapter 使用 JSON object 或兼容标签传输
  -> 可选 parsed state_update 只保留诊断，不进入权威状态
  -> 必要时 Judge 只给诊断裁定，不修改规则结果
  -> GameSession.apply_delta()
  -> 记录 turn_history
  -> 同一事务写 game_turns、session snapshot、终局 bundle 和幂等结果
  -> version + 1
```

重复 `request_id` 返回首次结果；`expected_version` 过期返回 409，前端重新读取权威 session。前端用同步 ref 阻止双击在 React 状态更新前重复发送。

## 7. 突破与终局

- `RealmSystem` 先生成成功/失败权威 delta；Judge 不得修改突破结果、境界、层数、寿元、飞升或终局字段。
- 飞升、死亡和突破回合先记录叙事与 turn history，再清空 choices 并触发终局回调。
- `GameSession.error` 随存档序列化和恢复，读档后终局原因保持一致。
- 终局 run、成就、奖励、玩家进度和遗泽使用同一事务及业务唯一约束；重试不会重复发奖。

## 8. 模型失败与契约恢复

模型请求失败时：

1. 事件流写入脱敏 model failure。
2. 引擎自动进入本地故事并生成四个选项。
3. `FallbackBanner` 只提示“已切换本地故事”，不显示无效“继续本局”按钮。
4. 玩家直接点击下方 A/B/C/D。
5. 本地故事同样调用 `settle_turn()`，推进年龄、寿元、阶段反馈和突破准备。

Narrator 请求成功但缺少叙事或四个 choices 时，普通回合可以用规则叙事和本地主线选项继续，但必须记录 `incomplete_output` / `contract_recovery`。`state_update` 不再是严格契约字段；即使兼容 parser 读到它，也只作为诊断。这种恢复不激活 provider fallback banner，也不算严格 live-model 成功。

## 9. 存读档与结束

- save/load/end 同样要求 `request_id` 与 `expected_version`。
- 存档只对登录用户开放；访客返回 401。
- save slot 与 session snapshot 在一个 mutation transaction 中写入。
- load 用存档恢复 runner，再通过 CAS 提交新 session version。
- load 同一事务截断存档回合之后的 `game_turns` 并同步 active run；已结算终局不允许原地覆盖历史。
- 旧存档没有 story binding 时按原世界补绑；已有但不可用的精确版本显式拒绝，不静默换线。
- end 写终局 bundle；手动重试通过幂等表返回原结果。

## 10. 健康与部署

- `/api/health` 会 ping PostgreSQL；不可用返回 503。
- `AGENS_ENV=prod` 和 `AGENS_ENV=production` 都按生产模式处理。
- 生产禁止 `AGENS_PG_AUTO_DDL=1`。
- Compose 先运行一次性 `agens-web-migrate`，成功后才启动应用副本。
- 应用镜像不在 entrypoint 中执行 Alembic。

## 11. 验证隔离

`tests\web` 会 truncate `TEST_DATABASE_URL` 指向的表。真实 Chrome 验收必须使用另一数据库，且不要与 pytest 并发运行。fallback 或 contract recovery 都不能算 live-model 成功，本地成功也不能替代生产验收。

迁移测试在同一 PostgreSQL 实例创建独立临时数据库，覆盖已有库升级、孤儿/重复数据回滚、downgrade/re-upgrade 和阻塞条件。备份恢复通过 `scripts/verify_pg_backup_restore.py` 使用另两座临时库执行，结束时无条件删除数据库和 dump 文件。

浏览器验收命令保持 `scripts/local_visible_playtest.cjs` 兼容；它将浏览器操作、持久化审计、可见内容审计、报告构造和纯函数裁决分离。脱敏 replay fixture 覆盖通过、失败、fallback、重复和状态冲突，不能写入仓库内运行证据。

## 12. 本地模型评估

评估进程用只读 `EvaluationModelConfigResolver` 替代产品模型解析器。Key 仅在一次 Agent
调用的私有运行时上下文读取，不能进入 session、Agent 可序列化 state、数据库、日志或证据。
`AGENS_EVALUATION_MODE=1` 时，`AGENS_ARTIFACT_ROOT` 必须位于仓库外；默认
`runtime/artifacts` 被禁用，所有持久化值在最终边界再次脱敏。启动/结束分别写入不含 prompt、
Key、Cookie、Authorization 或真实 Base URL 的 manifest 和 inventory hash。

能力 probe、20 回合 smoke、完整局和 Chrome 分别使用串行进程与独立 PostgreSQL 库。评估模式在
`AGENS_ENV=prod|production` 下会被 FastAPI 启动检查拒绝。真实 provider 结果必须标为
`llm_real`，不得被 fallback、repair 或 contract recovery 冒充严格成功。
