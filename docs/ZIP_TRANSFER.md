# ZIP 迁移与新电脑启动指南

本项目可以通过 ZIP 拷到另一台电脑测试，但不建议直接压缩整个 `D:\chat\agens` 目录。当前工作目录里包含本机专属虚拟环境、Buildozer 构建缓存、运行日志、存档和 Git 元数据，直接打包会很大，也可能带走无效路径或 reparse point。

## 推荐打包方式

在源电脑执行：

```powershell
cd D:\chat\agens
git status --short --untracked-files=no
git archive --format=zip --output D:\chat\agens-transfer.zip HEAD
```

`git archive` 只打包当前提交中的源码、文档、配置、提示词、BGM 和最终使用的 UI 资产，不会带走 `.venv/`、`.venv311/`、`.git/`、`mobile/.buildozer/`、`mobile/bin/`、`runtime/` 等本机产物。

如果有未提交改动，先确认是否要纳入迁移；`git archive HEAD` 不会包含未提交内容。

## 不建议打包的目录

手动压缩时至少排除：

- `.git/`
- `.venv/`
- `.venv311/`
- `.pytest_cache/`
- `.ruff_cache/`
- `.tmp/`
- `__pycache__/`
- `runtime/artifacts/`
- `runtime/checkpoints/`
- `runtime/logs/`
- `runtime/backups/`
- `runtime/saves/`
- `mobile/.buildozer/`
- `mobile/bin/`
- `mobile/agens_novel/`
- `mobile/config/`

其中 `mobile/agens_novel/` 和 `mobile/config/` 是本机打包/同步过程产生的 reparse point，可能导致 Windows ZIP 或 Git 扫描出现访问 warning。当前 Buildozer 配置从仓库根目录打包，不依赖这两个目录。

## 新电脑准备

1. 解压到目标目录，例如：

```powershell
D:\chat\agens
```

2. 安装 Python 3.11。

3. 创建测试环境：

```powershell
cd D:\chat\agens
python -m venv .venv
.\.venv\Scripts\activate
pip install -e ".[dev]"
```

4. 配置模型环境变量。密钥只放在当前 PowerShell 会话或应用内设置，不写入仓库：

```powershell
$env:AGNES_BASE_URL = "https://apihub.agnes-ai.com/v1"
$env:AGNES_MODEL    = "agnes-2.0-flash"
$env:AGNES_API_KEY  = "<your key>"
```

5. 构建 APK 后通过 USB 真机验证。ADB 命令模板见 `docs/RUNTIME_FLOW.md`。

## 新电脑验证

```powershell
cd D:\chat\agens
.\.venv\Scripts\python.exe -m compileall -q src tests mobile\main.py mobile\audio_manager.py mobile\screens mobile\widgets mobile\service
.\.venv\Scripts\python.exe -m pytest -q
```

如果要打包 APK，优先在 WSL2/Linux 环境使用 Buildozer：

```powershell
/build-apk
```

或在 Linux/WSL2 中进入 `mobile/` 后执行 Buildozer 命令。APK 构建产物和缓存仍应留在本地，不提交、不作为迁移包内容。

## 常见问题

- GitHub 推送失败不影响 ZIP 迁移；只要本地提交存在，`git archive HEAD` 就能生成迁移包。
- 如果新电脑启动时没有真实模型密钥，游戏会进入模型失败/兜底路径，不能代表真实体验。
- 如果只复制源码、不复制 `runtime/saves/`，旧电脑上的本地存档不会随包迁移。
- 如果手动复制整个目录，虚拟环境通常不能跨机器可靠复用，建议在新电脑重新创建 `.venv`。
