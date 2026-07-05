# Web 运行流程

## 当前实现状态

- 产品入口是 React/Vite 浏览器 UI + FastAPI 后端 + PostgreSQL；旧移动端、旧 CLI/REPL、旧 `web/frontend` 不在当前维护范围。
- 当前玩法是游戏模式 v5 Alpha：A/B/C/D 四按钮固定语义，A 稳妥、B 机遇、C 风险、D 气运；无自由文本主入口，无 HP/MP 常驻 UI。
- 模型设置为注册用户个人配置 + 系统 Agens 默认兜底；用户 key 加密存储，不写入前端、日志、文档、存档或 session snapshot。
- 当前本地自动化基线：本地 PostgreSQL 可用；动态开局批次 `compileall` passed，`tests\web` 73 passed，全量 `pytest -q` 495 passed，前端 build passed，`git diff --check` 仅 LF/CRLF warning。新增 profile-aware opening 相关单测与 Web/API 覆盖。
- 当前本地真实 Chrome 验收：`local-visible-dynamic-opening-20260706-strict-live5` 已完成动态开局 live start gate（`start_model_ok=true`、`start_fallback=false`、4 个初始 choices、动态世界字段存在）、20/20 choice non-fallback 和存读档；平均回合耗时约 26.7s，最大约 46.2s，narrator repair 18/20 仍是 P1 风险。
- 当前生产 P0：服务器线程部署 `25ad3d15` 后，账号流通过，production start 和至少 1 次 choice 均 non-fallback，choice 后 `turn_count=1`。未来生产部署或模型配置变更仍需复跑同一门禁；HTTP 200 或本地 final2 不能替代生产 live-model 验收。
- 当前本地代码已加入脱敏模型性能观测；这不代表性能已修复，最新 Chrome 采样显示 repair 依赖仍高，下一步应继续分辨 prompt/history、repair、judge 和 provider 慢因。
- 当前动态开局批次把角色创建后的开局生成改为 profile-aware opening payload：难度、天赋、灵根、家世、六维属性和随机/手选模式共同影响本局世界观、0-16 岁编年史、16 岁初始局势、外界情报和首次 A/B/C/D choices。模型未启用或失败时使用差异化本地 fallback；该 fallback 可玩但不算 live-model 成功。
- 当前阶段计划见 `docs/PLAYABLE_GAMEPLAY_ROADMAP_20260629.md`；当前待办见 `docs/NEXT_GOVERNANCE_BACKLOG.md`。
本文记录当前 Web-only 运行链路。产品入口是浏览器 UI + FastAPI 后端，不再包含移动端打包或设备验证路径。

## 本地启动

```powershell
cd <repo>
.\scripts\start_local_pg.ps1
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m uvicorn web.backend.app:app --host 127.0.0.1 --port 8000 --reload
```

如果当前虚拟环境尚未完成 editable install，先临时显式设置源码路径：

```powershell
$env:PYTHONPATH="D:\chat\agens-web\src"
$env:SESSION_COOKIE_SECURE="0"
.\.venv\Scripts\python.exe -m uvicorn web.backend.app:app --host 127.0.0.1 --port 8000
```

浏览器打开：

```text
http://127.0.0.1:8000/
```

## 业务流程

1. 首页
   - 生产入口加载 `web/frontend-react/dist/index.html`。
   - 旧 `web/frontend` 已归档删除，不再作为 fallback 或产品入口。
   - 首页提供新游戏、读档、教程、设置、邀请码注册入口和背景音乐开关。
   - 新游戏允许访客直接进入角色创建；读档/设置打开弹窗，不再强制跳登录页。
   - Web 端不执行“关闭程序”，结束本局只清理当前局状态并返回首页。

2. 设置
   - GET /api/settings/model returns the logged-in user effective model config summary with source user/system; guests receive 401.
   - POST /api/settings/model saves only the current user personal provider/base_url/model/API key. DELETE /api/settings/model clears the personal config and falls back to system Agens.
   - GET/POST /api/admin/settings/model is admin-only and manages the system default config.
   - API keys are stored in PostgreSQL as application-encrypted material; responses expose only api_key_set and masked state, never raw keys or process-global environment writes.

3. 会话
   - `POST /api/auth/register` 使用邀请码注册。
   - `POST /api/auth/login` 登录并设置 HttpOnly Session Cookie。
   - `GET /api/auth/me` 读取当前登录用户。
   - 未登录调用 `POST /api/sessions` 创建访客 Web 会话，并设置 HttpOnly 访客 Cookie。
   - 已登录调用 `POST /api/sessions` 创建账号 Web 会话。
   - 后端为每个 Web 会话持有一个 `GameEngine` runner。
   - 账号会话快照写入数据库，可在服务重启后从数据库恢复。
   - 访客会话只保留在当前后端进程内存中，不写入 `users`、`sessions` 或 `saves`。

