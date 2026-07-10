# Security - 公网 Alpha 边界

## Hard Rules

1. 不读取、打印、记录或提交真实 API Key、Cookie、密码、邀请码、Session Secret 或数据库 URL。
2. 前端不保存 bearer token；账号与访客身份都使用 HttpOnly Cookie。
3. PostgreSQL 不保存明文模型 Key；API、日志、错误、存档和回合记录不返回 Key。
4. 所有会改变 session 的请求都需要所有权校验、`request_id` 和 `expected_version`。
5. 模型输出是非可信输入；规则字段由规则引擎拥有。
6. 用户可控模型 URL 必须经过 SSRF 防护。
7. 生产 schema 只由 Alembic 修改，应用副本不自动迁移或建表。

## Required Production Env

```env
AGENS_ENV=production
DATABASE_URL=postgresql+psycopg://USER:CHANGE_ME@postgres:5432/agens_web
SESSION_SECRET=CHANGE_ME
SESSION_COOKIE_SECURE=1
INVITE_ADMIN_CODE=CHANGE_ME
MODEL_CONFIG_SECRET=CHANGE_ME_WITH_AT_LEAST_32_RANDOM_CHARACTERS
AGENS_ALLOWED_ORIGINS=https://game.example.com
AGENS_ALLOWED_HOSTS=game.example.com,agens-web,localhost,127.0.0.1
AGENS_MODEL_BASE_URL_ALLOWLIST=
AGNES_TOTAL_TIMEOUT_SECONDS=90
AGENS_GUEST_SESSION_TTL_SECONDS=86400
AGENS_MAX_REQUEST_BYTES=65536
TRUST_PROXY_HEADERS=0
```

`deploy/production.env.example` 只允许占位值。`AGENS_ENV=prod` 与
`AGENS_ENV=production` 均触发生产保护。

## Authentication And Sessions

- 注册使用邀请码；邀请码消费和用户创建在同一事务。
- 首管理员创建使用 PostgreSQL advisory transaction lock。
- 登录用户只能访问自己的 session、save 和个人模型配置。
- 访客可创建、推进和结束访客局，但不能存读档或设置模型。
- 访客 Cookie 原文不入库；数据库只保存 token hash 和过期时间。
- 访客局默认 24 小时过期，可跨进程恢复。
- 登录/注册成功立即删除当前访客局并清除访客 Cookie，不迁移到账号。
- 登录 Cookie 和访客 Cookie 均为 HttpOnly；生产必须启用 Secure 和 SameSite。

## Mutation Consistency

start/choice/action/save/load/end 请求必须包含：

```json
{
  "request_id": "UUID or other unique client id",
  "expected_version": 0
}
```

- 相同 request ID 返回首次成功结果。
- 过期 version 返回 409。
- 每 session 使用服务端锁和数据库 CAS。
- 回合、snapshot、终局、奖励、进度、遗泽和 save slot 原子提交。
- 事务失败恢复内存 runner，不吞持久化错误。

## Model Key Storage

- `/api/settings/model` 只管理当前用户个人配置。
- `/api/admin/settings/model` 只管理系统默认配置。
- `model_config` 和 `user_model_configs` 的 Key 使用 Fernet 加密，密钥材料由 `MODEL_CONFIG_SECRET` 经 SHA-256 派生。
- 数据库保存 encrypted token、masked metadata 和 `api_key_set`，不保存 raw Key。
- 缺少 secret、token 无效或完整性校验失败时 fail closed。
- 用户 Key 显式传给当前 runner 的模型调用，禁止写入 `os.environ`。
- `AGNES_API_KEY` 只保留开发/迁移兼容用途，不是正式用户配置主路径。

## Model URL SSRF Defense

保存配置和每次模型请求共用 `src/agens_novel/llm/url_security.py`：

- 只允许 HTTPS。
- 拒绝 URL 用户信息、query、fragment 和 IP 字面量。
- 官方 Agens、DeepSeek、Qwen/DashScope、GLM 域名内置允许。
- 自定义 hostname 必须在 `AGENS_MODEL_BASE_URL_ALLOWLIST`；可按 `host:port` 精确允许非 443 HTTPS 端口。
- 请求前解析全部 A/AAAA；任一地址不是 global unicast 即拒绝，包括 loopback、private、link-local、reserved、multicast 和云 metadata 地址。
- HTTPX 设置 `trust_env=False` 和 `follow_redirects=False`，不继承本机代理，也不跟随重定向。
- 当前 DNS 校验与连接仍是两个步骤，理论上存在 DNS rebinding TOCTOU 残余风险；公网高风险场景应增加出站网络 ACL 或固定解析连接层。

## Request Boundary

- body 默认上限 64 KiB，同时覆盖 Content-Length 和 chunked body。
- 状态变更请求校验 Origin/Referer。
- 生产启用 TrustedHost，关闭 `/docs`、`/redoc`、`/openapi.json`。
- 认证和回合接口有应用内限流；长期公网可迁到反代/Redis，但应用内保护不能视为分布式限流。
- `/api/health` ping PostgreSQL，数据库不可用返回 503。

## Deployment Boundary

- PostgreSQL 不暴露公网或 LAN。
- Compose 使用一次性 migration service；应用副本不执行 Alembic。
- 最终镜像非 root、只读根文件系统、drop all capabilities、`no-new-privileges`、tmpfs 和资源限制。
- 公网只暴露反代/Tunnel 到应用端口。
- 真实生产部署、迁移、备份恢复和 live-model 验收不属于本地代码验证。

## Local Key Pattern

已删除 `scripts/run_with_key.ps1`，因为 `-ApiKey ...` 形式会进入 PowerShell 命令历史。仅在当前 PowerShell 进程中设置环境变量，且不要把值写进脚本、文档或命令记录：

```powershell
$env:AGNES_API_KEY = Read-Host "Temporary development API key"
# run the local process in the same shell
Remove-Item Env:AGNES_API_KEY
```

正式用户配置应通过登录后的模型设置 API 保存为数据库密文。

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\unit\llm\test_url_security.py
$env:TEST_DATABASE_URL = "postgresql+psycopg://agens_test@127.0.0.1:55432/agens_web_test"
.\.venv\Scripts\python.exe -m pytest -q tests\web -n0
.\.venv\Scripts\python.exe -m ruff check src web tests scripts migrations
.\.venv\Scripts\python.exe -m mypy src web\backend
cd web\frontend-react
npm.cmd audit --audit-level=high
```

测试通过不等于生产安全验收；生产还需要外部网络策略、反代限制、备份恢复和脱敏日志复核。
