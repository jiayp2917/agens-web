## 通用编码准则

**权衡：** 这些准则偏向谨慎而非速度。对于简单任务，请使用判断力。

### 1. 第一规则：不确定就问

**不要假设。不要隐藏困惑。需求、边界、设计方向或预期结果不明确时，先停下来问用户。**

实现前：
- 明确陈述你的假设。不确定时提问。
- 存在多种解释时，提出它们，不要默默选择。
- 存在更简单方案时说出来。有理由时要反驳。
- 有不清楚的地方停下来，指出困惑点并提问。
- 这条规则优先于执行速度，尤其适用于 UI 方向、真实作品写回、破坏性清理、大范围重构、Git 提交/推送、API key 处理、模型供应商调整，以及任何可能让用户不清楚“到底改了什么”的操作。

### 2. 简洁优先

**解决问题的最少代码。不要投机。**

- 不添加超出需求的功能。
- 不为单用途代码创建抽象。
- 不添加未请求的"灵活性"或"可配置性"。
- 不为不可能的场景添加错误处理。
- 如果200行能写成50行，就重写。

自问："高级工程师会说这太复杂吗？"如果是，简化。

### 3. 精准改动

**只触碰必须改动的。只清理自己的烂摊子。**

编辑现有代码时：
- 不要"改进"相邻代码、注释或格式。
- 不要重构没坏的东西。
- 匹配现有风格，即使你会用不同方式。
- 注意到无关的死代码时，提出它，不要删除。

当改动产生孤立代码时：
- 移除你的改动导致未使用的 import/变量/函数。
- 不要删除预先存在的死代码，除非被要求。

验证标准：每一行改动都可追溯到用户请求。

### 4. 目标驱动执行

**定义成功标准，循环验证直到完成。**

将任务转化为可验证的目标：
- "添加验证" → "为无效输入写测试，然后让测试通过"
- "修复 bug" → "写一个复现 bug 的测试，然后让测试通过"
- "重构 X" → "确保重构前后测试都通过"

对于多步骤任务，陈述简要计划：
```
1. [步骤] → 验证: [检查]
2. [步骤] → 验证: [检查]
3. [步骤] → 验证: [检查]
```

强成功标准让你能独立循环。弱标准（"让它工作"）需要持续澄清。
# agens-novel-web — Web 文字修仙模拟器

## 项目定位

本仓库是 `agens` 的 Web-only 项目，当前 `master` 是浏览器版本主线。本项目不维护移动端打包或设备验证迭代。

核心玩法继续复用 `src/agens_novel/`：

- **Narrator**：生成叙事、状态变化和下一回合 A/B/C/D 选项建议；规则引擎会补齐固定 D 气运语义。
- **World Builder**：创建角色、世界开局和开场 A/B/C/D 选项建议；规则引擎会补齐固定 D 气运语义。
- **Judge**：审核状态变化与世界逻辑是否合理。

## 当前玩法契约

- Web 首期只开放游戏模式：A/B/C/D 四按钮固定语义（A 稳妥 / B 机遇 / C 风险 / D 气运），无自由文本输入。
- 引导模式、小说模式可以在 Web UI 中作为禁用入口保留，但不开放运行逻辑。
- 模型失败、无 key 或无有效选项时，允许用户选择本地故事兜底继续或结束本局。
- 战斗不提供常驻按钮，无 HP/MP；斗法、禁地、天劫、心魔以事件判定和概率结算表达。
- 界面不得明示隐藏触发规则或隐藏模式名称。
- 境界顺序：练气、筑基、金丹、元婴、化神、合体、大乘、渡劫、飞升；不得恢复已删除的旧境界。

## 技术方向

- **Backend**：FastAPI，包装 `GameEngine`，提供会话、开局、回合、存读档、设置和模型调用接口。
- **Frontend**：浏览器 Web UI，首期可用 React/Vite 或等价轻量前端。
- **Database**：PostgreSQL（本地与生产统一）；保存用户、会话、存档、chat_history 和模型配置摘要。
- **LLM**：继续使用 OpenAI 兼容调用，密钥只在后端读取、保存或脱敏展示，禁止进入前端代码和日志。
- **Tests**：后端 API 测试、核心引擎测试、浏览器端到端测试。

