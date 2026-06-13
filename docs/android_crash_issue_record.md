# Android 闪退问题记录

日期：2026-06-12  
项目：`D:\chat\agens`  
范围：记录移动端启动链路、打包配置和核心测试状态。

## 2026-06-12 修复记录

本轮已处理最可能导致“进入即闪退”的两个启动级问题：

1. 已将 `mobile/screens/*.py` 中越过顶层包的相对导入改为顶层绝对导入，例如 `from widgets.status_bar import StatusBar`、`from service.engine_adapter import EngineAdapter`。
2. 已新增仓库根入口 `main.py`，并将 `mobile/buildozer.spec` 的 `source.dir` 调整为仓库根目录 `..`，打包时显式包含 `mobile/**/*`、`src/agens_novel/**/*` 和 `config/**/*`，不再依赖 `mobile/agens_novel` / `mobile/config` symlink。
3. 已新增 `mobile/__init__.py`，让根入口可以稳定导入 `mobile.main`。
4. 已新增 `tests/unit/test_mobile_startup.py`，用 Kivy stub 验证 Buildozer 根入口可导入，防止导入链回归。

本轮验证：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\test_mobile_startup.py -q
.\.venv\Scripts\python.exe -m compileall -q main.py mobile src tests
```

结果：移动端启动导入测试通过，编译检查通过。随后全量测试通过：`445 passed in 22.09s`。

WSL Buildozer 验证：

```bash
cd /mnt/d/chat/agens/mobile
PIP_BREAK_SYSTEM_PACKAGES=1 buildozer android debug
```

结果：Buildozer 1.6.0 可启动，Android SDK/NDK 可识别，已进入 python-for-android dist 构建阶段。首次未设置 `PIP_BREAK_SYSTEM_PACKAGES=1` 时被 Ubuntu PEP 668 阻止；设置后继续。后续构建未到项目代码打包阶段，卡在下载 p4a 依赖 `SDL2_mixer-2.6.3.tar.gz`，日志和下载文件长时间无增长后手动停止。当前未生成 APK。

## 结论摘要

当前项目的桌面核心包基本健康。原先 Android/Kivy 移动端启动链路存在一个可确定的启动级导入错误，以及一个高概率 APK 内容缺失问题；这两个问题已在 2026-06-12 本轮修复中处理。仍需通过 Buildozer 实际打包和 Android 真机 logcat 验证。

原先优先级最高的问题是：

1. `mobile/main.py` 以顶层模块方式导入 `screens.game_screen`，但 `mobile/screens/*.py` 内部使用 `from ..widgets...`、`from ..service...` 这种上一级相对导入。该组合会触发 `ImportError: attempted relative import beyond top-level package`。已修复。
2. `mobile/buildozer.spec` 的 `source.dir = .` 指向 `mobile/`，但当前 `mobile/` 目录下没有 `agens_novel/` 和 `config/`。如果打包环境没有额外创建 symlink 或复制目录，APK 内会缺少核心引擎和提示词，后续会触发 `ModuleNotFoundError: No module named 'agens_novel'` 或系统提示词文件找不到。已通过根目录打包策略修复。

## 已验证状态

### 桌面核心包正常

执行结果：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

结果：原分析时为 `444 passed in 45.12s`；本轮新增移动端启动测试后为 `445 passed in 22.09s`。

执行结果：

```powershell
.\.venv\Scripts\python.exe -m agens_novel --help
```

结果：CLI 正常显示 `init/status/repl` 命令。

说明：核心 Python 包、REPL 入口和当前测试集不是闪退的直接证据点。

### 编译检查通过但不能覆盖启动导入错误

执行结果：

```powershell
$env:PYTHONPATH='src'
python -m compileall -q src tests mobile
```

结果：通过。

说明：`compileall` 只检查语法，不执行 `mobile/main.py` 的运行时导入链，因此无法发现 Kivy 入口的相对导入问题。

### 本地无法直接跑 Kivy

执行结果：

```powershell
.\.venv\Scripts\python.exe -c "import kivy"
```

结果：`ModuleNotFoundError: No module named 'kivy'`

说明：当前 Windows 虚拟环境未安装 Kivy，无法直接桌面启动 `python mobile/main.py` 做完整 UI 验证。

## P0 问题：移动端模块导入方式错误（已修复）

### 现象

`mobile/main.py` 中：

```python
from screens.game_screen import GameScreen
from screens.settings_screen import SettingsScreen
from screens.save_screen import SaveScreen
from screens.combat_screen import CombatScreen
from screens.tutorial_screen import TutorialScreen
```

这些导入会把 `screens` 当作顶层包。

但 `mobile/screens/game_screen.py` 中：

```python
from ..widgets.status_bar import StatusBar
from ..widgets.narrative_view import NarrativeView
from ..widgets.action_bar import ActionBar
from ..widgets.combat_bar import CombatBar
from ..widgets.loading_overlay import LoadingOverlay
from ..widgets.realm_card import RealmCard
from ..service.engine_adapter import EngineAdapter
```

`mobile/screens/settings_screen.py`、`save_screen.py`、`combat_screen.py` 也有同类 `..service` / `..widgets` 导入。

当前已改为：

```python
from widgets.status_bar import StatusBar
from widgets.narrative_view import NarrativeView
from widgets.action_bar import ActionBar
from widgets.combat_bar import CombatBar
from widgets.loading_overlay import LoadingOverlay
from widgets.realm_card import RealmCard
from service.engine_adapter import EngineAdapter
```

### 复现证据

由于本地没有 Kivy，我用临时 Kivy stub 只验证 Python 导入语义，结果为：

```text
ImportError: attempted relative import beyond top-level package
```

这和当前代码结构一致：`screens` 是顶层包时，`..widgets` 会越过顶层包边界。

### 影响

这是启动阶段错误。APK 打开时只要执行到 `from screens.game_screen import GameScreen`，就可能直接抛异常并退出，表现为“进入即闪退”。

### 处理结果

已采用顶层绝对导入方式，并用 `tests/unit/test_mobile_startup.py` 覆盖入口导入链。

## P0/P1 问题：APK 可能没有打入 `agens_novel` 和 `config`（已修复配置，待真机验证）

### 现象

原 `mobile/buildozer.spec`：

```ini
source.dir = .
source.include_patterns = agens_novel/**/*,config/**/*,screens/**/*,widgets/**/*,service/**/*
```

注释写明依赖 symlink：

```ini
# Extra directories to include (symlinks: agens_novel, config)
# Buildozer follows symlinks on Linux, so the engine & prompts are pulled in.
```

但当前仓库实际 `mobile/` 下只有：

```text
screens/
service/
widgets/
main.py
buildozer.spec
requirements.txt
```

未看到 `mobile/agens_novel` 或 `mobile/config`。

当前已改为从仓库根目录打包：

```ini
source.dir = ..
source.include_patterns = main.py,mobile/**/*,src/agens_novel/**/*,config/**/*
```

根目录 `main.py` 负责导入 `mobile.main`，`mobile/main.py` 会把 `mobile/`、`src/` 和项目根目录加入 `sys.path`。Android 下 `AGENS_NOVEL_ROOT` 指向项目根目录，因此 `paths.CONFIG_DIR` 能解析到打包后的 `config/`。

### 影响

移动端启动链路中 `mobile/service/engine_adapter.py` 会导入：

```python
from agens_novel.engine.game_engine import GameEngine
```

如果 APK 内没有 `agens_novel/`，会触发：

```text
ModuleNotFoundError: No module named 'agens_novel'
```

即使 `agens_novel/` 被打入，如果 `config/prompts/system/*.md` 没有被打入，首次新建游戏或执行叙事时也会在 Agent `build_prompt()` 中触发：

```text
FileNotFoundError: System prompt not found: .../config/prompts/system/world_builder.md
```

### 后续验证方向

1. 解包 APK 或检查 Buildozer build 目录，确认以下文件实际进入包内：
   - `src/agens_novel/engine/game_engine.py`
   - `src/agens_novel/agents/narrator/nodes.py`
   - `config/prompts/system/narrator.md`
   - `config/prompts/system/world_builder.md`
   - `config/prompts/system/judge.md`
   - `config/prompts/system/combat_narrator.md`
2. 真机启动后抓 logcat，确认不再出现 `ModuleNotFoundError: No module named 'agens_novel'` 或系统提示词缺失。

## P1 问题：Android 路径和运行时写目录需要真机确认

`mobile/main.py` 在 Android 上设置：

```python
os.environ["AGENS_NOVEL_ROOT"] = str(_project_root)
```

`src/agens_novel/paths.py` 由此派生：

```python
RUNTIME_DIR = PROJECT_ROOT / "runtime"
ARTIFACT_ROOT = RUNTIME_DIR / "artifacts"
CONFIG_DIR = PROJECT_ROOT / "config"
PROMPT_DIR = CONFIG_DIR / "prompts" / "system"
```

`save_manager_compat.py` 已将存档路径切到 `app.user_data_dir/saves`，这是正确方向。但 Agent 运行产物仍走 `runtime/artifacts`，在 Android 私有包目录下是否可写需要真机确认。

相关代码已有部分容错，例如 `agent_artifact_dir()` 捕获 `OSError`；但 `artifacts/store.py` 的具体写入路径仍建议用 logcat 验证。

### 建议排查方向

1. 真机启动后抓 `logcat`，查看是否有 `PermissionError`、`Read-only file system`、`FileNotFoundError`。
2. 如果产物目录不可写，移动端应像存档一样把 artifacts/logs 指向 `user_data_dir`。

## P1 问题：Buildozer 依赖链风险较高

`mobile/buildozer.spec` requirements：

```ini
python3==3.11.9,hostpython3==3.11.9,kivy==2.3.0,httpx,langgraph,langchain-core,langchain-openai,pyyaml
```

风险点：

1. `langgraph` / `langchain-core` 会带来较深的依赖树，Android/p4a 构建时容易出现 recipe、二进制 wheel 或传递依赖问题。
2. `mobile/requirements.txt` 注释提到 pydantic/pydantic-core 风险，但 spec 中并未固定传递依赖版本，也没有记录实际构建锁定结果。
3. `p4a.branch = master` 使用浮动分支，可复现性较弱，同一天不同环境构建结果可能不同。

### 建议排查方向

1. 保留完整 Buildozer 构建日志。
2. 在构建成功的机器上记录 `.buildozer/android/platform/build-*` 中实际安装的 Python 包版本。
3. 若闪退 traceback 指向依赖导入失败，再做最小依赖锁定；当前不建议先改业务代码。

## P2 问题：内置 API Key 与项目约束冲突

AGENTS 项目约束写明：

```text
API key 永远不写入磁盘 — 只从环境变量 AGNES_API_KEY 读取
```

但当前代码中存在内置 key：

```python
# mobile/main.py
_DEFAULT_KEY_B64 = "..."
os.environ["AGNES_API_KEY"] = key

# src/agens_novel/llm/client.py
_DEFAULT_KEY_B64 = "..."
_DEFAULT_KEY = base64.b64decode(_DEFAULT_KEY_B64).decode("utf-8")
```

这不一定导致闪退，但属于安全和发布风险。尤其 APK 可被反编译，base64 不是安全保护。

### 建议排查方向

移动端发布前需要重新确认产品策略：

1. 是否允许内置公共代理 key。
2. 是否改为用户自行输入 key。
3. 是否通过后端代理隐藏真实供应商 key。

## 建议的下一步排查顺序

1. 在 Linux/WSL Buildozer 环境重新打 debug APK。
2. 解包 APK 或检查 Buildozer build 目录，确认 `main.py`、`mobile/`、`src/agens_novel/`、`config/prompts/system/` 都存在。
3. 安装后立即抓真机日志：

```powershell
adb logcat -c
adb logcat | findstr /i "python kivy agens traceback exception importerror modulenotfounderror filenotfounderror"
```

4. 如果有 APK 文件，解包确认内容：

```powershell
apktool d app-debug.apk -o apk_out
```

重点找 `main.py`、`mobile/screens/`、`mobile/widgets/`、`mobile/service/`、`src/agens_novel/`、`config/prompts/system/`。

5. 在 Windows 本地安装 Kivy 或在 Linux/WSL 打包环境跑：

```powershell
cd D:\chat\agens
$env:PYTHONPATH = "src"
python mobile/main.py
```

这一步能提前暴露大部分 APK 启动前错误。

## 当前问题清单

| 优先级 | 问题 | 证据 | 影响 |
| --- | --- | --- | --- |
| P0 | `screens` 顶层导入与 `..widgets` 相对导入冲突 | 已改为顶层绝对导入，并新增启动导入测试 | 已修复 |
| P0/P1 | APK 可能缺少 `agens_novel` / `config` | 已改为仓库根目录打包，显式包含 `src/agens_novel` 和 `config` | 配置已修复，待 APK/真机验证 |
| P1 | Android runtime/artifacts 写路径未验证 | paths 指向 `AGENS_NOVEL_ROOT/runtime` | 真机上可能写入失败 |
| P1 | Buildozer 依赖链未锁定且较重 | spec 使用 langgraph/langchain/p4a master | 构建或运行时依赖导入风险 |
| P2 | 内置 API key 与约束冲突 | `main.py` 和 `llm/client.py` 均含 base64 key | 发布安全风险 |

## 本次未做事项

1. 未重新打 APK。
2. 未连接 Android 设备抓取 logcat。
3. 未解包现有 APK，因为仓库中未看到 `mobile/bin/` 或 APK 产物。
