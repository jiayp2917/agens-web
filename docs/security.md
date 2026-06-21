# Security — 外网 Alpha 安全边界

## Hard Rules

1. API key 不写入仓库、日志、运行产物或文档。
2. 运行时只从当前进程环境变量、应用内设置或本地兜底读取。
3. `SecretRedactor` 必须继续屏蔽真实密钥形态。
4. 存档路径必须经过 sanitizer，禁止路径穿越。
5. 数据库连接信息只从 `DATABASE_URL` 读取，真实值只放运行时 env。
6. 外网访问必须先登录；首版只允许邀请码注册。
7. Session 使用 HttpOnly Cookie，前端不得保存 bearer token。

## Runtime Env

生产环境必须注入：

```env
DATABASE_BACKEND=postgresql
DATABASE_URL=postgresql://agens_user:CHANGE_ME@postgres:5432/agens_web
SESSION_SECRET=CHANGE_ME
SESSION_COOKIE_SECURE=1
INVITE_ADMIN_CODE=CHANGE_ME
AGENS_API_KEY=CHANGE_ME
```

`deploy/production.env.example` 只能放占位值，不放真实密码或 key。

## Auth Boundary

- `GET /api/health`、`POST /api/auth/register`、`POST /api/auth/login` 公开。
- 游戏会话、存档、模型设置接口需要登录。
- 模型设置写入和读取仅管理员可用。
- 普通用户只能访问自己的 session/save。
- `INVITE_ADMIN_CODE` 只用于创建首个管理员；普通邀请码应由管理员通过后端接口创建。

## Deployment Boundary

- PostgreSQL 不暴露公网或 LAN。
- 应用容器通过内部 Docker network 访问 PG。
- 公网只暴露 Caddy/Cloudflare Tunnel 到 `agens-web:8000`。
- 日志不得输出 `DATABASE_URL`、Cookie、密码、真实 API Key 或请求头原文。

## Local Debug Pattern

`scripts/run_with_key.ps1` 只在当前 PowerShell 进程及其子进程中注入环境变量，随后在 `finally` 中清理：

```powershell
.\scripts\run_with_key.ps1 -ApiKey "<your key>"
```

该脚本仅用于本地环境变量注入验证；流程验证以 Web 后端 API 和浏览器 UI 为准。

## Verify

```powershell
$env:AGNES_API_KEY = "<redaction-test-key>"
.\scripts\run_with_key.ps1 -ApiKey $env:AGNES_API_KEY
echo "after script: $env:AGNES_API_KEY"

select-string -Path runtime\logs\*.jsonl,runtime\artifacts\**\*.json -Pattern "<secret-pattern>" -List
.\.venv\Scripts\python.exe -m pytest -q
```
