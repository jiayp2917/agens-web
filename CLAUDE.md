# agens-novel — Android-Only 开发说明

## 当前产品通路

本项目只保留 Android/Kivy 产品入口。不要恢复终端交互入口、CLI 命令或旧 REPL UI。

桌面调试启动：

```powershell
cd D:\chat\agens
.\.venv311\Scripts\python.exe mobile\main.py
```

测试：

```powershell
.\.venv\Scripts\python.exe -m compileall -q src tests mobile\main.py mobile\audio_manager.py mobile\screens mobile\widgets mobile\service demos/full_flow/demo_full_flow.py
.\.venv\Scripts\python.exe -m pytest -q
```

## 架构边界

- Android UI 只通过 `mobile/service/engine_adapter.py` 调用 `GameEngine`。
- `GameEngine` 是唯一游戏逻辑入口。
- `GameSession` 位于 `src/agens_novel/session/game_session.py`。
- 存档位于 `src/agens_novel/persistence/save_manager.py`。
- Agent 调用器位于 `src/agens_novel/engine/turn_runner.py`。
- REPL/CLI/终端入口已于历史版本移除，仅保留 `mobile/main.py` 单一入口。

## 架构图

详细架构与模块职责见 [src/agens_novel/ARCHITECTURE.md](src/agens_novel/ARCHITECTURE.md)。

## 入口说明

**统一入口**：项目只保留 `mobile/main.py` 作为唯一入口。
- **桌面调试**：直接运行 `python mobile/main.py`
- **Android 打包**：Buildozer 从 `mobile/` 目录打包，使用 `mobile/main.py` 作为入口
- 根目录不再有 `main.py`，所有入口统一到 `mobile/` 下

## UI 契约

- A/B/C 是模型基于上下文生成的建议选项。
- D 是底部自由输入框。
- 存档、读档、状态、背包、装备、功法、任务、突破、设置放在“更多”工具弹窗。
- 战斗不提供常驻按钮，玩家通过 D 输入框输入自然语言行动。
- 飞升页必须显示“飞升成仙”，不得复用死亡标题。

## 禁止项

- 不把 API key 写入代码、文档、日志或持久化环境变量。
- 不在 UI 明示隐藏触发规则或隐藏模式名称。
- 不恢复已删除境界。
- 不回退用户已有工作区改动。
