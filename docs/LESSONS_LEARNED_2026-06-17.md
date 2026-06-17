# 成功与失败经验 2026-06-17

本文给后续智能体作为执行前速读材料。它只记录已经验证过的工程经验、失败路线和最小操作命令，不替代产品规则文档。

## 先读结论

- 产品验证只走 Android APK + USB 真机 + ADB，不再使用 Windows 桌面 Kivy 真实点击方案。
- 打包优先在 WSL 中使用 Buildozer，构建前必须清理 staging 目录，避免旧验证脚本、截图、JSONL 被打进 APK。
- 默认模型仍是 Agens；DeepSeek 是可选测试项。手机端已验证 DeepSeek 可用，但不能把“后台有调用”直接等同于“UI 一定不会兜底”。
- API key 不得写入仓库、文档或日志；设置页只允许显示 provider/model/key 脱敏摘要。
- 当前最新交付 APK 证据目录是 `D:\chat\plan`，不要把该目录纳入 git。

## 成功经验

### USB 真机验证

稳定 ADB 路径：

```powershell
$adb = 'C:\Users\29176\adb\platform-tools\adb.exe'
```

最小验证命令：

```powershell
& $adb devices -l
& $adb install -r D:\chat\plan\<apk-name>.apk
& $adb shell logcat -c
& $adb shell am force-stop org.agens.agensnovel
& $adb shell am start -n org.agens.agensnovel/org.kivy.android.PythonActivity
```

截图与日志：

```powershell
& $adb shell screencap -p /sdcard/agens_screen.png
& $adb pull /sdcard/agens_screen.png D:\chat\plan\agens_screen.png
& $adb shell rm /sdcard/agens_screen.png

$pid = (& $adb shell pidof org.agens.agensnovel | Select-Object -First 1).Trim()
& $adb shell logcat -d --pid=$pid -v time | Out-File D:\chat\plan\agens_phone_log.txt -Encoding utf8
```

执行要点：

- 先确认手机屏幕亮起、USB 调试授权完成、`adb devices -l` 显示 `device`。
- 每轮验证前先 `logcat -c`，再启动应用，避免旧日志干扰。
- UI 问题优先用真机截图和 logcat 判断，不再依赖桌面窗口截图。

### APK 打包

已验证可用环境：

- WSL2 Ubuntu。
- Buildozer 1.6.0。
- Android API 34、min API 26。
- NDK 25b。
- 架构 `arm64-v8a`。

成功构建路径：

- WSL staging：`/home/jia/agens-build`
- Buildozer 配置：`D:\chat\agens\mobile\buildozer.spec`
- Windows 交付目录：`D:\chat\plan`

构建前必须保持 staging 干净，只保留：

- `mobile/`
- `src/`
- `config/`
- 根目录 `main.py`

最新一次成功包：

- `D:\chat\plan\agensnovel-0.4.0-arm64-v8a-debug.apk`
- 大小：`59,240,761 bytes`
- SHA256：`623E84AD83D93BFAF34714D786719FDB49189E1F53973BCC5C4D6B7CC0B383B1`
- staging 已确认不包含 `demos/`。

### 本地自动化检查

打包前最小检查：

```powershell
.\.venv\Scripts\python.exe -m compileall -q src tests mobile\main.py mobile\audio_manager.py mobile\screens mobile\widgets mobile\service
.\.venv\Scripts\python.exe -m pytest -q tests\mobile\test_buildozer_spec.py tests\mobile\test_mobile_startup.py tests\unit\game\test_bgm.py
```

架构改动后推荐检查：

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\unit\engine tests\unit\game tests\mobile
```

## 失败经验

### 不再使用桌面真实点击验证

Windows 桌面 Kivy 真实点击路线出现过黑屏、进程未响应、窗口焦点和截图不稳定问题。该路线已经放弃，后续不要继续投入时间。

正确替代方案：构建 APK 后，通过 USB 真机 + ADB 安装、启动、截图、拉日志。

### WSL 直接执行 Windows 脚本会被 CRLF 阻断

现象：

```text
set: -\r: invalid option
$'\r': command not found
```

原因：`.sh` 文件在 Windows 工作区可能被 CRLF 处理，WSL Bash 会把行尾 `\r` 当作命令字符。

处理方式：

- 长期方案：保持 `mobile/scripts/*.sh` 为 LF。
- 临时方案：在 WSL 内生成 LF 临时脚本，或用 PowerShell here-string 直接管道给 `wsl bash`。

### 旧 staging 会污染 APK

曾出现 Buildozer 把旧 `demos/validation`、截图、JSONL、历史报告复制进 APK 的情况。原因是 WSL staging 目录里残留旧文件，而 `source.dir = ..` 会从 staging 根目录收集内容。

处理方式：

- 打包前清理 `/home/jia/agens-build` 根目录，只保留 `mobile`、`src`、`config`。
- 不要把 `demos/`、`docs/`、`runtime/`、旧截图放进 staging。
- 构建后检查 `.buildozer/android/app` 中没有 `demos/`。

### 根目录 `bgm.flac` 已不是可靠路径

实际音频在：

```text
mobile/assets/audio/bgm.flac
```

旧同步脚本曾执行：

```bash
cp "$ROOT/bgm.flac" "$DEST/bgm.flac"
```

这会在根目录没有 `bgm.flac` 时阻断打包。同步脚本已经修正，不应恢复该拷贝。

### 后台有模型调用不代表 UI 没有兜底

已观察到：DeepSeek 后台有调用记录，但游戏 UI 仍可能出现兜底提示。

合理原因包括：

- 请求超时。
- 流式读取超时。
- 模型返回文本但缺少 `choices` 或 `state_update`。
- JSON/结构化解析失败。
- Judge 二次审核失败。

排查时看 logcat 中的 provider/model、耗时、错误类型、解析状态和 fallback 原因，不要只判断 key 是否保存。

### GitHub 推送不稳定时不要卡住

此前 `git push` 受网络和代理影响失败过。需要跨电脑交付时，优先按 `docs/ZIP_TRANSFER.md` 使用 source-only archive 或直接交付 APK，不要复制 `.venv*`、Buildozer 输出、runtime 和验证证据目录。

## 后续智能体执行顺序

1. 先读 `AGENTS.md`，确认 Android-only、A/B/C/D、隐藏规则、境界顺序和密钥边界。
2. 再读 `docs/INDEX.md`，找到本次任务相关文档。
3. 若是打包或真机验证，先读本文。
4. 若是业务/代码流程分析，读 `docs/RUNTIME_FLOW.md`。
5. 若是迁移到其他电脑，读 `docs/ZIP_TRANSFER.md`。
6. 修改代码前先看 `git status --short`，不要回退用户已有改动。

## 禁止重复踩坑

- 不用桌面真实点击替代 USB 真机验证。
- 不把 `D:\chat\plan`、`runtime/`、`mobile/bin/`、`.buildozer/`、`.venv*` 纳入 git。
- 不在文档、日志、提交信息中写真实 API key。
- 不恢复旧 REPL/CLI 产品入口。
- 不恢复三档自由度模式。
- 不恢复已删除境界。
- 不增加常驻战斗按钮。
