# Next Governance Backlog

本文件只列当前未完成项。历史执行记录在 `CHANGELOG.md`，不在 backlog 重复保留。

## P0

当前本地代码审计没有未处理的 P0。若生产允许用户自定义模型域名但未部署出站 ACL，DNS rebinding 残余风险应在发布前重新评估为 P0/P1。

## P1 Local Acceptance

1. **Docker gate**
   - 在具备 Docker 的本地环境运行：
   - `docker compose --env-file deploy/production.env -f deploy/docker-compose.yml config`
   - `docker build -t agens-web:local .`
   - 启动 migration + app，确认非 root、read-only 和健康检查正常。

2. **Extended real Chrome gate**
   - 2026-07-10 isolated fallback smoke 已覆盖访客清局、角色创建、双击、fallback、存读档、终局和 375/2K overflow。
   - 2026-07-11 素材细节验收已覆盖 1440x900、1920x1080、2560x1440、390x844、桌面/移动弹窗和六态组件；相关截图不提交仓库。
   - 后续只需补真实 provider 20 回合、显式 409 可见提示、内容质量和终局长局证据。
   - 不与 pytest 共用数据库。

3. **Live-model gate**
   - 使用手工 `llm_real` 或真实 Chrome，记录 start/choice 是否 non-fallback。
   - 记录 408/429/5xx 重试和整体时限行为。
   - 不输出 Key、URL 真值、账号、Cookie、邀请码或原始模型响应。

4. **DNS egress defense**
   - 在部署层增加禁止 loopback/private/link-local/metadata 的出站策略。
   - 应用 allowlist 不能单独消除 DNS rebinding TOCTOU。

## P1 Production Follow-up

生产任务单独执行，不属于本地代码批次：

1. 备份应用和 PostgreSQL。
2. 只读检查无法关联的历史 `game_turns`。
3. 确认 `MODEL_CONFIG_SECRET`、URL allowlist、总时限和访客 TTL 已配置，但不输出值。
4. 运行一次性 migration service 升级到 `20260710_0008`。
5. 验证 health、注册/登录、访客清局、start、choice、save/load、终局和奖励幂等。
6. live-model start + 至少一次 choice 必须 non-fallback。

## P2 Maintainability

1. 拆 `database_postgres.py`：优先抽 session mutation、catalog 和 rewards repository，保持 `WebDatabaseProtocol` 不变。
2. 拆 `tests/web/test_web_api.py`：按 auth、model settings、session、save/load、turn persistence 分类。
3. 评估把应用内 RateLimiter 换成 Redis/反代限流；Alpha 单实例仍可保留现实现。
4. 为模型 URL 校验增加可插拔的固定解析/连接层，进一步消除 DNS rebinding 窗口。
5. 扩展前端测试到完整账号流程和 409 可见提示；当前已有认证回调、fallback、双击、focus trap、选择按钮 loading 和游戏工具栏覆盖。

## Stable Invariants

- A/B/C/D 语义由后端槽位决定，D 永远是气运。
- 访客不能设置模型或云存档。
- 登录/注册后删除访客局，不迁移。
- 用户模型 Key 不写进环境变量、日志、响应、存档或回合记录。
- fallback 不算 live-model 成功。
- PostgreSQL schema 由 Alembic 拥有。
- 真实浏览器验收不能与 `tests\web` 共用数据库并发运行。
- 仓库不再保存 `output/`；生成证据写入外部 artifact 目录。
