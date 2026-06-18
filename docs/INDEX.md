# 项目文档索引

后续智能体先读本文，再按任务读取对应文档。本目录是 Web-only 项目。

## 必读入口

- `AGENTS.md`：Web 项目硬约束、玩法契约、技术方向和目录边界。
- `docs/WEB_ITERATION_PLAN.md`：Web-only 迭代计划和保留/删除清单。
- `docs/PROJECT_AUDIT.md`：当前结构边界、技术债和瘦身方向。
- `docs/RUNTIME_FLOW.md`：当前核心业务逻辑和代码调用链。

## 按任务读取

| 任务 | 优先阅读 |
| --- | --- |
| Web 化改造 | `docs/WEB_ITERATION_PLAN.md`、`AGENTS.md` |
| 理解项目边界或做架构审核 | `docs/PROJECT_AUDIT.md` |
| 分析游戏运行流程 | `docs/RUNTIME_FLOW.md` |
| 安全与密钥边界 | `docs/security.md`、`AGENTS.md` |
| Agent 提示词或调用链 | `config/prompts/system/*.md`、`src/agens_novel/agents/` |

## 当前执行边界

- 当前仓库是 Web 适配项目。
- 当前产品入口是浏览器 UI + FastAPI 后端。
- 默认模型仍是 Agens；DeepSeek 只是可选测试项。
- API key 只允许由后端读取、保存或脱敏展示，不写入仓库、前端包或日志。
