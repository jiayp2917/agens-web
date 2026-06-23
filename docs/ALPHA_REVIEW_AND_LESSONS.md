# Alpha Review And Lessons

记录日期：2026-06-21

本文记录本轮对“可给他人受控游玩”的问题确认、已修内容、成功/失败经验和后续执行规则。本文不包含真实 API Key、数据库密码、Session Secret、邀请码或生产连接串。

## 当前结论

- 2026-06-22 状态：v5 已实现 / 阶段 7/8 联调收尾中。
  - React 主入口已切到游戏模式 v5，A/B/C/D 四按钮固定语义，D 为气运/天命路线，不再是自由输入。
  - 旧纯 HTML/CSS/JS 前端 `web/frontend` 已删除，图片和 BGM 资产迁入 `web/frontend-react/public/assets`。
  - 新增 Alembic `20260622_0003` 覆盖 `game_runs`、`game_turns`、`player_progress`，以及 `20260622_0004_ddl_disallow_production` 标记 PG 生产库 DDL 治理策略；服务层已写入回合日志和终局进度。
- 本地 SQLite + React 主入口已经具备最小游玩闭环。
- 访客可以直接新开一局并游玩，但不提供云端存档；邀请码账号可以保存和读档。
- 项目还不能直接宣称“公网稳定可玩”，因为服务器生产库 `20260622_0003`、公网部署包和真实浏览器多宽度验收仍需逐项确认。

## 验证证据

- `.\.venv\Scripts\python.exe -m compileall -q src tests web scripts migrations`：通过。
- 2026-06-22 本地复核：`.\.venv\Scripts\python.exe -m pytest -q tests\web`：`37 passed, 1 skipped`。
- 2026-06-22 本地复核：`.\.venv\Scripts\python.exe -m pytest -q`：`548 passed, 1 skipped`。
- `cd D:\chat\agens-web\web\frontend-react; npm run build`：通过。
- 唯一跳过项：`TEST_DATABASE_URL` 未配置，PostgreSQL smoke 未跑。
- 本机未发现 `docker` 命令，Docker Compose 构建和容器启动未验证。

## 问题确认

1. 外网恶意风险判断正确。
   - 恶意注入：主要风险在用户输入进入模型上下文、日志、前端渲染和数据库持久化。当前 React 默认 JSX 转义，后端对模型失败事件做脱敏，但还需要更系统的输入长度、提示词滥用和内容审计策略。
   - 恶意攻击：主要风险是登录/注册爆破、回合接口刷请求、超大 body、CSRF、伪造代理 IP、公开数据库端口。当前已有基础限流、Origin 校验、body limit、生产 secret fail-fast；仍需要边缘层限流、WAF/Cloudflare 策略和真实部署验证。
   - 其他滥用：包括匿名用户消耗模型额度、多人共享同一局 ID、日志泄密、公开 OpenAPI 文档、资源文件流量消耗。访客局本轮改为内存态并绑定 HttpOnly 访客 cookie，降低了未登录持久化滥用。

2. PostgreSQL 架构问题判断部分正确。
   - 当前 PostgreSQL 路线已经有 `DATABASE_URL`、SQLAlchemy/Alembic 方向和生产 env 样例，但真正的生产库迁移、索引、备份、慢查询、连接池和 JSONB 查询策略尚未完成实测。
   - 当前最小表结构能支撑 Alpha，但不等于最终合理架构。后续应补 schema 评审、迁移演练和数据保留策略。

3. UI 改造不完全判断正确。
   - 之前 React 页面过素，截图中登录页缺返回、角色页缺返回和模式说明、游戏页兜底提示过重、终局页右侧大片空白。
   - 本轮已把现有水墨素材用于首页、角色页、游戏页、终局页，并增加登录返回、模式区、访客提示、终局记录区。

4. 新游戏、设置、读档强制登录判断正确。
   - 本轮已改为：新游戏可访客直接游玩；读档/设置打开弹窗，不强制跳登录。
   - 存档、读档、模型管理仍要求登录/管理员，这是公网合理边界。

5. 登录游玩方式已落地。
   - 访客新局：可直接游玩，不提供云端存档；后端不写入用户、会话或存档表。
   - 邀请码注册游玩：登录后可保存/读档，服务端按用户隔离。

6. BGM 功能已恢复。
   - BGM 文件放在 `web/frontend-react/public/assets/audio/bgm.flac`。
   - React 顶栏常驻小喇叭按钮，用户点击后播放/暂停。浏览器禁止无手势自动播放是预期限制。

7. 品牌已改为 `jiayp2917`。
   - 顶栏品牌文字改为 `jiayp2917`。
   - 点击打开 `https://www.jiayp2917.xyz/`，使用 `target="_blank"` 和 `rel="noreferrer"`。

## 本轮已修

