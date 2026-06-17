# 项目整体架构图

本文只描述当前实际架构：Android/Kivy 单入口、A/B/C/D 单一游玩模式、三 Agent 协作、USB 真机验证。不包含已废弃的 CLI/REPL、三自由度模式、桌面点击验证路线。

## 1. 总体分层

```mermaid
flowchart TD
    User["玩家 / USB 真机验证"] --> APK["Android APK"]
    APK --> Main["mobile/main.py<br/>Kivy App 入口"]
    Main --> Screens["ScreenManager<br/>Home / CharacterCreate / Game / Death"]
    Screens --> Widgets["Widgets<br/>StatusBar / NarrativeView / ActionBar / CombatBar"]
    Screens --> Adapter["mobile/service/engine_adapter.py<br/>UI 与引擎唯一桥接"]
    Widgets --> Adapter

    Adapter --> Engine["GameEngine<br/>src/agens_novel/engine/game_engine.py<br/>唯一游戏逻辑入口"]

    Engine --> Session["GameSession<br/>session/game_session.py<br/>运行状态与 apply_delta"]
    Engine --> Rules["本地规则<br/>game/realm.py<br/>game/combat.py<br/>game/constants.py"]
    Engine --> Persistence["存档<br/>persistence/save_manager.py"]
    Engine --> TurnRunner["turn_runner.py<br/>Agent 调用器"]

    TurnRunner --> WorldBuilder["World Builder<br/>开局世界与 A/B/C"]
    TurnRunner --> Narrator["Narrator<br/>叙事 / 状态变化 / A/B/C"]
    TurnRunner --> Judge["Judge<br/>状态变化审核"]

    WorldBuilder --> LLM["llm/client.py<br/>OpenAI 兼容接口"]
    Narrator --> LLM
    Judge --> LLM

    LLM --> Provider["Agens 默认<br/>DeepSeek 可选测试<br/>其他 OpenAI 兼容模型"]

    Main --> Settings["settings_store.py<br/>settings.json / user_model.json / secrets.json"]
    Settings --> Env["进程环境变量<br/>AGNES_BASE_URL / AGNES_MODEL / AGNES_API_KEY"]
    Env --> LLM

    Main --> Audio["audio_manager.py / bgm.py<br/>BGM 开关"]
    Main --> Assets["mobile/assets<br/>图片 / 字体 / 音频"]
```

## 2. 游戏主流程

```mermaid
flowchart TD
    Home["主页"] --> NewGame["新游戏"]
    Home --> Load["读档"]
    Home --> Tutorial["教程弹窗"]
    Home --> SettingsPopup["设置弹窗"]

    NewGame --> Create["角色创建<br/>游戏名 / 角色名 / 随机角色 / 难度"]
    Create --> StartProfile["EngineAdapter.start_from_profile(profile)"]
    Load --> LoadSession["EngineAdapter.load(slot)"]

    StartProfile --> WorldCall["World Builder 生成开场"]
    WorldCall --> OpeningOK["开场叙事 + A/B/C"]
    WorldCall --> OpeningFail["模型异常 / 无 Key / 无选项"]
    OpeningFail --> FallbackAsk["弹窗：本地兜底继续 / 结束本局"]
    FallbackAsk --> LocalStory["本地预设故事<br/>当前 1 套，结构预留多套"]
    FallbackAsk --> EndRun["终止态"]

    OpeningOK --> Game["游戏主界面"]
    LocalStory --> Game
    LoadSession --> Game

    Game --> ChoiceABC["点击 A/B/C<br/>选项文本作为行动"]
    Game --> ChoiceD["底部 D 输入框<br/>玩家自由键入行动"]
    ChoiceABC --> Turn["EngineAdapter.handle_action(text)"]
    ChoiceD --> Turn

    Turn --> Dispatch["GameEngine 分发"]
    Dispatch --> Combat["本地战斗逻辑"]
    Dispatch --> Breakthrough["突破逻辑"]
    Dispatch --> LocalStoryTurn["本地故事节点推进"]
    Dispatch --> NarratorCall["Narrator 回合推演"]

    NarratorCall --> JudgeCall["Judge 审核 state_delta"]
    JudgeCall --> Apply["GameSession.apply_delta"]
    Combat --> Apply
    Breakthrough --> Apply
    LocalStoryTurn --> Apply

    Apply --> AutoStage["小层自动推进 / 死亡检查 / 飞升检查"]
    AutoStage --> Autosave["自动存档"]
    Autosave --> Game

    AutoStage --> Death["死亡终局"]
    AutoStage --> Finale["飞升成仙终局"]
```

## 3. 单回合调用链

```mermaid
sequenceDiagram
    participant UI as GameScreen / Widgets
    participant Adapter as EngineAdapter
    participant Engine as GameEngine
    participant Session as GameSession
    participant Runner as turn_runner
    participant Narrator as Narrator Agent
    participant Judge as Judge Agent
    participant LLM as LLM Client

    UI->>Adapter: handle_action(action_text)
    Adapter->>Engine: 后台线程调用 handle_action
    Engine->>Session: 读取当前状态
    Engine->>Runner: run_turn_sync("narrator", action, session)
    Runner->>Narrator: LangGraph 调用
    Narrator->>LLM: chat / stream_chat
    LLM-->>Narrator: narrative + state_update + choices
    Narrator-->>Runner: 结构化结果
    Runner-->>Engine: narrator_result

    alt 存在 state_delta
        Engine->>Runner: run_turn_sync("judge", delta, session)
        Runner->>Judge: LangGraph 审核
        Judge->>LLM: 审核请求
        LLM-->>Judge: approved / corrected_delta
        Judge-->>Engine: judge_result
    end

    Engine->>Session: apply_delta(approved_delta)
    Engine->>Engine: 小层推进 / 突破 / 死亡 / 飞升 / 自动存档
    Engine-->>Adapter: callbacks
    Adapter-->>UI: Clock.schedule_once 回到 Kivy 主线程更新 UI
```

