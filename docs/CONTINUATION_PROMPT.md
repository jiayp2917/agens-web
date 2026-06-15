# 后续开发提示词

项目路径：`D:\chat\agens`

## 当前目标

继续维护 Android-only 文字修仙模拟器。产品入口是 Kivy/Buildozer 移动端，不恢复终端 REPL/CLI。

## 关键流程

1. 主页进入新游戏、读档、教程、设置或退出。
2. 角色创建提交 profile。
3. `GameEngine.start_from_profile()` 优先调用 World Builder 生成开场叙事和 A/B/C。
4. 游戏页显示顶部角色状态、中部叙事和 A/B/C、底部 D 输入框。
5. 玩家点击 A/B/C 或键入 D 行动。
6. `GameEngine.handle_action()` 调用 Narrator，再由 Judge 审核状态变更。
7. 存档、读档、状态、背包、装备、功法、任务、突破、设置通过“更多”工具弹窗进入。
8. 死亡进入重开/读档/主页；飞升进入“飞升成仙”终局。

## 关键文件

- `mobile/main.py`
- `mobile/screens/home_screen.py`
- `mobile/screens/character_create_screen.py`
- `mobile/screens/game_screen.py`
- `mobile/screens/death_screen.py`
- `mobile/widgets/action_bar.py`
- `mobile/widgets/narrative_view.py`
- `mobile/service/engine_adapter.py`
- `src/agens_novel/engine/game_engine.py`
- `src/agens_novel/session/game_session.py`
- `src/agens_novel/persistence/save_manager.py`
- `src/agens_novel/engine/turn_runner.py`

## 验证命令

```powershell
.\.venv\Scripts\python.exe -m compileall -q src tests mobile\main.py mobile\audio_manager.py mobile\screens mobile\widgets mobile\service demo_full_flow.py
.\.venv\Scripts\python.exe -m pytest -q
.\.venv311\Scripts\python.exe mobile\main.py
```

## 开发约束

- 不引用 `agens_novel.repl.*`。
- 不恢复终端产品入口。
- 不把密钥写入仓库。
- A/B/C 模型优先，D 始终是自由输入。
- 战斗通过自然语言输入完成，不增加常驻战斗按钮。
