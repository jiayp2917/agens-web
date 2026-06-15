# agens-novel

Android-only 文字修仙模拟器。产品入口是 Kivy/Buildozer 移动端，核心玩法由 LangGraph Agent、GameEngine、Session、存档和规则系统驱动。

## 启动

```powershell
cd D:\chat\agens
.\.venv311\Scripts\python.exe mobile\main.py
```

开发测试环境：

```powershell
cd D:\chat\agens
python -m venv .venv
.\.venv\Scripts\activate
pip install -e ".[dev]"
```

可选模型配置只通过当前进程环境变量或应用内设置注入，不把密钥写入仓库：

```powershell
$env:AGNES_BASE_URL = "https://apihub.agnes-ai.com/v1"
$env:AGNES_MODEL    = "agnes-2.0-flash"
$env:AGNES_API_KEY  = "<your key>"
```

## ZIP 迁移

如果 GitHub 推送不可用，可以用 ZIP 迁移到另一台电脑测试。不要直接压缩整个 `D:\chat\agens` 工作目录；推荐生成干净源码包：

```powershell
cd D:\chat\agens
git archive --format=zip --output D:\chat\agens-transfer.zip HEAD
```

新电脑上的环境重建、启动和验证步骤见 [docs/ZIP_TRANSFER.md](docs/ZIP_TRANSFER.md)。

## 当前流程

1. 主页显示水墨背景、BGM 开关、新游戏、读档、教程、设置、退出。
2. 新游戏进入角色创建，填写游戏名称、角色名，选择天赋、灵根、家世、难度，可随机基础属性。
3. 开局优先调用 World Builder 生成天道背景和 A/B/C 三个上下文选项；失败时显示“天道紊乱”兜底提示。
4. 游戏主界面顶部显示角色状态，中部展示叙事和 A/B/C，底部固定 D 自由输入。
5. 存档、读档、状态、背包、装备、功法、任务、突破、设置都收在“更多”工具弹窗，不常驻挤占叙事空间。
6. 战斗不提供常驻按钮，玩家通过 D 输入框键入攻击、防御、逃跑、施展功法等自然语言行动。
7. 死亡进入重开/读档/主页流程；飞升进入独立“飞升成仙”终局。

## 关键模块

- `mobile/main.py`：Android/Kivy 应用入口。
- `mobile/screens/`：主页、游戏页、角色创建、死亡/飞升页。
- `mobile/widgets/`：输入栏、叙事区、状态栏、战斗提示、加载层。
- `mobile/assets/images/`：沉浸水墨背景、宣纸纹理、死亡/飞升终局背景。
- `mobile/service/`：Kivy 与核心引擎之间的适配层。
- `src/agens_novel/engine/game_engine.py`：唯一游戏逻辑入口。
- `src/agens_novel/session/game_session.py`：游戏会话状态和序列化。
- `src/agens_novel/persistence/save_manager.py`：存读档。
- `src/agens_novel/engine/turn_runner.py`：Agent 调用器。
- `src/agens_novel/game/`：境界、战斗、常量等规则。
- `config/prompts/system/`：Narrator、World Builder、Judge 系统提示词。

## 测试

```powershell
.\.venv\Scripts\python.exe -m compileall -q src tests mobile\main.py mobile\audio_manager.py mobile\screens mobile\widgets mobile\service demo_full_flow.py
.\.venv\Scripts\python.exe -m pytest -q
```

## 打包

```powershell
/build-apk
/build-apk --clean
/build-apk --release
```

Buildozer 配置在 `mobile/buildozer.spec`，产品方向固定为 Android 竖屏。