## 4. 数据归属

```mermaid
flowchart LR
    UI["Android UI<br/>只显示与发起动作"] --> Adapter["EngineAdapter<br/>线程与回调桥接"]
    Adapter --> Engine["GameEngine<br/>唯一业务入口"]
    Engine --> Session["GameSession<br/>唯一运行状态"]
    Engine --> Rules["RealmSystem / CombatEngine<br/>本地规则判定"]
    Engine --> Save["SaveManager<br/>JSON 存读档"]

    Agent["Agent 输出<br/>叙事 + state_delta + choices"] --> Engine
    Engine --> Policy["action_delta_policy<br/>叙事/状态一致性检查"]
    Policy --> Session

    Settings["settings_store<br/>普通设置 + app-private secrets"] --> Env["AGNES_* 环境变量"]
    Env --> LLM["LLMClient"]
```

核心约束：

- Android UI 不直接修改 `GameSession`。
- 状态只能通过 `GameSession.apply_delta()`、`RealmSystem`、突破逻辑和本地战斗逻辑改变。
- 当前只开放引导模式：A/B/C 由模型基于上下文生成，D 始终是玩家输入。
- 角色创建页保留小说模式、游戏模式灰色入口，但不可点击，不进入运行逻辑。
- 模型失败或无选项时，用户确认后进入本地预设故事；本地故事仍复用 `GameSession.apply_delta()`、`RealmSystem`、存读档和现有 UI 回调。
- API key 不写入仓库、文档、日志或普通设置文件。

三层理解与代码映射：

- 交互层：`mobile/screens/*`、`mobile/widgets/*`、`EngineAdapter`，负责展示 A/B/C/D、弹窗和用户输入。
- 校验层：`Judge`、`action_delta_policy.py`、`RealmSystem`、本地故事节点条件，负责判断状态变化是否能生效。
- 状态/记忆层：`GameSession`、`SaveManager`，负责角色、世界、回合、存档和本地故事节点位置。

## 5. 模块职责速览

| 层 | 关键文件 | 职责 |
| --- | --- | --- |
| Android 入口 | `mobile/main.py` | Kivy App 启动、路径、字体、主题、设置、Screen 注册 |
| Android 页面 | `mobile/screens/*.py` | 主页、角色创建、游戏主界面、死亡/飞升终局 |
| Android 组件 | `mobile/widgets/*.py` | 状态栏、叙事区、A/B/C、D 输入栏、战斗提示 |
| UI 桥接 | `mobile/service/engine_adapter.py` | 后台线程执行引擎，回调切回 Kivy 主线程 |
| 设置 | `mobile/service/settings_store.py` | 普通设置、模型配置、app-private key、环境变量注入 |
| 引擎 | `src/agens_novel/engine/game_engine.py` | 游戏主循环、动作分发、回调、自动存档、终局 |
| 选项策略 | `src/agens_novel/engine/choices.py` | 模型选项清洗、本地兜底 A/B/C |
| 本地故事 | `src/agens_novel/engine/local_story.py` | 无模型/模型失败后的预设故事节点、A/B/C 推进、D 关键词匹配 |
| 模型结果分类 | `src/agens_novel/engine/model_result.py` | 请求失败、输出不完整、审核失败、本地兜底分类 |
| 状态一致性 | `src/agens_novel/engine/action_delta_policy.py` | 叙事声称获得/突破/接任务时校验结构化 delta |
| 会话 | `src/agens_novel/session/game_session.py` | 运行状态、状态变更、序列化 |
| 境界 | `src/agens_novel/game/realm.py` | 小层推进、突破资格、突破概率、飞升终态 |
| 战斗 | `src/agens_novel/game/combat.py` | 本地战斗状态机 |
| 存档 | `src/agens_novel/persistence/save_manager.py` | JSON 多槽位存档 |
| Agent 调用 | `src/agens_novel/engine/turn_runner.py` | 同步执行 LangGraph Agent |
| Agent | `src/agens_novel/agents/*` | World Builder / Narrator / Judge |
| LLM | `src/agens_novel/llm/client.py` | OpenAI 兼容 HTTP 调用 |

## 6. 验证与交付链路

```mermaid
flowchart TD
    Code["源码修改"] --> Tests["本地测试<br/>compileall / pytest"]
    Tests --> Build["Buildozer 打包 APK"]
    Build --> PlanDir["输出到 D:\\chat\\plan"]
    PlanDir --> Install["USB + ADB 安装到手机"]
    Install --> PhoneRun["手机真实操作验证"]
    PhoneRun --> Evidence["ADB 截图 / logcat / 问题记录"]
    Evidence --> Fix["确认后修复"]
```

固定边界：

- 产品验证只走 Android APK + USB 真机。
- 不再使用 Windows 桌面 Kivy 真实点击方案。
- 默认模型仍是 Agens；DeepSeek 是可选测试项。
- `D:\chat\plan` 是外部 APK 和证据目录，不属于仓库内容。
