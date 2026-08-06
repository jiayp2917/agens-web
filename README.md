# agens-web

Web-only 文字修仙模拟器。当前主线由 React/Vite、FastAPI、PostgreSQL 和
`src/agens_novel/` 游戏核心组成。

## Current Status

- 游戏模式 v5 Alpha：A/B/C/D 固定为 A 稳妥、B 机遇、C 风险、D 气运，无自由文本主入口，无 HP/MP 常驻 UI。
- PostgreSQL-only；Alembic 是 schema authority。当前 head 为 `20260721_0009_spirit_root_metadata`。
- 注册用户可保存个人模型配置；无个人配置时使用系统 Agens 默认；访客不可配置模型。
- 模型 Key 只以应用层密文写入 PostgreSQL，API、日志、存档、session snapshot 和前端包都不得出现原文。
- 自定义模型地址只允许 HTTPS 官方域名或 `AGENS_MODEL_BASE_URL_ALLOWLIST` 中的主机；请求前会解析全部 A/AAAA，任何非公网地址均拒绝。
- 访客局持久化到 PostgreSQL，默认保留 24 小时；登录或注册成功后删除当前访客局并清除访客 Cookie。
- start/choice/action/save/load/end 都要求 `request_id` 与 `expected_version`，后端通过会话锁、CAS 和幂等结果防止双击、重试和并发覆盖。
- 回合日志、session snapshot、活跃/终局 run、奖励和遗泽消费使用同一数据库事务；失败恢复内存 runner。
- 模型失败会保留待处理状态；玩家可显式选择重试、转入本地故事或结束本局。任何本地故事处理均不算 live-model 成功。
- 四套世界包保留 60 回合 `story_version=1` 旧档兼容；新局默认使用九阶段 90 回合 `story_version=2`。`story_version=3` 已实现九阶段事件、两条命数承诺、最近五项 motif 去重、路线后果与 90 回合后的 `post_arc`，但尚未完成真实模型和浏览器完整局验收，默认版本不变。
- 普通回合由事件表声明模型可承接的 delta 类型；Web `choice_index` 与引擎 A/B/C/D 输入共用同一语义包装。
- Narrator 缺任一契约段时会记录 `contract_recovery`；即使规则侧能继续结算，也不能计作 live-model 成功。
- FastAPI 路由已拆为 auth/catalog/session/settings；`GameEngine` 仍是玩法门面，开局、普通回合、突破和 fallback 分别由 flow/policy 模块承担。
- 灵根规则和网页 catalog 初始化共用 `game/spirit_roots.py` 注册表；同步只追加缺失名称并补齐缺失 metadata，不覆盖已有 PostgreSQL 记录。前端优先显示权威寿元，仅在字段缺失或非法时回退境界默认值。
- `WebGameService` 保持 API 门面，session、turn、save/load 用例已拆到独立模块；评估能力只通过默认空钩子接入，产品服务不依赖评估实现。
- 前端关键面板使用 SVG 九宫双线内收角与同轮廓背景蒙版；工具按钮、寿元条、细滚动条和 A/B/C/D 六态已按当前素材规范统一，移动端保留同一视觉语言。
- 2026-07-23 当前工作树已通过本地静态、PostgreSQL Web（96 项）、非真实模型 pytest（914 项）、前端测试、生产构建、高危依赖审计和测试库备份恢复；双模型结果和未完成项见审计与 backlog。
- 本轮不检查、修改或声明生产环境状态。生产发布仍需要在独立范围内重新执行部署、数据库、网络隔离和严格 live-model 验收。
当前本地门禁、strict live 证据、性能数据和残余风险统一见
[docs/PROJECT_AUDIT.md](docs/PROJECT_AUDIT.md)。本地通过不等于生产通过。

## Local PostgreSQL

```powershell
cd D:\chat\agens-web
F:\pg\bin\pg_isready.exe -h 127.0.0.1 -p 5432
```

本机开发默认连接 `jiayp2917@127.0.0.1:5432/agens_web`，无需手动设置
`DATABASE_URL`。显式设置该变量可覆盖本机默认值；生产环境仍必须显式配置。
本仓库只使用这一个本机开发/测试数据库。`tests\web`、迁移和备份恢复门禁会清空或重建其 schema；运行测试前不要保留需要持久化的本地会话、存档或模型配置。数据库、pytest 与浏览器流程仍须串行运行。

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
\.\.venv\Scripts\alembic.exe upgrade head
$env:PYTHONPATH = "D:\chat\agens-web\src"
.\.venv\Scripts\python.exe -m uvicorn web.backend.app:app --host 127.0.0.1 --port 8000 --reload
```

前端：

```powershell
cd D:\chat\agens-web\web\frontend-react
npm.cmd run dev -- --host 127.0.0.1 --port 5173
```

浏览器访问 `http://127.0.0.1:5173/`。健康检查为
`http://127.0.0.1:8000/api/health`，数据库不可用时返回 503。

## Validation

