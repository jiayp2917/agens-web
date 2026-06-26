# agens-novel-web

Web-only 文字修仙模拟器。当前 `master` 是浏览器版本主线。

## 当前目标

复用 `src/agens_novel/` 核心游戏逻辑，提供 FastAPI 后端、React/Vite 浏览器 UI、PostgreSQL 数据库（本地与生产统一）、邀请码账号存档和脱敏模型配置管理。

## 当前状态

- 2026-06-26 状态：本地测试已改为 PostgreSQL-only 验证；`TEST_DATABASE_URL` 指向安全本地测试库时，`tests\web` 已从“全跳过/部分跳过”变为真实执行 `50 passed`，全量 `pytest -q` 为 `415 passed`。
- 2026-06-26 本地 Chrome 验收已覆盖 PostgreSQL 下的访客开局/一回合、账号注册/登录/新局/存档/读档、2K 无横向溢出、窄屏无横向溢出；截图证据保存在 `output/`。本地 live-model 回合 HTTP 200，但耗时约 63 秒且结构化叙事诊断不完整，仍是 P1 风险。
- 2026-06-25 状态：执行代码审计方案 C，数据库统一为 PostgreSQL（删除 SQLite 后端，净减约 900 行）；P0 安全修复、P1 死代码清理、P2 PG-only 合并、P3 部分去重已完成，详见 CHANGELOG。
- 2026-06-24 状态为历史记录：当时本地 React + SQLite 主链路可运行；该本地 SQLite 路径已被 2026-06-25 Option C 的 PostgreSQL-only 路径取代。
- 已落地：编年史 UI、角色创建命数方案 A 折叠卡、首页 QQ 图标资产、A/B/C/D 固定语义、寿元剩余值显示、编年史年份权威化。
- 待确认：生产账号注册/登录/存档/读档、production live model 成功、公开 Alpha 日志/限流/Cookie/Origin 观察和备份恢复演练。
- 本机自动浏览器验收优先使用 Chrome DevTools MCP 或外部 Chrome；Codex 内置浏览器存在环境闪退风险。

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
  -> GameSession / PostgreSQL Database
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
# Requires a running safe local PostgreSQL test database.
$env:TEST_DATABASE_URL = "postgresql+psycopg://agens_test@127.0.0.1:55432/agens_web_test"
.\.venv\Scripts\python.exe -m compileall -q src tests web scripts migrations
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pytest -q tests/web
cd web\frontend-react
npm run build
```

## 文档

- [docs/INDEX.md](docs/INDEX.md)：文档入口。
- [docs/UI_REFACTOR_PLAN.md](docs/UI_REFACTOR_PLAN.md)：已确认 UI 原型和重构验收标准。
- [docs/PROJECT_AUDIT.md](docs/PROJECT_AUDIT.md)：结构边界、瘦身清单和技术债。
- [docs/RUNTIME_FLOW.md](docs/RUNTIME_FLOW.md)：当前核心运行流程。
- [docs/security.md](docs/security.md)：密钥与安全边界。
