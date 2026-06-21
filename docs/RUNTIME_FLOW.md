# Web 运行流程

> **当前实现状态：引导模式 Alpha。** 本文描述的是当前可运行的 Alpha 版本实现，不是游戏模式 v5 规格。游戏模式 v5 是下一阶段规格，详见 `docs/GAME_MODE_SPEC.md`（草案 v5 / 待批准立项）。

本文记录当前 Web-only 运行链路。产品入口是浏览器 UI + FastAPI 后端，不再包含移动端打包或设备验证路径。

## 本地启动

```powershell
cd <repo>
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
   - 生产入口优先加载 `web/frontend-react/dist/index.html`；旧 `web/frontend/index.html` 只作为 fallback。
   - 首页提供新游戏、读档、教程、设置、邀请码注册入口和背景音乐开关。
   - 新游戏允许访客直接进入角色创建；读档/设置打开弹窗，不再强制跳登录页。
   - Web 端不执行“关闭程序”，结束本局只清理当前局状态并返回首页。

2. 设置
   - `GET /api/settings/model` 返回脱敏模型配置，仅管理员可访问。
   - `POST /api/settings/model` 更新 provider、base_url、model 和可选 API key，仅管理员可访问。
   - API key 只进入当前后端进程环境和数据库脱敏摘要，不返回前端明文。

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
   - 前端角色页提交游戏名称、角色名、天赋、灵根、家世、难度和属性。
   - `POST /api/sessions/{id}/start` 调用 `GameEngine.start_from_profile()`。
   - World Builder 负责开场叙事和 A/B/C；无 key 或模型失败时进入本地故事兜底，并在前端提供继续或结束本局。
   - 特殊开局只由后端识别，前端不明示隐藏规则。

5. 回合推进
   - A/B/C 按钮调用 `POST /api/sessions/{id}/choice`。
   - D 输入框调用 `POST /api/sessions/{id}/action`。
   - 后端把行动交给 `GameEngine.handle_action()`，引擎继续负责 Narrator、Judge、状态落账、战斗、突破、死亡和飞升。
   - API 响应统一返回叙事事件、角色状态、世界状态、A/B/C、回合数和终局状态。

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
  -> SQLite or PostgreSQL snapshots / saves
  -> Browser UI
```

关键约束：

- Web 前端只调用 API，不直接修改 `GameSession`。
- `GameEngine` 仍是唯一游戏逻辑入口。
- API key 不进入前端包、日志、文档或 Git。
- 外网首版为访客新局 + 邀请码注册存档，登录态使用 HttpOnly Cookie。
- 访客局必须持有服务端下发的 HttpOnly 访客 Cookie 才能继续操作该局。
- 生产数据库通过 `DATABASE_BACKEND=postgresql` 和 `DATABASE_URL=postgresql+psycopg://...` 接入。
- 生产 PostgreSQL schema 由 Alembic 迁移创建，应用启动不隐式建表；catalog 和死亡奖励表也必须由迁移覆盖。
- PostgreSQL 启动后可补充 catalog 种子数据，但不能依赖应用隐式建表。
- 状态变更 API 需要同源/允许来源校验。
- 生产模式关闭 `/docs`、`/redoc`、`/openapi.json`，并启用 Host 白名单。
- 当前 Alpha 实现仍是引导模式：A/B/C 模型选项 + D 自由输入，支持访客新局 + 邀请码存档。游戏模式 v5 规格见 `docs/GAME_MODE_SPEC.md`。
- 境界顺序固定为：练气、筑基、金丹、元婴、化神、合体、大乘、渡劫、飞升。

## 验证

```powershell
.\.venv\Scripts\python.exe -m compileall -q src tests web
.\.venv\Scripts\python.exe -m pytest -q tests/web
.\.venv\Scripts\python.exe -m pytest -q
```
