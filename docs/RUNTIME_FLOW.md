# Web 运行流程

本文记录当前 Web-only 运行链路。产品入口是浏览器 UI + FastAPI 后端，不再包含移动端打包或设备验证路径。

## 本地启动

```powershell
cd <repo>
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m uvicorn web.backend.app:app --host 127.0.0.1 --port 8000 --reload
```

浏览器打开：

```text
http://127.0.0.1:8000/
```

## 业务流程

1. 首页
   - 浏览器加载 `web/frontend/index.html`。
   - 首页提供新游戏、读档、教程、设置、结束/返回首页和背景音乐开关。
   - Web 端不执行“关闭程序”，结束按钮只清理当前前端状态并返回首页。

2. 设置
   - `GET /api/settings/model` 返回脱敏模型配置。
   - `POST /api/settings/model` 更新 provider、base_url、model 和可选 API key。
   - API key 只进入当前后端进程环境和 SQLite 脱敏摘要，不返回前端明文。

3. 会话
   - `POST /api/users/login` 创建或读取本地用户。
   - `POST /api/sessions` 创建 Web 会话，后端为该会话持有一个 `GameEngine` runner。
   - 会话快照写入 SQLite，可在服务重启后从数据库恢复。

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
   - `POST /api/sessions/{id}/save` 将当前 `GameSession.to_save_dict()`、事件和 chat_history 写入 SQLite。
   - `POST /api/sessions/{id}/load` 从 SQLite 还原 `GameSession.from_save_dict()`。
   - `GET /api/saves` 返回当前用户存档摘要。

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
  -> SQLite snapshots / saves
  -> Browser UI
```

关键约束：

- Web 前端只调用 API，不直接修改 `GameSession`。
- `GameEngine` 仍是唯一游戏逻辑入口。
- API key 不进入前端包、日志、文档或 Git。
- 首期只开放引导模式：A/B/C 模型选项 + D 自由输入。
- 境界顺序固定为：练气、筑基、金丹、元婴、化神、合体、大乘、渡劫、飞升。

## 验证

```powershell
.\.venv\Scripts\python.exe -m compileall -q src tests web
.\.venv\Scripts\python.exe -m pytest -q tests/web
.\.venv\Scripts\python.exe -m pytest -q
```
