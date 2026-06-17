# 项目深度复盘 2026-06-17

## 结论

- 产品通路保持 Android-only：Kivy/Buildozer 是唯一对外入口，后续流程验证只走 USB 真机。
- 当前玩法契约保持单一 A/B/C/D：A/B/C 由模型按上下文生成，D 为玩家自由键入。
- USB 真机验证路线已证明比 Windows 桌面真实点击路线稳定；后续需要真实点击、截图、日志时优先走 ADB。
- 默认模型仍为 Agens；DeepSeek 作为可选测试预设。手机端已确认 DeepSeek 可用，但设置页必须通过脱敏摘要确认当前生效配置。
- 本轮清理运行产物和失败验证残留，不做大文件拆分，不改变核心流程。

## 冗余清理

- 移出 git 跟踪的验证产物：`demos/validation/screenshots/*` 和 `demos/validation/auto_validate_v040.jsonl`。
- 删除失败的 Windows 桌面真实点击方案残留：`demos/validation/real_click*`、`capture_region_win.py`、`kivy_minimal_probe.py`。
- 删除旧桌面演示/自动验证路线：`demos/full_flow/`、`demos/validation/auto_validate_v040.py`、`docs/validation_report_v0.4.0.md`。
- 清理本地运行产物：`runtime/artifacts/`、`runtime/logs/`、`runtime/saves/`、`demos/validation/__pycache__/`。
- 保留 `runtime/.gitkeep`。
- `.gitignore` 已补充验证截图、JSONL、APK、runtime 日志/存档等规则，避免产物再次入库。
- `D:\chat\plan` 是外部证据目录，本轮不删除；后续如要压缩迁移，应先筛选最新 APK、截图和日志。

保留的外部证据索引：

- `D:\chat\plan\agens_deepseek_phone_log.txt`：DeepSeek 手机验证日志。
- `D:\chat\plan\agens_deepseek_home.png`：DeepSeek 验证首页截图。
- `D:\chat\plan\agens_deepseek_character.png`：DeepSeek 验证角色创建截图。
- `D:\chat\plan\agens_deepseek_loading.png`：DeepSeek 验证加载态截图。
- `D:\chat\plan\agens_deepseek_after45.png`：DeepSeek 等待后兜底/异常状态截图。
- `D:\chat\plan\agensnovel-timeout75-20260616_214752.apk`：最近一次 timeout=75 的 APK 证据包。

## USB 手机验证经验

稳定 ADB 路径：

```powershell
$adb = 'C:\Users\29176\adb\platform-tools\adb.exe'
```

常用检查：

```powershell
& $adb devices -l
& $adb shell pm path org.agens.agensnovel
& $adb shell pidof org.agens.agensnovel
```

安装与启动：

```powershell
& $adb install -r D:\chat\plan\<apk-name>.apk
& $adb shell logcat -c
& $adb shell am force-stop org.agens.agensnovel
& $adb shell am start -n org.agens.agensnovel/org.kivy.android.PythonActivity
```

截图取证：

```powershell
& $adb shell screencap -p /sdcard/agens_screen.png
& $adb pull /sdcard/agens_screen.png D:\chat\plan\agens_screen.png
& $adb shell rm /sdcard/agens_screen.png
```

日志取证：

```powershell
$pid = (& $adb shell pidof org.agens.agensnovel | Select-Object -First 1).Trim()
& $adb shell logcat -d --pid=$pid -v time | Out-File D:\chat\plan\agens_phone_log.txt -Encoding utf8
```

经验记录：

- 使用 USB 真机时，先确认手机屏幕亮起、USB 调试授权弹窗已同意、`adb devices -l` 显示 `device`。
- 截图优先使用 `adb shell screencap` 后 `adb pull`；不要依赖 Windows 桌面窗口截图判断 Android 真机 UI。
- 日志先清空再启动，避免混入旧包日志；按 PID 拉取比全量 logcat 更易定位。
- 设置页保存 key 后不应回显明文；应显示 provider/model/key 掩码摘要，用于确认当前生效配置。

## DeepSeek 与模型配置

- 默认配置仍是 Agens：`https://apihub.agnes-ai.com/v1` + `agnes-2.0-flash`。
- DeepSeek 测试配置为：`https://api.deepseek.com/v1` + `deepseek-chat`。
- 手机端 key 保存策略：非密钥配置写入 `settings.json` / `user_model.json`，API key 写入 app-private `secrets.json`，不写入普通设置文件，不在 UI 回显明文。
- 已观察到的“天道紊乱但后台有调用”更像请求超时、流式读取超时、模型返回不可解析或二次 Agent 调用失败，不应简单归因为 key 未保存。
- 后续定位该问题时，优先看 logcat 中的 `load_settings`、`call_llm_stream`、`ReadTimeout`、`llm_error`、`fallback`、`choices`、`narrator error`。

## 架构审查

当前架构：

- `mobile/main.py` 启动 Kivy 应用并加载设置。
- Android UI 通过 `mobile/service/engine_adapter.py` 进入 `GameEngine`。
- `GameEngine` 是唯一游戏逻辑入口，负责回合、突破、存读档、模型异常兜底和终局回调。
- `Narrator`、`World Builder`、`Judge` 通过 OpenAI 兼容 LLM 客户端协作。
- `Session`、`Persistence`、`Game` 规则层保持 UI 无关。

轻量风险：

- `src/agens_novel/engine/game_engine.py` 已超过 1400 行，后续应拆分回合处理、突破处理、兜底处理和存档回调。
- `mobile/screens/home_screen.py` 已超过 500 行，后续可拆出设置弹窗、读档弹窗和教程弹窗。
- `runtime/` 是运行产物，不应作为源码架构权重；审计报告中需要单独排除或标注。
- Windows 桌面真实点击路线已多次受窗口焦点、黑屏和未响应影响，不再作为主验证方案。

## 后续队列

1. 真机优先验证 DeepSeek 回合：设置保存、当前生效摘要、开局、3-5 回合、出现“天道紊乱”时拉取日志。
2. 定位“后台调用但 UI 兜底”的真实原因：区分请求超时、解析失败、Judge 失败和用户选择超时。
3. 分阶段拆分 `game_engine.py` 和 `home_screen.py`，先加测试保护，再小步拆。
4. 完善文档中 API key 描述，统一为“app-private secrets.json，不写 settings.json，不回显明文”。
5. ZIP/跨机迁移时使用 `git archive` 或源代码包，不复制 `.venv*`、Buildozer 输出、runtime 产物和手机验证证据目录。
