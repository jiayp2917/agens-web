# Security — 外网 Alpha 安全边界

## Hard Rules

1. API key 不写入仓库、日志、运行产物或文档。
2. 运行时只从当前进程环境变量、应用内设置或本地兜底读取。
3. `SecretRedactor` 必须继续屏蔽真实密钥形态。
4. 存档路径必须经过 sanitizer，禁止路径穿越。
5. 数据库连接信息只从 `DATABASE_URL` 读取，真实值只放运行时 env。
6. 公网允许访客新局游玩；云存档、读档、模型设置需要邀请码注册登录。
7. Session 使用 HttpOnly Cookie，前端不得保存 bearer token。访客局额外使用 HttpOnly 访客 Cookie 绑定内存 runner。

## Runtime Env

生产环境必须注入：

```env
DATABASE_URL=postgresql+psycopg://agens_user:CHANGE_ME@postgres:5432/agens_web
SESSION_SECRET=CHANGE_ME
SESSION_COOKIE_SECURE=1
INVITE_ADMIN_CODE=CHANGE_ME
AGENS_ALLOWED_ORIGINS=https://game.jiayp2917.xyz
AGENS_ALLOWED_HOSTS=game.jiayp2917.xyz,agens-web,localhost,127.0.0.1
TRUST_PROXY_HEADERS=0
AGENS_API_KEY=CHANGE_ME
```

`deploy/production.env.example` 只能放占位值，不放真实密码或 key。

## Auth Boundary

- `GET /api/health`、`POST /api/auth/register`、`POST /api/auth/login` 公开。
- 访客可以 `POST /api/sessions` 创建新局、推进回合、结束本局；存读档和模型设置接口对访客返回 401。
- 已登录用户可以访问自己的游戏会话、存档和存档列表。
- 模型设置写入和读取仅管理员可用。
- 普通用户只能访问自己的 session/save。
- `INVITE_ADMIN_CODE` 只用于创建首个管理员；普通邀请码应由管理员通过后端接口创建。
- 生产/PostgreSQL 模式下缺少 `SESSION_SECRET`、`DATABASE_URL` 或 `INVITE_ADMIN_CODE` 会启动失败。
- 生产/PostgreSQL 模式下缺少 `AGENS_ALLOWED_ORIGINS` 会启动失败。
- 生产模式关闭 `/docs`、`/redoc`、`/openapi.json`。
- 生产模式启用 Host 白名单，来源为 `AGENS_ALLOWED_HOSTS` 和 `AGENS_ALLOWED_ORIGINS`。
- Cookie 登录态的状态变更请求需要匹配 `AGENS_ALLOWED_ORIGINS` 或同源 Host。

## Deployment Boundary

- PostgreSQL 不暴露公网或 LAN。
- 应用容器通过内部 Docker network 访问 PG。
- 公网只暴露 Caddy/Cloudflare Tunnel 到 `agens-web:8000`。
- 日志不得输出 `DATABASE_URL`、Cookie、密码、真实 API Key 或请求头原文。
- PostgreSQL schema 由 Alembic 迁移拥有；生产应用启动不执行隐式建表。旧库如已由应用建表，需要先人工 `alembic stamp head` 或做一次性迁移核对。

## Caddy / Cloudflare Tunnel

推荐公网只暴露应用子域名：

```caddy
game.jiayp2917.xyz {
    encode zstd gzip
    request_body {
        max_size 64KB
    }
    header {
        X-Content-Type-Options nosniff
        Referrer-Policy same-origin
        X-Frame-Options DENY
    }
    reverse_proxy agens-web:8000
}
```

如果通过 Cloudflare Tunnel 暴露，Tunnel 入口同样只指向 `http://agens-web:8000`；数据库仍保持内部网络或 SSH 隧道访问。

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
