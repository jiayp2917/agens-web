# agens-novel-web — Web 文字修仙模拟器

## 项目定位

本目录是 `agens` 的 Web-only 项目，路径固定为 `D:\chat\agens -web`，当前 `master` 是浏览器版本主线。本项目不维护移动端打包或设备验证迭代。

核心玩法继续复用 `src/agens_novel/`：

- **Narrator**：生成叙事、状态变化和下一回合 A/B/C 选项。
- **World Builder**：创建角色、世界开局和开场 A/B/C 选项。
- **Judge**：审核状态变化与世界逻辑是否合理。

## 当前玩法契约

- Web 首期只开放引导模式：A/B/C 由模型基于上下文生成，D 为玩家自由键入。
- 小说模式、游戏模式可以在 Web UI 中作为禁用入口保留，但不开放运行逻辑。
- 模型失败、无 key 或无有效选项时，允许用户选择本地故事兜底继续或结束本局。
- 战斗不提供常驻按钮，玩家通过 D 输入框键入攻击、防御、逃跑、施展功法等行动。
- 界面不得明示隐藏触发规则或隐藏模式名称。
- 境界顺序：练气、筑基、金丹、元婴、化神、合体、大乘、渡劫、飞升；不得恢复已删除的旧境界。

## 技术方向

- **Backend**：FastAPI，包装 `GameEngine`，提供会话、开局、回合、存读档、设置和模型调用接口。
- **Frontend**：浏览器 Web UI，首期可用 React/Vite 或等价轻量前端。
- **Database**：SQLite 起步，后续可替换 PostgreSQL；保存用户、会话、存档、chat_history 和模型配置摘要。
- **LLM**：继续使用 OpenAI 兼容调用，密钥只在后端读取、保存或脱敏展示，禁止进入前端代码和日志。
- **Tests**：后端 API 测试、核心引擎测试、浏览器端到端测试。

## 目录边界

| 目录 | Web 项目职责 |
| --- | --- |
| `src/agens_novel/` | 核心游戏逻辑、Agent、LLM、状态、规则和存档能力，优先复用。 |
| `web/backend/` | 新增 Web API、数据库访问、用户/会话服务。 |
| `web/frontend/` | 新增浏览器 UI。 |
| `docs/` | Web 项目文档入口和迁移计划。 |

## 架构约束

- 当前对话和后续 Web 改造只操作 `D:\chat\agens -web`。
- 不在本项目维护移动端打包或设备验证流程。
- 不恢复 `agens-novel` CLI、终端 REPL 或旧高中低自由度模式。
- `GameEngine` 仍是唯一游戏逻辑入口；Web 前端不得直接修改 `GameSession`。
- API key 不写入仓库、前端包、文档、日志或持久化环境变量。
- Web 后端日志只允许记录 provider、model、base_url、是否有 key、耗时和错误类型等脱敏信息。
- 不回退其他产品线的任何内容。

## 常用命令

```powershell
cd "D:\chat\agens -web"

# 当前基线检查
.\.venv\Scripts\python.exe -m compileall -q src tests
.\.venv\Scripts\python.exe -m pytest -q

.\.venv\Scripts\python.exe -m uvicorn web.backend.app:app --host 127.0.0.1 --port 8000 --reload
```

## 文档索引

后续智能体先读 `docs/INDEX.md`。Web 化路线见 `docs/WEB_ITERATION_PLAN.md`，当前结构边界和技术债见 `docs/PROJECT_AUDIT.md`。

## 通用编码准则

### 1. 不确定就问

需求、边界、设计方向或破坏性清理不明确时，先停下来问用户。

### 2. 简洁优先

解决问题的最少代码。首期 Web 先跑通最小闭环，不提前建设复杂平台。

### 3. 精准改动

只触碰 Web 化必须改动的内容。移动端项目已在另一个目录维护，不在这里同步迭代。

### 4. 目标驱动执行

每次改动都要能通过明确验证：后端 API、浏览器 UI、核心引擎测试或文档检查。
