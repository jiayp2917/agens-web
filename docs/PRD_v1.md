# PRD v1 — Android 文字修仙模拟器

## Product Goal

交付 Android 竖屏文字修仙模拟器。玩家通过模型生成的 A/B/C 选项和 D 自由输入推进修仙叙事。

## Primary Flow

1. 主页：新游戏、读档、教程、设置、退出，右上 BGM 开关。
2. 角色创建：游戏名称、角色名、天赋、灵根、家世、难度、基础属性随机。
3. 开局：World Builder 生成背景叙事和 A/B/C。
4. 回合：玩家点击 A/B/C 或键入 D 行动。
5. 叙事：Narrator 生成结果、状态变化和下一轮 A/B/C。
6. 审核：Judge 校验状态变化合理性。
7. 工具：存档、读档、状态、背包、装备、功法、任务、突破、设置在“更多”弹窗中。
8. 终局：死亡可重开/读档/回主页；飞升显示“飞升成仙”。

## Gameplay Rules

- 境界：练气、筑基、金丹、元婴、化神、合体、大乘、渡劫、飞升。
- A/B/C 必须尽量来自模型，基于上文、地点、NPC、资源、风险生成。
- D 始终是自由输入，不作为模型生成的第四选项。
- 模型失败或无选项时显示“天道紊乱，暂以因果残影指引。”并使用系统兜底。
- 纯修炼不能直接满足所有大境界突破条件。
- 战斗通过自然语言输入完成，不设置常驻战斗按钮。

## Android UI Requirements

- 主页使用水墨背景和轻量按钮。
- 游戏页阅读优先：顶部状态压缩，中部叙事最大化，底部只保留“更多 + D 输入 + 发送”。
- 更多工具弹窗保留全部辅助功能。
- 角色创建底部固定“随机属性 / 开始修行”。
- 所有触控目标不小于 44dp。
- UI 不明示隐藏触发规则或隐藏模式名称。

## Technical Boundaries

- Product entry: `mobile/main.py`.
- Core logic: `src/agens_novel/engine/game_engine.py`.
- Session: `src/agens_novel/session/game_session.py`.
- Persistence: `src/agens_novel/persistence/save_manager.py`.
- Agent runner: `src/agens_novel/engine/turn_runner.py`.
- Terminal product entry is not supported.
- API keys are runtime-only configuration.

## Acceptance

- `compileall` passes for `src`, `tests`, `mobile`.
- `pytest -q` passes.
- Desktop Kivy debug launch renders home, character creation, and game screen.
- Running code and non-archive docs do not contain removed realm or hidden-mode UI wording.
- Buildozer config includes required image, font, JSON/YAML/text, and audio assets.