4. 角色创建
   - 前端角色页提交角色名、天赋、灵根、家世、难度和六维属性；不再提交游戏名称或隐藏开局码。
   - 六维属性遵循 `docs/GAME_MODE_SPEC.md` §4.1：手动模式单项 2-8 且总和必须为 30；随机模式单项 0-10 且总和固定为 30。后端会重新校验角色创建入参。
   - 运行时六维属性统一按 0-10 解析，5 为中性默认值；旧 0-100 存档、World Builder 输出或 catalog 元数据只作为兼容输入迁移，不再作为新逻辑尺度。
   - 随机模式提交前端展示的随机属性池；后端只在随机模式未带属性时兜底生成新池，避免“看到的随机值”和实际入局值不一致。
   - `POST /api/sessions/{id}/start` 调用 `GameEngine.start_from_profile()`。
   - World Builder 负责开场世界观、0-16 岁编年史、16 岁初始局势和 A/B/C/D；无 key 或模型失败时先走用户 fallback 决策，继续后使用同一 profile 输入生成差异化本地开局，不再默认退回固定 `misty_gate` 本地故事。fallback 仍通过 `fallback_prompt.active=true` 暴露，不能算 live-model 成功。
   - 特殊开局只由后端识别，前端不明示隐藏规则。

5. 回合推进
   - A/B/C/D 固定按钮调用 `POST /api/sessions/{id}/choice`，D 为气运/天命路线。
   - `POST /api/sessions/{id}/action` 仅保留给兜底“继续本局”和兼容调用，不再作为 React 主入口的自由文本输入。
   - 后端把行动交给 `GameEngine.handle_action()`，引擎继续负责 Narrator、必要 Judge、状态落账、事件化斗法、突破、死亡和飞升。
   - 本地故事无效输入只提示并保留当前选项，不消耗回合；重复选择自循环节点会生成变化文本，避免完全相同叙事连发。
   - 正式突破成功/失败会写入 `turn_history`，账号局后续可持久化为连续 `game_turns`。
   - API 响应统一返回叙事事件、角色状态、世界状态、A/B/C/D、回合数和终局状态。

6. 存读档
   - `POST /api/sessions/{id}/save` 将当前 `GameSession.to_save_dict()`、事件和 chat_history 写入数据库。
   - `POST /api/sessions/{id}/load` 从数据库还原 `GameSession.from_save_dict()`。
   - `GET /api/saves` 返回当前用户存档摘要。
   - 存读档只对邀请码注册/登录用户开放。
   - 访客局可以继续当前局，但不提供云端保存、读档或跨刷新恢复。

7. 结束本局
   - `POST /api/sessions/{id}/end` 将当前会话置为终局，浏览器进入结束页。
   - Web 端不尝试关闭浏览器或后端进程。

## 代码链路

```text
Browser UI
  -> web/backend FastAPI
  -> WebGameService / WebRunner
  -> GameEngine
  -> World Builder / Narrator / Judge
  -> GameSession.apply_delta()
  -> PostgreSQL snapshots / saves
  -> Browser UI
```

关键约束：

- Web 前端只调用 API，不直接修改 `GameSession`。
- `GameEngine` 仍是唯一游戏逻辑入口。
- API key 不进入前端包、日志、文档或 Git。
- 外网首版为访客新局 + 邀请码注册存档，登录态使用 HttpOnly Cookie。
- 访客局必须持有服务端下发的 HttpOnly 访客 Cookie 才能继续操作该局。
- 生产数据库通过 `DATABASE_URL=postgresql+psycopg://...` 接入（PostgreSQL 单后端；`DATABASE_BACKEND` 已不再是生产信号）。
- 生产 PostgreSQL schema 由 Alembic 迁移创建，应用启动不隐式建表；catalog 和死亡奖励表也必须由迁移覆盖。
- PostgreSQL 启动后可补充 catalog 种子数据，但不能依赖应用隐式建表。
- 状态变更 API 需要同源/允许来源校验。
- 生产模式关闭 `/docs`、`/redoc`、`/openapi.json`，并启用 Host 白名单。
- 当前 React 主入口已切到游戏模式 v5 Alpha：A/B/C/D 四按钮固定语义，支持访客新局、邀请码账号存档，以及注册用户个人模型配置。
- 境界顺序固定为：练气、筑基、金丹、元婴、化神、合体、大乘、渡劫、飞升。
- 侧栏“外界情报”只展示现有世界摘要和 lore，不写入状态；权威状态仍由 `GameEngine` 和 `GameSession.apply_delta()` 结算。

## 验证

```powershell
.\.venv\Scripts\python.exe -m compileall -q src tests web
$env:TEST_DATABASE_URL = "postgresql+psycopg://agens_test@127.0.0.1:55432/agens_web_test"
.\.venv\Scripts\python.exe -m pytest -q tests/web
.\.venv\Scripts\python.exe -m pytest -q
```

`tests\web` 的 autouse fixture 会在每个测试前 truncate `TEST_DATABASE_URL` 指向的应用表。真实 Chrome 验收必须避免和 pytest 共用同一个数据库并发运行；否则账号、session、game_turns 被清空属于测试隔离副作用，不足以单独判定为产品 bug。

## 2026-06-28 Model Settings Runtime Flow

- `GET /api/settings/model` returns the logged-in user's effective config summary with `source: "user" | "system"`; guests receive 401.
- `POST /api/settings/model` saves only the current user's personal config. `DELETE /api/settings/model` clears it and falls back to system Agens.
- `GET/POST /api/admin/settings/model` manages the system default config and requires admin auth.
- During gameplay, `WebGameService` resolves the current session user's effective config and passes it into `GameEngine`/agent calls explicitly. User keys are not injected into process-global `os.environ`.
