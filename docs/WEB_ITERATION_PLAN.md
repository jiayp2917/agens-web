# Web-only 迭代计划

## 目标

当前 `master` 是 Web-only 版本：保留核心游戏逻辑，提供浏览器 UI、FastAPI 后端、SQLite 数据库和 Web 验证。

## 一句话计划

已移除移动端产品链路；保留 `src/agens_novel/` 的 GameEngine、Agent、LLM、Session、境界和规则；新增 `web/backend` FastAPI 接口、`web/frontend` 浏览器界面、SQLite 数据库、用户登录、会话存档、chat_history 和模型配置管理；验证改为后端 API 测试、核心引擎测试和浏览器端到端测试。

## 阶段

| 阶段 | 内容 | 验收 |
| --- | --- | --- |
| 1 | 建立 `web/backend`，用 FastAPI 包装 `GameEngine`。 | 能创建会话、开局、提交 A/B/C、提交 D 输入、读取状态。 |
| 2 | 建立 `web/frontend`，实现首页、角色创建、游戏页、设置、存读档、死亡/飞升页。 | 浏览器可完成一局最小流程。 |
| 3 | 引入 SQLite，保存用户、会话、存档、chat_history 和模型配置摘要。 | 刷新页面或重启服务后可恢复存档。 |
| 4 | 清理旧文档和测试分类。 | 搜索不到旧移动端产品入口作为当前运行路径。 |
| 5 | 完善测试和部署。 | 后端测试、核心测试、浏览器端到端测试通过。 |

## API 最小集合

- `POST /api/sessions`：创建会话。
- `POST /api/sessions/{id}/start`：角色创建并开局。
- `POST /api/sessions/{id}/choice`：提交 A/B/C。
- `POST /api/sessions/{id}/action`：提交 D 输入。
- `GET /api/sessions/{id}`：读取当前叙事、状态、选项和终局状态。
- `POST /api/sessions/{id}/save`：保存。
- `POST /api/sessions/{id}/load`：读档。
- `POST /api/sessions/{id}/end`：结束当前本局并进入终局页。
- `GET /api/saves`：读取存档摘要。
- `GET /api/settings/model` / `POST /api/settings/model`：读取和保存脱敏模型配置。

## 保留与删除

保留：

- `src/agens_novel/engine/`
- `src/agens_novel/agents/`
- `src/agens_novel/session/`
- `src/agens_novel/persistence/`
- `src/agens_novel/game/`
- `src/agens_novel/llm/`
- `config/prompts/system/`

已删除或替换：

- 移动端源码目录
- 移动端打包配置
- 设备验证文档
- 移动端 UI 契约测试
- 打包命令

## 注意事项

- 移动端项目继续由 `D:\chat\agens` 维护；本目录不再同步移动端改动。
- Web 前端不得保存或显示真实 API key。
- 多用户能力不要绕过 `GameEngine` 和 `GameSession`。
- 若 Web 化需要改核心规则，单独提交并说明是否需要回灌到其他产品线。
