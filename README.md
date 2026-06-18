# agens-novel-web

Web-only 文字修仙模拟器。当前 `master` 是浏览器版本主线。

## 当前目标

复用 `src/agens_novel/` 核心游戏逻辑，提供 FastAPI 后端、浏览器 UI、SQLite 会话/存档和脱敏模型配置管理。

## 当前玩法

1. 角色创建后进入引导模式。
2. A/B/C 由模型基于上下文生成。
3. D 由玩家自由键入。
4. 无 key、模型失败或无有效选项时，用户可选择本地故事兜底继续或结束本局。
5. 小说模式、游戏模式暂时只作为禁用入口保留。

## 推荐 Web 架构

```text
Browser UI
  -> web/backend FastAPI
  -> GameEngine
  -> World Builder / Narrator / Judge
  -> GameSession / SQLite Database
```

## 开发入口

```powershell
cd <repo>
python -m venv .venv
.\.venv\Scripts\activate
pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m uvicorn web.backend.app:app --host 127.0.0.1 --port 8000 --reload
```

可选模型配置只允许在后端读取或保存脱敏状态，不得进入前端包：

```powershell
$env:AGNES_BASE_URL = "https://apihub.agnes-ai.com/v1"
$env:AGNES_MODEL    = "agnes-2.0-flash"
$env:AGNES_API_KEY  = "<your key>"
```

## 当前基线检查

```powershell
.\.venv\Scripts\python.exe -m compileall -q src tests
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pytest -q tests/web
```

## 文档

- [docs/INDEX.md](docs/INDEX.md)：文档入口。
- [docs/WEB_ITERATION_PLAN.md](docs/WEB_ITERATION_PLAN.md)：Web-only 迭代计划。
- [docs/PROJECT_AUDIT.md](docs/PROJECT_AUDIT.md)：结构边界、瘦身清单和技术债。
- [docs/RUNTIME_FLOW.md](docs/RUNTIME_FLOW.md)：当前核心运行流程。
- [docs/security.md](docs/security.md)：密钥与安全边界。
