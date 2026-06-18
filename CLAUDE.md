# agens-novel-web — Web 开发说明

## 当前产品通路

本项目只保留浏览器 UI + FastAPI 后端产品入口。不要恢复终端交互入口、CLI 命令、旧 REPL UI 或移动端打包流程。

流程验证以 Web 后端 API、核心引擎测试和浏览器 UI 为准。

测试：

```powershell
.\.venv\Scripts\python.exe -m compileall -q src tests web
.\.venv\Scripts\python.exe -m pytest -q
```

## 架构边界

- Web UI 只通过 `web/backend` API 调用游戏逻辑。
- `GameEngine` 是唯一游戏逻辑入口。
- `GameSession` 位于 `src/agens_novel/session/game_session.py`。
- Web 会话和存档由 `web/backend/database.py` 写入 SQLite。
- Agent 调用器位于 `src/agens_novel/engine/turn_runner.py`。

## 入口说明

本地开发入口：

```powershell
.\.venv\Scripts\python.exe -m uvicorn web.backend.app:app --host 127.0.0.1 --port 8000 --reload
```

## UI 契约

- A/B/C 是模型基于上下文生成的建议选项。
- D 是底部自由输入框。
- 首页、角色创建、游戏页、设置、教程、存读档、死亡/飞升页是 Web 首期页面。
- 小说模式、游戏模式只作为禁用入口保留。
- 飞升页必须显示“飞升”，不得复用死亡标题。

## 禁止项

- 不把 API key 写入代码、文档、日志或持久化环境变量。
- 不在 UI 明示隐藏触发规则或隐藏模式名称。
- 不恢复已删除境界。
- 不回退用户已有工作区改动。
