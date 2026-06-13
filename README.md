# agens-novel

> **文字修仙模拟器** — AI 驱动的互动叙事，基于 LangGraph 多 Agent 架构。
> 支持终端 REPL（Rich）和 Android APK（Kivy/Buildozer）。

## 安全提示

🔒 **API key 永远不要写入任何文件。** 本项目只从环境变量读取 `AGNES_API_KEY`、`AGNES_BASE_URL`、`AGNES_MODEL`，并通过 `SecretRedactor` 在日志/输出中屏蔽任何形如 `sk-...` 的字符串。

---

## 快速开始

### 1. 安装依赖

```powershell
cd D:\chat\agens
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
```

### 2. 设置环境变量

在当前终端中注入（关闭终端后失效）：

```powershell
$env:AGNES_BASE_URL = "https://apihub.agnes-ai.com/v1"
$env:AGNES_MODEL    = "agnes-2.0-flash"
$env:AGNES_API_KEY  = "<你的 key>"
$env:PYTHONPATH     = "src"
```

### 3. 启动模拟器

```powershell
python -m agens_novel repl
```

你会看到欢迎面板：

```
┌─────────────────────────────────────────────────────┐
│ 文字修仙 - AI 驱动的修仙世界模拟器                      │
│ 输入行动探索世界，或用命令管理游戏。                       │
│ 输入 /new 开始新游戏，/help 查看所有命令。               │
└─────────────────────────────────────────────────────┘
修仙>
```

---

## 玩法

### 创建角色

```
修仙> /new 我叫许满，火灵根，出身农家
```

AI 会生成你的初始角色（境界、灵根、HP/MP）、起始地点和开场叙事。

### 自由行动

输入任何文字作为你的行动：

```
修仙> 修炼吐纳功法
修仙> 去后山采药
修仙> 和陈师兄切磋
```

AI 叙述者会描述你的行动后果，并更新状态（HP/MP/经验等）。

### 境界突破

```
修仙> /breakthrough
```

9 重境界（练气 → 筑基 → 金丹 → 元婴 → 化神 → 合体 → 大乘 → 渡劫 → 飞升），突破成功率和灵根品质相关。

### 战斗系统

触发战斗后可用命令：

```
修仙> /attack              # 普通攻击
修仙> /technique 引剑诀     # 使用功法
修仙> /item 回灵丹          # 使用丹药
修仙> /defend              # 防御
修仙> /flee                # 逃跑
```

### 游戏命令

| 命令 | 说明 |
|------|------|
| `/new` | 开始新游戏 |
| `/status` | 显示角色状态 |
| `/inv` | 显示背包 |
| `/skills` | 显示功法 |
| `/map` | 显示已探索地点 |
| `/quest` | 显示当前任务 |
| `/log` | 显示最近回合 |
| `/breakthrough` | 尝试突破境界 |
| `/attack` | 战斗：普通攻击 |
| `/technique <名>` | 战斗：使用功法 |
| `/item <名>` | 战斗：使用丹药 |
| `/defend` | 战斗：防御 |
| `/flee` | 战斗：逃跑 |
| `/expand` | 请求世界扩展 |
| `/save` | 保存进度 |
| `/load` | 加载存档 |
| `/reset` | 重置游戏 |
| `/config` | 显示配置 |
| `/history` | 命令历史 |
| `/clear` | 清屏 |
| `/help` | 显示所有命令 |

---

## 架构

```
玩家输入
    │
    ├── /new → [World Builder] → 初始化角色 + 世界
    │
    ├── 行动 → [Narrator] → 叙事 + 状态变化
    │              │
    │              ▼
    │         [Judge] → 审核通过/修正
    │              │
    │              ▼
    │         更新状态 → 显示 → 自动存档
    │
    ├── /breakthrough → [RealmSystem] → 突破判定
    │
    ├── /attack /defend ... → [CombatEngine] → 战斗回合
    │
    └── /save /load /status → 存档管理
```

- **Narrator Agent**: 天道叙述者，根据玩家行动生成叙事和状态变化
- **World Builder Agent**: 世界设计师，创建角色和世界内容
- **Judge Agent**: 规则仲裁者，审核状态变化的合理性
- **RealmSystem**: 9 境界突破 + 8 灵根加成 + 飞升大结局
- **CombatEngine**: 回合制战斗（攻击/功法/丹药/防御/逃跑）

## 移动端

可通过 Buildozer 打包为 Android APK（arm64-v8a，API 34）：

```powershell
/build-apk              # 增量打包
/build-apk --clean      # 清缓存重打包
```

详细说明见 [`.claude/skills/build-apk/SKILL.md`](.claude/skills/build-apk/SKILL.md)。

## 测试

```powershell
python -m pytest -q                          # 全部测试（445 passed）
python -m pytest tests/unit/test_destructive.py -v  # 破坏性测试
python -m pytest tests/integration/ -v       # 真 LLM 集成测试（需 AGNES_API_KEY）
```