```powershell
cd D:\chat\agens-web

.\.venv\Scripts\python.exe -m compileall -q src tests web scripts migrations
.\.venv\Scripts\python.exe -m ruff check src web tests scripts migrations
.\.venv\Scripts\python.exe -m ruff check src web tests scripts migrations --select C901
.\.venv\Scripts\python.exe -m mypy src web\backend
.\.venv\Scripts\python.exe scripts\verify_skill_copies.py
.\.venv\Scripts\python.exe -m pytest -q tests\web -n0
.\.venv\Scripts\python.exe -m pytest -q -m "not llm_real"
$env:PG_BIN = "F:\pg\bin"  # pg_dump/pg_restore 不在 PATH 时设置
.\.venv\Scripts\python.exe scripts\verify_pg_backup_restore.py

cd web\frontend-react
npm.cmd test
npm.cmd run build
npm.cmd audit --audit-level=high
```

真实 LLM 测试标记为 `llm_real`，默认门禁排除；手工执行时必须同时要求
Narrator `ok`、`fallback=false`、`fallback_prompt.active=false`、`contract_recovery=false` 和契约完整。

## Model Settings

- `GET/POST/DELETE /api/settings/model`：当前登录用户个人配置。
- `GET/POST /api/admin/settings/model`：管理员维护系统默认配置。
- `MODEL_CONFIG_SECRET`：用于加密/解密 PostgreSQL 中已存的模型 Key。本机运行时系统环境 Key 是直接来源；旧密文无法解密且环境 Key 缺失时，调用会返回脱敏配置错误。
- `AGENS_MODEL_BASE_URL_ALLOWLIST`：自定义 OpenAI-compatible HTTPS 主机白名单，逗号分隔；官方域名无需重复配置。
- `AGNES_TOTAL_TIMEOUT_SECONDS`：单次模型调用整体时限。
- 不得把用户 Key 写入 `os.environ`，也不得通过命令行参数传入真实 Key。

## Local Model Verification

本地开发、测试和浏览器验证都启动普通 `web.backend.app`，由 `ModelConfigService` 解析当前
PostgreSQL 系统模型配置。数据库未配置时，`AGENS_SYSTEM_MODEL_*` 或兼容的 `AGNES_*` 才作为启动
回退；Key 只在单次模型调用边界读取或解密。不存在独立的评估应用、模型解析器、预算账本或专用环境变量。

新请求显式使用 `response_mode`，默认 `json_object`；解析不按厂商、模型名或地址分支。浏览器工具通过
公开 API 运行，并把临时脱敏汇总写入系统临时目录，或写入 `AGENS_PLAYTEST_OUTPUT_DIR` 指定的仓库外目录。
不得保存 prompt、原始响应、Key、Cookie、Authorization、真实 Base URL 或玩家数据。默认 pytest 门禁
不会调用真实模型；真实模型资格结论和后续门禁见 `docs/PROJECT_AUDIT.md` 与
`docs/NEXT_GOVERNANCE_BACKLOG.md`。

## Deployment Shape

- `deploy/docker-compose.yml` 使用一次性 `agens-web-migrate` 服务执行 Alembic。
- 应用副本不执行迁移；镜像使用锁定依赖、非 root 用户和只读根文件系统。
- Compose 默认 drop capabilities、启用 `no-new-privileges`、tmpfs 和 CPU/内存/PID 限制。
- PostgreSQL、Redis 和 Squid 仅在内部网络可见，不对公网或 LAN 暴露。
- 生产限流使用 Redis 原子滑动窗口；Redis 不可用时敏感写请求返回 503，不降级为各实例独立计数。
- 模型请求只通过显式 Squid HTTPS CONNECT 代理访问允许域名，`DOCKER-USER` 专用链阻止应用绕过代理直连公网或私网。
- 主机 ACL 必须先完整写入并置于 `DOCKER-USER` 首位，再开启 bridge filtering；不得在运行 Docker 容器的主机上执行 `modprobe -r br_netfilter`。

## Artifacts

原 `output/` 已归档到 `D:\chat\agens-web-artifacts\20260710`：723 个文件，
599,683,815 字节。归档目录包含 `MANIFEST.sha256` 和 `INVENTORY.txt`，不属于 Git 提交内容。

## Docs

- [docs/INDEX.md](docs/INDEX.md)：文档入口。
- [docs/plan.md](docs/plan.md)：长期目标、稳定边界、里程碑状态和验收原则。
- [docs/RUNTIME_FLOW.md](docs/RUNTIME_FLOW.md)：当前运行链路。
- [docs/GAME_MODE_SPEC.md](docs/GAME_MODE_SPEC.md)：玩法规则 source of truth。
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)：模块与依赖边界。
- [docs/security.md](docs/security.md)：安全边界。
- [docs/PROJECT_AUDIT.md](docs/PROJECT_AUDIT.md)：当前审计结论。
- [docs/NEXT_GOVERNANCE_BACKLOG.md](docs/NEXT_GOVERNANCE_BACKLOG.md)：剩余工作。
- [CHANGELOG.md](CHANGELOG.md)：历史变更和旧验收证据。
