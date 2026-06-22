# agens-novel-web

Web-only 文字修仙模拟器。当前 `master` 是浏览器版本主线。

## 当前目标

复用 `src/agens_novel/` 核心游戏逻辑，提供 FastAPI 后端、React/Vite 浏览器 UI、SQLite 本地后端、PostgreSQL 生产后端、邀请码账号存档和脱敏模型配置管理。

## 当前玩法

1. 当前主入口是游戏模式 v5 Alpha。
2. 玩家每回合在 A/B/C/D 四个固定语义按钮中选择：A 稳妥、B 机遇、C 风险、D 气运。
3. D 不再是自由输入；气运/天命路线由规则引擎结算。
4. 无 key、模型失败或无有效选项时，用户可选择本地故事兜底继续或结束本局。
5. 小说模式、引导模式暂时只作为禁用入口保留。

## 推荐 Web 架构

```text
Browser UI
  -> web/backend FastAPI
  -> GameEngine
  -> World Builder / Narrator / Judge
  -> GameSession / SQLite or PostgreSQL Database
```

## 开发入口

```powershell
cd <repo>
python -m venv .venv
.\.venv\Scripts\activate
pip install -e ".[dev]"
cd web\frontend-react
npm install
npm run build
cd ..\..
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
.\.venv\Scripts\python.exe -m compileall -q src tests web scripts migrations
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pytest -q tests/web
cd web\frontend-react
npm run build
```

## 文档

- [docs/INDEX.md](docs/INDEX.md)：文档入口。
- [docs/WEB_ITERATION_PLAN.md](docs/WEB_ITERATION_PLAN.md)：Web-only 迭代计划。
- [docs/PROJECT_AUDIT.md](docs/PROJECT_AUDIT.md)：结构边界、瘦身清单和技术债。
- [docs/RUNTIME_FLOW.md](docs/RUNTIME_FLOW.md)：当前核心运行流程。
- [docs/security.md](docs/security.md)：密钥与安全边界。