- 后端新增访客会话契约：未登录 `POST /api/sessions` 创建访客局并设置 HttpOnly 访客 cookie。
- 访客局只保留在进程内存中，不调用数据库保存 session。
- 访客 start/choice/action/end 需要匹配访客 cookie，不能只靠 session id 操作。
- 访客 save/load/list saves 返回未授权或权限错误。
- React 新游戏不再要求登录。
- React 读档/设置不再强制登录，弹窗内显示访客不能云存档的明确状态。
- React 登录页增加返回首页。
- React 角色页增加返回首页和模式区。
- React 顶栏品牌改为 `jiayp2917` 外链。
- React 顶栏增加 BGM 小喇叭。
- UI 重新接入现有水墨素材，改善首页、角色页、游戏页和终局页视觉完成度。
- 文档更新访客局/账号局运行流程。
- PostgreSQL Alembic 初始迁移补齐运行时会访问的 catalog 和死亡奖励相关表。
- 生产模式增加配置 fail-fast：默认 `SESSION_SECRET`、缺少 `DATABASE_URL`、缺少 `INVITE_ADMIN_CODE`、缺少 `AGENS_ALLOWED_ORIGINS` 都不能启动。
- 生产模式隐藏 `/docs`、`/redoc`、`/openapi.json`，并启用 Host 白名单。
- A/B/C、D 输入和兜底按钮增加 busy guard，降低重复提交风险。
- React 主入口改为 A/B/C/D 固定语义，D 为气运/天命路线。
- 旧 `web/frontend` 已删除，后端不再提供 legacy fallback。
- v5 回合日志表和进度表已加入 Alembic `20260622_0003`，服务层写入 `game_turns` 和 `game_runs`。

## 成功经验

- 先把“可玩”和“可存档”拆开，避免为了存档能力强制所有玩家登录。
- 访客局不落库，比创建 `local` 公共用户更适合公网 Alpha。
- 访客 cookie 绑定内存 runner，比单纯 session id 更稳妥。
- UI 修复优先处理阻塞体验：返回路径、按钮有响应、弹窗状态明确、移动端不横向滚动。
- BGM 用用户点击触发，符合浏览器自动播放限制。
- 先补 P0 安全闸门，再谈公网部署，可以避免“能打开但不该开放”的状态误判。
- Alembic 作为生产 schema authority，比应用启动时隐式建表更可审计。
- 把当前实现和未来规格分开写文档，减少“文档说已经有，代码还没切”的误判。
- 对模型失败统一做本地故事兜底，比把供应商错误直接暴露给玩家更稳。
- 用契约测试锁定按钮、BGM、品牌跳转和访客提示，适合当前还没有完整浏览器 e2e 的阶段。

## 失败经验

- 早期把所有会话都绑到登录态，导致“新游戏”被认证流程阻塞。
- 早期保留 `local` 用户思路，不适合公网，因为匿名访问会产生持久化公共数据。
- 原型图和素材没有进入实现，只停留在计划和输出目录，造成实际 UI 与设计目标脱节。
- React 单文件仍然偏大，继续迭代时维护成本会上升。
- PostgreSQL 仍缺少真实空库迁移、导入、备份恢复和部署连通性验证，不能把“设计完成”当成“上线完成”。
- 早期把 SQLite 本地测试通过等同于数据库路线完成，遗漏了 PostgreSQL/Alembic 生产 schema 覆盖问题。
- 读档、设置、教程等按钮曾经存在“入口可见但行为不完整”的情况，后续 UI 新入口必须同步补交互和测试。
- 安全设计曾经分散在计划里，落地前缺少启动 fail-fast、Host、Origin、body limit 等可执行门槛。
- 文档一度混合当前 Alpha 和未来游戏模式 v5，容易让后续智能体误把草案当实现。
- 删除旧前端前必须先迁移 `/assets`，否则 React 构建产物中引用的图片和 BGM 会在运行时 404。

## 剩余风险

- 访客局只在单进程内存中，多 worker 或容器重启会丢失；Alpha 可接受，正式多人部署需要共享会话存储或明确提示。
- 匿名玩家仍可能消耗模型额度；应在公网前增加访客回合限额、IP/设备限额和模型预算保护。
- PostgreSQL schema 还需要确认服务器生产库已升级到 `20260622_0003`，并继续评审索引、JSONB 字段边界、迁移回滚和备份恢复。
- 安全头、Host 校验、OpenAPI 生产暴露、边缘 body limit、访问日志脱敏还需要在 Caddy/Cloudflare 配置中实测。
- 当前 UI 是一轮修复，不是完整设计系统；后续应拆组件并用浏览器截图做 375/768/1440 验收。

## 后续执行规则

- 任何公网开放前，必须先跑通 PostgreSQL smoke，并确认空库 `alembic upgrade head` 后能注册、登录、开局、A/B/C/D、保存、读档、结束、写入 `game_turns` 和查询 catalog。
- 任何部署报告必须区分本地测试、容器测试、反代测试和公网测试，不能用其中一个替代全部。
- 任何新增首页按钮、弹窗入口或游戏操作，都必须同时补前端契约测试或浏览器验收记录。
- 任何数据库字段、索引或表结构变化，都必须先进 Alembic migration，再考虑 SQLite 测试兼容。
- 任何模型、数据库、Session、Cookie、邀请码相关配置，都只能写占位值或环境变量名，不写真实值。
- React 继续迭代前，应先拆分 `web/frontend-react/src/main.tsx`，至少拆出认证、首页、角色创建、游戏页、设置/存档弹窗、BGM 和终局页。
