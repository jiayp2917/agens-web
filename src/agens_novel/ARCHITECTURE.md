# agens_novel Architecture

## 概述

`agens_novel` 是文字修仙模拟器的核心引擎，提供游戏逻辑、状态管理、AI 集成等功能。本模块与 Kivy UI 层（`mobile/`）分离，可独立测试和运行。

## 模块协作流程

```
mobile/main.py (Kivy 入口)
    ↓
mobile/service/engine_adapter.py (UI → 引擎的桥)
    ↓
src/agens_novel/session/game_session.py (游戏会话，管理 player state)
    ↓
src/agens_novel/engine/game_engine.py (核心游戏循环，唯一入口)
    ├─→ engine/turn_runner.py (每回合调 LLM)
    ├─→ engine/render.py (生成 UI 文本)
    └─→ game/{combat,realm,constants}.py (规则)
    ↓
src/agens_novel/agents/{narrator,world_builder,judge}/ (LangGraph 3 Agent)
    ↓
src/agens_novel/llm/client.py (OpenAI 兼容 HTTP)
    ↓
src/agens_novel/persistence/save_manager.py (存档)
```

## 核心模块说明

### `engine/` - 游戏引擎
- **`game_engine.py`**: 核心游戏逻辑入口，管理游戏循环、事件回调、状态更新
- **`turn_runner.py`**: 每回合调用 LLM Agent，处理响应和错误
- **`render.py`**: 将游戏状态渲染为 UI 文本

### `session/` - 会话管理
- **`game_session.py`**: 游戏会话对象，管理角色状态、世界状态、背包等

### `game/` - 游戏规则
- **`combat.py`**: 回合制战斗系统
- **`realm.py`**: 境界系统和突破规则
- **`constants.py`**: 游戏常量配置

### `agents/` - AI Agent
- **`narrator/`**: 叙事 Agent，生成游戏剧情
- **`world_builder/`**: 世界生成 Agent，初始化游戏世界
- **`judge/`**: 判定 Agent，验证玩家动作合理性

### `llm/` - LLM 集成
- **`client.py`**: OpenAI 兼容的 HTTP 客户端
- **`sse.py`**: SSE 流式响应解析

### `persistence/` - 存档系统
- **`save_manager.py`**: 存档读写管理

### `state/` - 状态管理
- **`game_schema.py`**: 游戏状态数据模型
- **`reducers.py`**: 状态更新器

## UI 集成

Android UI (Kivy) 通过 **唯一入口** 调用游戏引擎：

```python
# mobile/service/engine_adapter.py
from agens_novel.engine.game_engine import GameEngine

engine = GameEngine()
engine.on_narrative = lambda text, turn: ui.update_narrative(text)
engine.on_combat_update = lambda state: ui.update_combat(state)
engine.on_game_over = lambda reason: ui.show_game_over(reason)
```

**重要约定**：
- UI 只通过 `engine_adapter.py` 调用 `GameEngine`
- 不直接引用 `agens_novel.repl.*` (已废弃)
- 所有状态更新通过事件回调

## 关键文件路径

| 模块 | 关键文件 |
|------|---------|
| 引擎入口 | `src/agens_novel/engine/game_engine.py` |
| 会话管理 | `src/agens_novel/session/game_session.py` |
| 存档系统 | `src/agens_novel/persistence/save_manager.py` |
| Agent 调用 | `src/agens_novel/engine/turn_runner.py` |
| UI 桥接 | `mobile/service/engine_adapter.py` |
| Kivy 入口 | `mobile/main.py` |

## 扩展指南

### 添加新的游戏规则
1. 在 `game/` 下创建新模块或扩展现有模块
2. 在 `GameEngine` 中添加对应的处理方法
3. 在 `engine_adapter.py` 中添加 UI 触发点

### 添加新的 Agent
1. 在 `agents/` 下创建新目录
2. 实现 LangGraph Agent 接口
3. 在 `turn_runner.py` 中注册调用

### 修改状态模型
1. 更新 `state/game_schema.py`
2. 添加对应的 reducer 到 `state/reducers.py`
3. 更新 `persistence/save_manager.py` 的序列化逻辑
