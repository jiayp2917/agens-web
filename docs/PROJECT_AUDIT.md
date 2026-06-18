# 项目结构审核与收束

本文是当前项目结构、功能边界、冗余清理和技术债队列的精简总览。后续开发先读 `AGENTS.md` 和 `docs/INDEX.md`，再按本文确认边界。

## 当前边界

- 产品入口只保留 Android/Kivy/Buildozer：`mobile/main.py` 和根目录 `main.py`。
- 产品验证只走 Android APK + USB 真机 + ADB；不再使用 Windows 桌面 Kivy 真实点击。
- 当前只开放引导模式：A/B/C 为模型基于上下文生成的选项，D 为玩家键入。
- 小说模式、游戏模式只作为后续接口方向，不在当前运行流程中开放。
- 模型失败、无 key、无有效选项时，用户可选择本地兜底继续或结束本局。
- 境界顺序固定为：练气、筑基、金丹、元婴、化神、合体、大乘、渡劫、飞升。

## 功能分层

| 层级 | 边界 | 主要文件 |
| --- | --- | --- |
| 交互层 | 只负责展示、点击、输入、弹窗和真机 UI 反馈，不直接改游戏状态。 | `mobile/screens/`、`mobile/widgets/`、`mobile/service/engine_adapter.py` |
| 校验层 | 负责模型结果分类、叙事/结构化状态一致性、Judge 审核、本地规则门槛。 | `src/agens_novel/engine/model_result.py`、`action_delta_policy.py`、`game/realm.py`、`agents/judge/` |
| 状态层 | 负责会话状态、结构化 delta 落账、存读档、序列化兼容。 | `src/agens_novel/session/game_session.py`、`src/agens_novel/persistence/save_manager.py` |

## Agent 职责

- World Builder：只负责角色创建后的世界开局、开场叙事和开场 A/B/C。
- Narrator：只负责每回合叙事、结构化状态建议和下一轮 A/B/C。
- Judge：只负责审核状态变化是否合理；不负责生成剧情，也不直接改状态。
- LLM client：只负责 OpenAI 兼容 HTTP 调用、超时/错误和脱敏日志，不承载游戏规则。

## 当前调用链

```text
Android UI
  -> mobile/service/engine_adapter.py
  -> GameEngine
  -> turn_runner
  -> World Builder / Narrator / Judge
  -> GameSession.apply_delta
  -> SaveManager
  -> Engine callbacks
  -> Android UI
```

关键约束：

- Android UI 只能通过 `EngineAdapter` 调用 `GameEngine`。
- `GameEngine` 是唯一游戏逻辑入口。
- 结构化状态只通过 `GameSession.apply_delta()`、境界系统和突破逻辑生效。
- “更多”面板只能读取 Session/Engine 输出，不自行伪造背包、功法、地图或任务。

## 冗余清理结论

- 已确认 `.workbuddy/` 是旧记忆目录，内容仍描述 REPL/纯 Python 架构，应从仓库删除。
- `.claude/` 本轮保留不动，但不作为当前权威文档；当前权威入口是 `AGENTS.md`、`docs/INDEX.md`、`docs/AGENT_OPERATION_RULES.md`。
- 过期问题报告、旧复盘、重复架构图和过长经验文档应合并到本文或删除，避免后续智能体误读。
- `runtime/`、APK、截图、logcat、JSONL、`.venv*`、`__pycache__` 均为本地产物，不进入 git。

## 技术债队列

| 优先级 | 问题 | 处理方向 |
| --- | --- | --- |
| P1 | `game_engine.py` 体量过大，承担回合、突破、兜底、存档、模型异常等多类职责。 | 分步拆出模型失败处理、本地故事 runner、突破流程和存读档调度。 |
| P1 | 叙事与状态仍可能不同步，表现为文字获得/升层但背包、功法、状态未落账。 | 收紧 Narrator delta、Judge 修正、`apply_delta()` 和 UI 刷新链路。 |
| P1 | 模型返回文本但缺少结构化选项时，容易进入兜底或阻断流程。 | 保持格式修复重试，并在日志中区分请求失败、输出不完整、审核失败和本地兜底。 |
| P2 | `game_screen.py` 超过 500 行。 | 拆出工具弹窗、存读档弹窗、模型失败弹窗。 |
| P2 | 本地故事兜底只达到最小可玩。 | 后续改成数据文件化故事节点，逐步扩展多套故事。 |
| P3 | 测试目录有正式回归、破坏性测试和历史演示测试混杂趋势。 | 明确测试分类，避免历史验证脚本成为长期主路径。 |

## 验证入口

本地检查：

```powershell
.\.venv\Scripts\python.exe -m compileall -q src tests mobile\main.py mobile\audio_manager.py mobile\screens mobile\widgets mobile\service
.\.venv\Scripts\python.exe -m pytest -q
```

USB 真机：

```powershell
$adb = 'C:\Users\29176\adb\platform-tools\adb.exe'
& $adb devices -l
& $adb install -r D:\chat\plan\<apk-name>.apk
& $adb shell logcat -c
& $adb shell am force-stop org.agens.agensnovel
& $adb shell am start -n org.agens.agensnovel/org.kivy.android.PythonActivity
```

审计：

```powershell
python C:\Users\29176\.codex\skills\codex-dev-team\scripts\project_audit.py --root D:\chat\agens --forbid <forbidden-term>
```
