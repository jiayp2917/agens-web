# agens-web

Web-only 文字修仙模拟器。当前主线由 React/Vite、FastAPI、PostgreSQL 和
`src/agens_novel/` 游戏核心组成。

## Current Status

- 游戏模式 v5 Alpha：A/B/C/D 固定为 A 稳妥、B 机遇、C 风险、D 气运，无自由文本主入口，无 HP/MP 常驻 UI。
- PostgreSQL-only；Alembic 是 schema authority。当前 head 为 `20260710_0008_runtime_consistency`。
- 注册用户可保存个人模型配置；无个人配置时使用系统 Agens 默认；访客不可配置模型。
- 模型 Key 只以应用层密文写入 PostgreSQL，API、日志、存档、session snapshot 和前端包都不得出现原文。
- 自定义模型地址只允许 HTTPS 官方域名或 `AGENS_MODEL_BASE_URL_ALLOWLIST` 中的主机；请求前会解析全部 A/AAAA，任何非公网地址均拒绝。
- 访客局持久化到 PostgreSQL，默认保留 24 小时；登录或注册成功后删除当前访客局并清除访客 Cookie。
- start/choice/action/save/load/end 都要求 `request_id` 与 `expected_version`，后端通过会话锁、CAS 和幂等结果防止双击、重试和并发覆盖。
- 回合日志、session snapshot、活跃/终局 run、奖励和遗泽消费使用同一数据库事务；失败恢复内存 runner。
- fallback 会自动切换本地故事，玩家直接使用下方 A/B/C/D；fallback 不能算 live-model 成功。
- FastAPI 路由已拆为 auth/catalog/session/settings；`GameEngine` 仍是玩法门面，开局、普通回合、突破和 fallback 分别由 flow/policy 模块承担。
- 当前本地门禁：空库 Alembic 18 表升级通过；Ruff/C901/mypy 零错误；`tests\web` 92 passed；非 live 全量 pytest 594 passed；Vitest 5 passed；前端 build 通过；npm audit 0 vulnerabilities；真实 Chrome smoke 通过。

本轮只做本地实现和验证，未执行生产部署或生产验收。真实 Chrome smoke 使用无真实 Key 的 fallback 路径，不是 live-model 验收。历史生产证据只保留在 `CHANGELOG.md`，不能代表当前未部署工作树。

## Local PostgreSQL

```powershell
cd D:\chat\agens-web
F:\pg\bin\pg_isready.exe -h 127.0.0.1 -p 55432
$env:TEST_DATABASE_URL = "postgresql+psycopg://agens_test@127.0.0.1:55432/agens_web_test"
```

若未启动：

```powershell
.\scripts\start_local_pg.ps1
```

不要在 PostgreSQL 仍运行时删除 `.tmp\pg-test-20260626-55432` 或手工处理
`postmaster.pid`。先检查 `pg_isready`、`pg_ctl status` 和端口占用。

`tests\web` 会在每个测试前 truncate `TEST_DATABASE_URL` 指向的应用表。真实浏览器验收必须使用独立数据库，且不要与 pytest 并发运行。

## Install

Python 依赖由 `uv.lock` 锁定：

```powershell
cd D:\chat\agens-web
uv sync --frozen --extra dev

cd web\frontend-react
npm.cmd ci
```

## Development

后端：

```powershell
cd D:\chat\agens-web
$env:DATABASE_URL = "postgresql+psycopg://agens_test@127.0.0.1:55432/agens_web_test"
$env:AGENS_PG_AUTO_DDL = "1"
$env:SESSION_COOKIE_SECURE = "0"
$env:PYTHONPATH = "D:\chat\agens-web\src"
.\.venv\Scripts\python.exe -m uvicorn web.backend.app:app --host 127.0.0.1 --port 8000 --reload
```

前端：

```powershell
cd D:\chat\agens-web\web\frontend-react
npm.cmd run dev -- --host 127.0.0.1 --port 5173
```

浏览器访问 `http://127.0.0.1:5173/static/`。健康检查为
`http://127.0.0.1:8000/api/health`，数据库不可用时返回 503。

## Validation

```powershell
cd D:\chat\agens-web
$env:TEST_DATABASE_URL = "postgresql+psycopg://agens_test@127.0.0.1:55432/agens_web_test"

.\.venv\Scripts\python.exe -m compileall -q src tests web scripts migrations
.\.venv\Scripts\python.exe -m ruff check src web tests scripts migrations
.\.venv\Scripts\python.exe -m ruff check src web tests scripts migrations --select C901
.\.venv\Scripts\python.exe -m mypy src web\backend
.\.venv\Scripts\python.exe -m pytest -q tests\web -n0
.\.venv\Scripts\python.exe -m pytest -q -m "not llm_real"

cd web\frontend-react
npm.cmd test
npm.cmd run build
npm.cmd audit --audit-level=high
```

真实 LLM 测试标记为 `llm_real`，默认门禁排除；手工执行时仍必须把
`fallback=true` 视为失败。

## Model Settings

- `GET/POST/DELETE /api/settings/model`：当前登录用户个人配置。
- `GET/POST /api/admin/settings/model`：管理员维护系统默认配置。
- `MODEL_CONFIG_SECRET`：加密/解密 PostgreSQL 中的模型 Key；缺失时 fail closed。
- `AGENS_MODEL_BASE_URL_ALLOWLIST`：自定义 OpenAI-compatible HTTPS 主机白名单，逗号分隔；官方域名无需重复配置。
- `AGNES_TOTAL_TIMEOUT_SECONDS`：单次模型调用整体时限。
- 不得把用户 Key 写入 `os.environ`，也不得通过命令行参数传入真实 Key。

## Deployment Shape

- `deploy/docker-compose.yml` 使用一次性 `agens-web-migrate` 服务执行 Alembic。
- 应用副本不执行迁移；镜像使用锁定依赖、非 root 用户和只读根文件系统。
- Compose 默认 drop capabilities、启用 `no-new-privileges`、tmpfs 和 CPU/内存/PID 限制。
- PostgreSQL 只在内部网络可见，不对公网或 LAN 暴露。

本机当前未安装 Docker CLI，因此本批 Docker build 需在具备 Docker 的本地环境补验；这不等于生产验证。

## Artifacts

原 `output/` 已归档到 `D:\chat\agens-web-artifacts\20260710`：723 个文件，
599,683,815 字节。归档目录包含 `MANIFEST.sha256` 和 `INVENTORY.txt`，不属于 Git 提交内容。

## Docs

- [docs/INDEX.md](docs/INDEX.md)：文档入口。
- [docs/RUNTIME_FLOW.md](docs/RUNTIME_FLOW.md)：当前运行链路。
- [docs/GAME_MODE_SPEC.md](docs/GAME_MODE_SPEC.md)：玩法规则 source of truth。
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)：模块与依赖边界。
- [docs/security.md](docs/security.md)：安全边界。
- [docs/PROJECT_AUDIT.md](docs/PROJECT_AUDIT.md)：当前审计结论。
- [docs/NEXT_GOVERNANCE_BACKLOG.md](docs/NEXT_GOVERNANCE_BACKLOG.md)：剩余工作。
- [CHANGELOG.md](CHANGELOG.md)：历史变更和旧验收证据。
