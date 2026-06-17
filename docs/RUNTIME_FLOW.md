# 项目实际运行逻辑

本文只记录当前运行流程。产品验证只走 Android APK + USB 真机，不再使用 Windows 桌面 Kivy 窗口。

## 业务逻辑

1. 主页
   - 用户进入主页，可选择新游戏、读档、教程、设置、退出。
   - 主页提供 BGM 开关；设置中可选择模型预设、填写 Base URL、Model、API Key、主题色和音频开关。
   - 默认模型预设是 Agens；DeepSeek 是可选测试预设。

2. 设置保存
   - Base URL、Model、主题、音频写入普通设置。
   - API Key 写入应用私有 `secrets.json`，不写入仓库、文档、日志或普通设置文件。
   - UI 只显示脱敏后的 provider/model/key 摘要，不回显明文 key。

3. 角色创建
   - 新游戏进入角色创建页。
   - 用户填写游戏名称、角色名，选择天赋、灵根、家世、难度，可随机基础属性。
   - 确认后进入游戏页，并启动开场推演。

4. 开场推演
   - 优先调用 World Builder 生成开场叙事和 A/B/C 选项。
   - A/B/C 必须基于当前角色和世界上下文。
   - D 不由模型生成，始终是底部自由输入框。
   - 模型失败、无 key、超时或无可用选项时，弹出“本地兜底继续 / 结束本局”。

5. 回合推进
   - 用户点击 A/B/C 时，对应选项文本作为本回合行动。
   - 用户在 D 输入框键入时，自由文本作为本回合行动。
   - 每回合由 Narrator 生成叙事、状态变化和下一组 A/B/C。
   - Judge 审核状态变化；审核失败且无修正时，本回合叙事可显示，但状态变化不生效。

6. 修炼与突破
   - 纯修炼主要增长修为，可推进小层。
   - 大境界突破需要满层、修为、感悟和对应破境准备。
   - 历练、请教、探索、任务、寻药、炼丹、炼器、阵法、战斗等行动才更容易获得感悟和破境准备。
   - 境界顺序固定为：练气、筑基、金丹、元婴、化神、合体、大乘、渡劫、飞升。

7. 战斗
   - 战斗不提供常驻按钮。
   - 玩家仍通过 D 输入框键入攻击、防御、逃跑、施展功法等自然语言行动。
   - 界面只显示紧凑战斗状态提示。

8. 存档和终局
   - 开局、回合结束、突破后会自动保存。
   - 更多工具中可手动存档、读档、查看状态、背包、装备、功法、任务、地图和突破。
   - HP 归零或模型不可用且用户选择结束本局时进入死亡/结束态。
   - 渡劫突破到飞升时进入独立“飞升成仙”终局。

## 代码逻辑

1. APK 入口
   - `main.py` 是 APK 启动入口，导入 `mobile.main.XianxiaApp`。
   - `mobile/main.py` 初始化路径、日志、字体、主题、设置、音频和存档目录。
   - Kivy `ScreenManager` 注册 `HomeScreen`、`CharacterCreateScreen`、`GameScreen`、`DeathScreen`。

2. UI 到引擎
   - Android UI 不直接修改 `GameSession`。
   - `mobile/service/engine_adapter.py` 持有唯一 `GameEngine` 实例。
   - UI 调用 `EngineAdapter.start_from_profile()`、`handle_action()`、`attempt_breakthrough()`、`save()`、`load()`。
   - 耗时引擎调用放到后台线程，引擎回调通过 `Clock.schedule_once` 回到 Kivy 主线程更新 UI。

3. 设置链路
   - `mobile/service/settings_store.py` 读取 `settings.json`、`user_model.json` 和私有 `secrets.json`。
   - `apply_settings_to_env()` 把当前生效的 `AGNES_BASE_URL`、`AGNES_MODEL`、`AGNES_API_KEY` 注入进程环境。
   - `src/agens_novel/llm/client.py` 调用 OpenAI 兼容 `/chat/completions`，读取这些环境变量。

