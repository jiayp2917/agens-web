# Agent 操作规则

本文只记录非玩法类执行规则，目标是减少后续智能体在 Windows、WSL、APK、ADB、日志、密钥和产物目录上的重复试错。业务流程和游戏设计以 `AGENTS.md`、`docs/RUNTIME_FLOW.md` 及对应代码为准。

## 读取顺序

1. 先读 `AGENTS.md` 和 `docs/INDEX.md`，确认本次任务属于哪一类。
2. 涉及 APK 打包、真机验证、ADB、logcat 时，必须读 `docs/LESSONS_LEARNED_2026-06-17.md`。
3. 涉及跨电脑迁移或交付源码包时，必须读 `docs/ZIP_TRANSFER.md`。
4. 修改代码前先执行 `git status --short`，理解脏工作区，不回退用户已有改动。

## PowerShell 与编码

- 仓库源码和文档默认按 UTF-8 处理。
- PowerShell 读取含中文文件时，不依赖默认编码，使用：

```powershell
Get-Content -Raw -Encoding UTF8 <path>
```

- 输出中文日志或文件时显式指定 UTF-8，例如：

```powershell
Out-File <path> -Encoding utf8
```

- Python 读写文本文件必须显式指定 `encoding="utf-8"`。
- 看到中文乱码时，先怀疑终端显示或命令编码；用显式 UTF-8 方式复读文件确认，不要直接批量重存、转码或替换源码中文。
- PowerShell 调用可执行文件使用 `&`：

```powershell
& 'C:\Users\29176\adb\platform-tools\adb.exe' devices -l
```

## Windows 与 WSL 分工

- Windows 侧用于源码编辑、本地 pytest、ADB 真机验证和证据整理。
- APK 打包优先在 WSL2/Linux 中使用 Buildozer。
- 不要把 Bash 写法直接当 PowerShell 执行，也不要把 PowerShell 变量语法直接放进 Bash。
- WSL 中执行 `.sh` 前确认脚本为 LF 行尾。若出现 `$'\r': command not found` 或 `set: -\r: invalid option`，先处理 CRLF，不要改业务代码。
- 临时执行 Bash 逻辑时，可在 WSL 内生成 LF 临时脚本，或从 PowerShell here-string 管道给 `wsl bash`。

## Buildozer 与 APK

- 打包前保持 WSL staging 目录干净；已验证 staging 路径为 `/home/jia/agens-build`。
- staging 根目录只应保留：
  - `mobile/`
  - `src/`
  - `config/`
  - `main.py`
- 不要把 `demos/`、`docs/`、`runtime/`、旧截图、JSONL、历史报告或本机缓存放进 staging。
- 构建后检查 `.buildozer/android/app`，确认没有 `demos/`、`docs/`、`runtime/` 等无关目录。
- `mobile/buildozer.spec` 的 `source.dir = ..` 表示会从 staging 根目录收集内容，staging 污染会直接污染 APK。
- 真实交付 APK 和验证证据放在 `D:\chat\plan`，该目录不属于仓库内容。

## ADB 与真机验证

- 固定 ADB 路径：

```powershell
$adb = 'C:\Users\29176\adb\platform-tools\adb.exe'
```

- 每轮真机验证先确认设备授权并清空旧日志：

```powershell
& $adb devices -l
& $adb shell logcat -c
```

- 安装和启动模板：

```powershell
& $adb install -r D:\chat\plan\<apk-name>.apk
& $adb shell am force-stop org.agens.agensnovel
& $adb shell am start -n org.agens.agensnovel/org.kivy.android.PythonActivity
```

- 截图和日志模板：

```powershell
& $adb shell screencap -p /sdcard/agens_screen.png
& $adb pull /sdcard/agens_screen.png D:\chat\plan\agens_screen.png
& $adb shell rm /sdcard/agens_screen.png

$pid = (& $adb shell pidof org.agens.agensnovel | Select-Object -First 1).Trim()
& $adb shell logcat -d --pid=$pid -v time | Out-File D:\chat\plan\agens_phone_log.txt -Encoding utf8
```

- UI 问题优先用真机截图和 logcat 判断，不使用 Windows 桌面 Kivy 真实点击作为产品验证路径。
- 每轮启动前清空 logcat，避免旧日志误判。

## 模型与日志判断

- 默认模型配置仍以项目现有设置为准；更换供应商或默认模型前必须明确说明影响并征得用户确认。
- 后台有模型调用记录不等于 UI 没有进入兜底路径。
- 排查模型相关问题时看 provider/model、耗时、异常类型、响应结构、解析状态和审核结果，不只判断 key 是否保存或请求是否发出。
- `llm/client.py`、`llm/retry.py`、`llm/sse.py` 是通用 LLM 层，非必要不改。

## 密钥边界

- API key 不写入源码、文档、日志、提交信息或普通设置文件。
- 本地调试只使用当前进程环境变量；移动端用户输入的 key 只能保存到 app-private `secrets.json`。
- UI、日志和文档只能展示脱敏摘要。
- 测试中使用 fake key，不使用真实 key。

## 本地检查

- 普通代码改动至少先跑编译检查：

```powershell
.\.venv\Scripts\python.exe -m compileall -q src tests mobile\main.py mobile\audio_manager.py mobile\screens mobile\widgets mobile\service
```

- 按改动范围运行 pytest。打包前最小检查可参考：

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\mobile\test_buildozer_spec.py tests\mobile\test_mobile_startup.py tests\unit\game\test_bgm.py
```

- 涉及架构、引擎或移动端入口时，优先扩大到：

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\unit\engine tests\unit\game tests\mobile
```

- 真实 LLM 测试不是默认验证项；没有 `AGNES_API_KEY` 时跳过不应视为失败。

## 资产与音频

- 新资产放在 `mobile/assets/` 下，并确认 `mobile/buildozer.spec` 包含最终使用格式。
- BGM 实际文件路径是 `mobile/assets/audio/bgm.flac`；不要依赖根目录 `bgm.flac`。
- 修复音频问题时优先核对 `src/agens_novel/bgm.py`、`mobile/audio_manager.py` 和 `tests/unit/game/test_bgm.py`。

## 产物、迁移与 Git

- 不提交或迁移本机产物：`.venv*`、`.pytest_cache/`、`.ruff_cache/`、`mobile/.buildozer/`、`mobile/bin/`、`runtime/`、APK、截图、logcat、JSONL。
- `D:\chat\plan` 是外部 APK 和证据目录，不纳入 git。
- 跨电脑迁移优先使用 `git archive` 或 source-only archive，不直接压缩整个工作目录。
- GitHub push 不稳定时，不要卡住交付；优先按 `docs/ZIP_TRANSFER.md` 准备源码包或直接交付 APK。
- 需要清理产物时先列出目标路径并确认范围，避免误删源码或用户文件。
