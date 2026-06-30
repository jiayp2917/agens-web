# agens-novel-web

Web-only 文字修仙模拟器。当前 `master` 是浏览器版本主线：React/Vite 前端、FastAPI 后端、PostgreSQL 数据库和 `src/agens_novel/` 游戏核心。

## Current Status

- 当前玩法是游戏模式 v5 Alpha：A/B/C/D 四按钮固定语义，A 稳妥 / B 机遇 / C 风险 / D 气运。
- 数据库路线是 PostgreSQL-only；本地和生产都以 Alembic schema 为准。
- 用户级模型设置已本地落地：注册用户可保存个人 provider/base URL/model/API key，访客不可配置，无个人配置时使用系统 Agens 默认。
- 模型 API key 只允许后端加密存储和脱敏展示，不得出现在响应、日志、存档、session snapshot、前端包或文档中。
- 角色创建六维属性池已按 `docs/GAME_MODE_SPEC.md` §4.1 收束：手动单项 2-8、总和 30；随机单项 0-10、总和 30。
- 最新本地自动化基线：本地 PostgreSQL 可用；`tests\web` 63 passed；带 `TEST_DATABASE_URL` 的全量 `pytest -q` 432 passed；前端 build 通过。
- 最新本地真实 Chrome 验收：登录、系统默认模型、个人模型配置保存/清除、角色创建、20 回合、存档/读档、`game_turns` 连续性均通过；20 个 choice 请求均 non-fallback，但仍有 P1 体验问题（响应慢、突破选项约束、叙事/状态落账）。
- 最新生产批次：服务器线程已部署当前包并迁移到 Alembic `20260622_0005`，`user_model_configs` 存在，public/origin health、catalog、容器健康和日志敏感标记扫描通过；一次性真实账号注册、登录、存档、读档、跨会话恢复通过。
- 尚未完成：production live model 非 fallback 验收。生产开局为 non-fallback，但一回合选择返回 `fallback_active=true` 且 `turn_count=0`，不能按 live model 成功验收。

## Local PostgreSQL

本地 PostgreSQL 预期运行在 `127.0.0.1:55432`。启动前先检查，不要重复启动：

```powershell
cd D:\chat\agens-web
F:\pg\bin\pg_isready.exe -h 127.0.0.1 -p 55432
$env:TEST_DATABASE_URL = "postgresql+psycopg://agens_test@127.0.0.1:55432/agens_web_test"
```

如果 `pg_isready` 已接受连接，直接跑测试；不要删除 `.tmp\pg-test-20260626-55432`。如果未启动，可用脚本恢复：

```powershell
.\scripts\start_local_pg.ps1
```

注意：`tests\web` 会在每个测试前清空 `TEST_DATABASE_URL` 指向的测试库。真实 Chrome 验收不要和 pytest 共用同一个库并发运行，否则会看到 users/sessions/game_turns 突然归零的假象。

## Development

```powershell
cd D:\chat\agens-web
python -m venv .venv
.\.venv\Scripts\activate
pip install -e ".[dev]"
cd web\frontend-react
npm install
npm run build
cd ..\..
.\.venv\Scripts\python.exe -m uvicorn web.backend.app:app --host 127.0.0.1 --port 8000 --reload
```

如未完成 editable install，启动后端前临时设置源码路径：

```powershell
$env:PYTHONPATH = "D:\chat\agens-web\src"
```

## Baseline Checks

```powershell
cd D:\chat\agens-web
$env:TEST_DATABASE_URL = "postgresql+psycopg://agens_test@127.0.0.1:55432/agens_web_test"
.\.venv\Scripts\python.exe -m compileall -q src tests web scripts migrations
.\.venv\Scripts\python.exe -m pytest -q tests\web
.\.venv\Scripts\python.exe -m pytest -q
cd web\frontend-react
npm.cmd run build
```

## Model Settings Rule

- Ordinary registered users use `/api/settings/model` for personal settings.
- Admins use `/api/admin/settings/model` for the system default Agens config.
- Guests receive 401 on model settings.
- Production must set `MODEL_CONFIG_SECRET` before encrypted key storage can work.
- Do not inject user keys into process-global `os.environ`.

## Docs

- [docs/INDEX.md](docs/INDEX.md)：文档入口和阅读路由。
- [docs/RUNTIME_FLOW.md](docs/RUNTIME_FLOW.md)：当前运行链路和本地启动。
- [docs/GAME_MODE_SPEC.md](docs/GAME_MODE_SPEC.md)：游戏模式 v5 规则规格。
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)：模块地图。
- [docs/PROJECT_AUDIT.md](docs/PROJECT_AUDIT.md)：结构边界、已清理内容和剩余风险。
- [docs/NEXT_GOVERNANCE_BACKLOG.md](docs/NEXT_GOVERNANCE_BACKLOG.md)：下一批治理工作。
- [docs/security.md](docs/security.md)：密钥和公网 Alpha 安全边界。
- [docs/PRODUCTION_V5_MIGRATION_CHECKLIST.md](docs/PRODUCTION_V5_MIGRATION_CHECKLIST.md)：生产迁移和验收门槛。
- [docs/archive/](docs/archive/)：历史计划、Alpha 复盘和旧 UI 原型。
