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

# agens-novel-web — Web 开发说明

## 当前产品通路

本项目只保留浏览器 UI + FastAPI 后端产品入口。不要恢复终端交互入口、CLI 命令、旧 REPL UI 或移动端打包流程。

流程验证以 Web 后端 API、核心引擎测试和浏览器 UI 为准。

测试：

```powershell
.\.venv\Scripts\python.exe -m compileall -q src tests web
.\.venv\Scripts\python.exe -m pytest -q
```

## 架构边界

- Web UI 只通过 `web/backend` API 调用游戏逻辑。
- `GameEngine` 是唯一游戏逻辑入口。
- `GameSession` 位于 `src/agens_novel/session/game_session.py`。
- Web 会话和存档由 `web/backend/database.py` 写入 PostgreSQL。
- Agent 调用器位于 `src/agens_novel/engine/turn_runner.py`。

## 入口说明

本地开发入口：

```powershell
.\.venv\Scripts\python.exe -m uvicorn web.backend.app:app --host 127.0.0.1 --port 8000 --reload
```

## UI 契约

- A/B/C/D 四按钮固定语义：A 稳妥 / B 机遇 / C 风险 / D 气运；无自由文本输入。
- 首页、角色创建、游戏页、设置、教程、存读档、死亡/飞升页是 Web 首期页面。
- 游戏模式为当前主要开放模式；引导模式、小说模式只作为禁用入口保留。
- 飞升页必须显示“飞升”，不得复用死亡标题。
- 无 HP/MP；战斗、禁地、天劫、心魔以事件判定表达。

## 禁止项

- 不把 API key 写入代码、文档、日志或持久化环境变量。
- 不在 UI 明示隐藏触发规则或隐藏模式名称。
- 不恢复已删除境界。
- 不回退用户已有工作区改动。

## Governance Constraints

Follow `AGENTS.md` Governance Constraints before refactor, feature, cleanup, deployment, or documentation work.

Do not add custom layers before checking whether existing FastAPI, SQLAlchemy/Alembic, React, Python, or project-local helpers can solve the problem with less code. Keep current facts, historical notes, future plans, and TODOs separated.

## 2026-06-28 Model Settings Boundary

- Ordinary registered users configure personal model settings through `/api/settings/model`; guests receive 401.
- Users with no personal config use the system default Agens config. Admins manage that default through `/api/admin/settings/model`.
- `MODEL_CONFIG_SECRET` is required for encrypted stored keys in production. Never write raw model API keys to docs, logs, frontend code, saves, snapshots, or database plaintext columns.