4. 开局链路
   - `CharacterCreateScreen._start()` 组装 profile。
   - `EngineAdapter.start_from_profile(profile)` 后台调用 `GameEngine.start_from_profile(profile)`。
   - `GameEngine` 初始化 `GameSession`，再调用 `run_turn_sync("world_builder", ...)`。
   - World Builder 输出开场叙事、角色/世界数据和 A/B/C。
   - 引擎写入 `game_session.last_choices`，回调 `on_narrative`、`on_character_created`、`on_status_bar`。

5. 普通回合链路
   - `GameScreen` 的 A/B/C 按钮或 D 输入框进入 `_on_user_action(text)`。
   - `EngineAdapter.handle_action(text)` 调用 `GameEngine.handle_action(text)`。
   - 引擎先把 `A/B/C/1/2/3` 映射成当前 `last_choices`，`D:` 前缀会剥离为自由输入。
   - 若文本表达突破意图，转入 `attempt_breakthrough()`。
   - 若文本是明确战斗指令，转入本地战斗逻辑。
   - 其他行动调用 `run_turn_sync("narrator", ...)`。
   - Narrator 返回 `narrative`、`state_delta`、`choices`。
   - 若有 `state_delta`，再调用 `run_turn_sync("judge", ...)` 审核。
   - 审核后由 `GameSession.apply_delta()` 应用状态，随后尝试小层自动推进、检查死亡或飞升、自动保存。

6. 选项和兜底
   - `normalize_choices()` 只清洗模型选项，不补固定项。
   - `_set_choices()` 在模型选项为空或模型失败时才调用 `fallback_choices()`。
   - 需要玩家选择时，引擎通过 `on_model_failure_choice` 同步等待 UI 弹窗结果。
   - 用户选“本地兜底继续”则写入本地 A/B/C 并显示“天道紊乱，暂以因果残影指引。”。
   - 用户选“结束本局”则设置 `game_over` 并进入结束页。

7. 突破链路
   - `GameEngine.attempt_breakthrough()` 先调用 `RealmSystem.can_attempt_breakthrough(session)`。
   - 不满足满层、修为、感悟或破境准备时，只提示原因，不进入突破。
   - 满足条件后，Narrator 生成突破叙事和选项。
   - `RealmSystem.attempt_breakthrough(session)` 执行本地概率判定并生成权威境界变化。
   - Judge 审核合并后的变化。
   - 成功突破到“飞升”时设置 finale，`GameScreen` 跳转 `DeathScreen` 的飞升态。

8. 存档链路
   - `mobile/service/save_manager_compat.py` 将存档目录指向 Android app 私有目录。
   - `src/agens_novel/persistence/save_manager.py` 负责 JSON 存读档、槽位列表、删除和重命名。
   - `GameSession.to_save_dict()` 和 `from_save_dict()` 负责状态序列化兼容。

## USB 真机调试

固定 ADB 路径：

```powershell
$adb = 'C:\Users\29176\adb\platform-tools\adb.exe'
```

安装和启动：

```powershell
& $adb devices -l
& $adb install -r D:\chat\plan\<apk-name>.apk
& $adb shell logcat -c
& $adb shell am force-stop org.agens.agensnovel
& $adb shell am start -n org.agens.agensnovel/org.kivy.android.PythonActivity
```

截图和日志：

```powershell
& $adb shell screencap -p /sdcard/agens_screen.png
& $adb pull /sdcard/agens_screen.png D:\chat\plan\agens_screen.png
& $adb shell rm /sdcard/agens_screen.png

$pid = (& $adb shell pidof org.agens.agensnovel | Select-Object -First 1).Trim()
& $adb shell logcat -d --pid=$pid -v time | Out-File D:\chat\plan\agens_phone_log.txt -Encoding utf8
```

后续问题复现、截图、日志均按 USB 真机路线执行。