## 目录边界

| 目录 | Web 项目职责 |
| --- | --- |
| `src/agens_novel/` | 核心游戏逻辑、Agent、LLM、状态、规则和存档能力，优先复用。 |
| `web/backend/` | 新增 Web API、数据库访问、用户/会话服务。 |
| `web/frontend-react/` | React/Vite 浏览器 UI 和静态资产。 |
| `docs/` | Web 项目文档入口和迁移计划。 |

## 架构约束

- 当前对话和后续 Web 改造只操作本仓库。
- 不在本项目维护移动端打包或设备验证流程。
- 不恢复 `agens-novel` CLI、终端 REPL 或旧高中低自由度模式。
- `GameEngine` 仍是唯一游戏逻辑入口；Web 前端不得直接修改 `GameSession`。
- API key 不写入仓库、前端包、文档、日志或持久化环境变量。
- Web 后端日志只允许记录 provider、model、base_url、是否有 key、耗时和错误类型等脱敏信息。
- 不回退其他产品线的任何内容。

## Governance Constraints

Before adding new logic, check whether existing framework, language, or project-local features can solve the problem with less code.

Known recurring risks:
- Architecture complexity: avoid growing large files, multi-responsibility classes, and after-the-fact abstractions. Prefer one small boundary per change.
- Documentation drift: keep current facts, historical notes, future plans, and TODOs separated. Do not mix outdated plans with verified runtime facts.
- AI over-implementation: do not add another layer of custom logic before asking whether old logic can be deleted, simplified, or replaced by existing framework/library features.

Default priority:
1. Reduce code complexity.
2. Keep public/runtime behavior stable.
3. Clean directories only with inventory, backup, and quarantine.
4. Add features only after boundaries are clear.

For deeper guidance, read:
- `D:\chat\ai-governance\reviews\MAINTENANCE_STRATEGY.md`
- `D:\chat\ai-governance\reviews\CODE_QUALITY_REVIEW_GUIDE.md`
- `D:\chat\ai-governance\prompts\CODEX_WORKFLOWS.md`

## 常用命令

```powershell
cd <repo>

# 当前基线检查
.\.venv\Scripts\python.exe -m compileall -q src tests
.\.venv\Scripts\python.exe -m pytest -q

.\.venv\Scripts\python.exe -m uvicorn web.backend.app:app --host 127.0.0.1 --port 8000 --reload
```

## 文档索引

后续智能体先读 `docs/INDEX.md`。当前运行链路见 `docs/RUNTIME_FLOW.md`，结构边界和技术债见 `docs/PROJECT_AUDIT.md`，下一批治理工作见 `docs/NEXT_GOVERNANCE_BACKLOG.md`。历史计划只看 `docs/archive/`。

## 通用编码准则

### 1. 不确定就问

需求、边界、设计方向或破坏性清理不明确时，先停下来问用户。

### 2. 简洁优先

解决问题的最少代码。首期 Web 先跑通最小闭环，不提前建设复杂平台。

### 3. 精准改动

只触碰 Web 化必须改动的内容。移动端项目已在另一个目录维护，不在这里同步迭代。

### 4. 目标驱动执行

每次改动都要能通过明确验证：后端 API、浏览器 UI、核心引擎测试或文档检查。

## 2026-06-28 Model Settings Boundary

- `/api/settings/model` is a logged-in user endpoint, not an admin/global endpoint. Each registered user owns one personal model config and may clear it to use the system Agens default.
- `/api/admin/settings/model` is the admin-only system-default endpoint. Do not mix it with user settings.
- Stored API keys must be encrypted with `MODEL_CONFIG_SECRET`; PostgreSQL must not store raw keys, and responses/logs must only expose `api_key_set` and masked state.
- Model calls must receive the resolved per-session config explicitly. Do not inject user keys into `os.environ`.
