# agens-novel-web

Web-only 文字修仙模拟器。当前 `master` 是浏览器版本主线：React/Vite 前端、FastAPI 后端、PostgreSQL 数据库和 `src/agens_novel/` 游戏核心。

## Current Status

- 当前玩法是游戏模式 v5 Alpha：A/B/C/D 四按钮固定语义，A 稳妥 / B 机遇 / C 风险 / D 气运。
- 数据库路线是 PostgreSQL-only；本地和生产都以 Alembic schema 为准。
- 用户级模型设置已本地落地：注册用户可保存个人 provider/base URL/model/API key，访客不可配置，无个人配置时使用系统 Agens 默认。
- 模型 API key 只允许后端加密存储和脱敏展示，不得出现在响应、日志、存档、session snapshot、前端包或文档中。
- 角色创建六维属性池已按 `docs/GAME_MODE_SPEC.md` §4.1 收束：手动单项 2-8、总和 30；随机单项 0-10、总和 30。
- 运行时六维属性统一为 0-10 尺度，5 为中性默认值；旧 0-100 存档或模型输出只在加载/入局时兼容迁移，不能再作为新逻辑的默认尺度。
- 动态开局链路已接入：难度、天赋、灵根、家世、六维属性和随机/手选模式共同生成本局世界观、0-16 岁编年史、16 岁初始局势、外界情报和首次 A/B/C/D choices。模型未启用或失败时使用差异化 profile-aware fallback；fallback 可玩但不算 live-model 成功。
- 最新本地自动化基线：本地 PostgreSQL 可用；境界/突破/寿元一致性批次 `compileall` passed，`tests\web` 73 passed，全量 `pytest -q` 507 passed / 1 xfailed，前端 build passed，`git diff --check` 仅 LF/CRLF warning。
- 最新本地真实 Chrome 验收：2026-07-06 `local-visible-dynamic-opening-20260706-strict-live5` 通过，使用隔离 8001 后端验证动态开局 live path：`start_model_ok=true`、`start_fallback=false`、4 个初始 choices、动态世界名/0-16 岁编年史/16 岁初始局势存在，普通账号注册/登录、角色创建、20/20 choice non-fallback、存档/读档均通过；平均回合耗时约 26.7s，最大约 46.2s，repair 18/20 仍是 P1 风险。
- 最新生产批次：服务器线程已部署 `25ad3d15` 并迁移到 Alembic `20260622_0005`，`user_model_configs` 存在，public/origin health、catalog、容器健康和日志敏感标记扫描通过；一次性真实账号注册、登录、存档、读档、跨会话恢复通过。
- production live model P0 已通过脱敏验收：生产 start 和至少 1 次 choice 均为 non-fallback，choice 后 `turn_count=1`。历史 `model_config` 旧行遮蔽 env key 的失败保留为经验，后续不再作为当前阻塞。
- 尚未完成：P1 游玩质量和治理，包括 live 响应慢、narrator repair 依赖高、重复闭关/突破循环、叙事/权威状态落账和大文件复杂度治理。

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

如果脚本提示 stale `postmaster.pid`、日志权限或端口占用，不要直接删除数据目录。先确认端口和进程：

```powershell
F:\pg\bin\pg_ctl.exe status -D D:\chat\agens-web\.tmp\pg-test-20260626-55432
Get-NetTCPConnection -LocalPort 55432 -ErrorAction SilentlyContinue
```

只有确认没有 PostgreSQL 进程仍在使用该数据目录后，才按脚本提示处理 stale pid 或日志文件。

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

本地调试的常用服务入口：

```powershell
cd D:\chat\agens-web
.\scripts\start_local_pg.ps1
$env:DATABASE_URL = "postgresql+psycopg://agens_test@127.0.0.1:55432/agens_web_test"
$env:TEST_DATABASE_URL = "postgresql+psycopg://agens_test@127.0.0.1:55432/agens_web_test"
$env:AGENS_PG_AUTO_DDL = "1"
$env:SESSION_COOKIE_SECURE = "0"
$env:PYTHONPATH = "D:\chat\agens-web\src"
.\.venv\Scripts\python.exe -m uvicorn web.backend.app:app --host 127.0.0.1 --port 8000 --reload

cd D:\chat\agens-web\web\frontend-react
npm.cmd run dev -- --host 127.0.0.1 --port 5173
```

浏览器打开 `http://127.0.0.1:5173/`。后端健康检查为 `http://127.0.0.1:8000/api/health`。

如果本地后端或 Vite 进程早于最新代码提交启动，先重启后端和前端再做页面验证。`uvicorn --reload` 通常会重新加载 Python 文件，但真实 Chrome 验收和 UI 复核应避免使用旧进程状态。

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
- 历史计划、Alpha 复盘和旧 UI 原型已从 `docs/archive/` 清理；必要历史只保留在 `CHANGELOG.md` 和当前文档的经验摘要中。
