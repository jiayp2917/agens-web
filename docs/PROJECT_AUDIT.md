# 项目结构审核与收束

本文是 Web-only 项目的结构边界、瘦身清单和技术债队列。本目录只做浏览器版本。

## 当前边界

- 产品入口是浏览器 Web UI + FastAPI 后端。
- 当前核心游戏逻辑继续复用 `src/agens_novel/`。
- 当前只开放引导模式：A/B/C 为模型基于上下文生成的选项，D 为玩家键入。
- 小说模式、游戏模式只作为后续接口方向，首期在 UI 中禁用。
- 模型失败、无 key、无有效选项时，用户可选择本地故事兜底继续或结束本局。
- 境界顺序固定为：练气、筑基、金丹、元婴、化神、合体、大乘、渡劫、飞升。

## 目标架构

| 层级 | 边界 | 主要目录 |
| --- | --- | --- |
| Web 交互层 | 浏览器展示、点击、输入、设置、存读档入口，不直接改游戏状态。 | `web/frontend/` |
| API 层 | 会话、开局、回合、存读档、设置、认证和脱敏日志。 | `web/backend/` |
| 游戏核心层 | Agent 调用、规则校验、状态落账、境界、战斗、本地故事兜底。 | `src/agens_novel/` |
| 数据层 | 用户、会话、存档、chat_history、模型配置摘要。 | SQLite 起步，后续可迁移 PostgreSQL |

## Agent 职责

- World Builder：只负责角色创建后的世界开局、开场叙事和开场 A/B/C。
- Narrator：只负责每回合叙事、结构化状态建议和下一轮 A/B/C。
- Judge：只负责审核状态变化是否合理；不负责生成剧情，也不直接改状态。
- LLM client：只负责 OpenAI 兼容 HTTP 调用、超时/错误和脱敏日志，不承载游戏规则。

## 目标调用链

```text
Browser UI
  -> FastAPI
  -> WebGameService / WebRunner
  -> GameEngine
  -> World Builder / Narrator / Judge
  -> GameSession.apply_delta
  -> SQLite sessions / saves
  -> FastAPI response
  -> Browser UI
```

关键约束：

- Web 前端只能通过 API 调用游戏逻辑。
- `GameEngine` 是唯一游戏逻辑入口。
- 结构化状态只通过 `GameSession.apply_delta()`、境界系统和突破逻辑生效。
- 背包、功法、地图、任务等面板只能读取 Session/Engine 输出，不自行伪造。

## 瘦身清单

已删除或替换：

- 移动端源码和打包配置
- 设备验证相关文档
- 移动端 UI 测试
- 移动端运行产物说明
- 本项目不再使用的 BGM 适配层

保留：

- `src/agens_novel/`
- `config/prompts/system/`
- 核心规则测试
- Agent、LLM、状态、存档相关测试
- Web 后端和前端测试

## 技术债队列

| 优先级 | 问题 | 处理方向 |
| --- | --- | --- |
| P1 | `game_engine.py` 体量过大，承担回合、突破、兜底、存档、模型异常等多类职责。 | 先稳定 Web 服务接口，后续拆出模型失败处理、本地故事 runner、突破流程和存读档调度。 |
| P1 | 叙事与状态仍可能不同步，表现为文字获得/升层但背包、功法、状态未落账。 | 收紧 Narrator delta、Judge 修正、`apply_delta()` 和 Web 状态响应。 |
| P1 | 模型返回文本但缺少结构化选项时，容易进入兜底或阻断流程。 | 保持格式修复重试，并在 API 响应中区分请求失败、输出不完整、审核失败和本地兜底。 |
| P2 | 本地故事兜底只达到最小可玩。 | 改成数据文件化故事节点，逐步扩展多套故事。 |
| P2 | Web 多用户会引入会话隔离和密钥安全问题。 | API 层统一鉴权、限流、脱敏日志和 per-user session 存储。 |
| P3 | 测试目录需继续从旧产品分类迁移到 Web 分类。 | 保留核心测试，新增 API 和浏览器测试，删除旧 UI 契约测试。 |

## 验证入口

```powershell
.\.venv\Scripts\python.exe -m compileall -q src tests web
.\.venv\Scripts\python.exe -m pytest -q tests/web
.\.venv\Scripts\python.exe -m pytest -q
```
