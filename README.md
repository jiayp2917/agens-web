# agens-novel

> **AI 小说写作助手** — 基于 LangGraph 的多 Agent 流水线，支持自由对话和逐步可控的小说生成。

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

### 3. 启动交互式 REPL

```powershell
python -m agens_novel repl
```

你会看到欢迎面板：

```
+---------------------------------------------------------+
| agens-novel - multi-agent novel REPL                    |
| Chat freely, or use /plan, /write, /review, /edit for  |
| step-by-step pipeline. Type /help for commands.         |
+---------------------------------------------------------+
agens>
```

### 4. 或者用 PowerShell 脚本（自动清理环境变量）

```powershell
.\scripts\run_with_key.ps1 -ApiKey "<你的 key>" -- repl
```

---

## 使用方式

### 模式一：自由对话（默认）

输入任何非命令文字，都会和 Chat Agent 对话：

```
agens> 你好
你好！我是 Agens，小说写作助手。
我可以帮你构思情节、讨论风格，也可以直接开始写作流水线。
输入 /help 查看所有命令。

agens> 什么是 LangGraph？
LangGraph 是一个用于构建多步骤 AI 工作流的框架...
```

### 模式二：智能检测写作意图

当你输入包含写作意图的文字（如"写一段""生成""小说"等关键词），系统会弹出确认选项：

```
agens> 用50字写一段都市修仙开头，主角叫许满

  Writing request detected. How would you like to proceed?
    1. Step-by-step pipeline (with confirmations) (Recommended)
    2. Run full pipeline automatically
    3. Cancel, just chat
  select> _
```

- **选 1** → 逐步模式，每一步确认后才继续
- **选 2** → 一键跑完整个流水线
- **选 3** → 取消，回到对话

### 模式三：逐步流水线（每步确认）

用斜杠命令手动控制每个阶段：

```
agens> /plan 用50字写一段都市修仙开头，主角叫许满
```

系统跑 Planner，显示大纲，然后问：

```
  Outline generated. What next?
    1. Continue to Writer (write draft) (Recommended)
    2. Cancel pipeline
  select> 1
```

继续 Writer → Reviewer → Editor，每步都会弹窗确认：

```
agens> /write      ← 跑 Writer（需要先 /plan）
agens> /review     ← 跑 Reviewer（需要先 /write）
agens> /edit        ← 跑 Editor（需要先 /write）
```

每步完成后你会看到结果，并选择下一步（继续/重来/取消）。

### 模式四：一键完整流水线

```
agens> /run 用50字写一段都市修仙开头，主角叫许满
```

自动跑完 Planner → Writer → Reviewer → Editor，无确认弹窗。

---

## 全部命令

| 命令 | 说明 |
|------|------|
| `/help` | 显示所有命令 |
| `/agents` | 显示多 Agent 流水线说明 |
| `/config` | 显示当前配置（API key 已脱敏） |
| `/status` | 显示最近一次运行结果 |
| `/history` | 显示本次会话的命令历史 |
| `/step` | 显示当前流水线状态（哪步完成、下一步是什么） |
| `/plan <请求>` | 跑 Planner 生成大纲，存入会话 |
| `/write` | 跑 Writer 写初稿（需要先 /plan） |
| `/review` | 跑 Reviewer 打分（需要先 /write） |
| `/edit` | 跑 Editor 产出终稿（需要先 /write） |
| `/run <请求>` | 一键跑完整流水线（无确认） |
| `/reset` | 清空当前流水线会话 |
| `/clear` | 清屏 |
| `/exit` 或 `:q` | 退出 REPL |

输入任何非斜杠文字 → Chat Agent 对话。

---

## 多 Agent 流水线

```
用户请求
   │
   ▼
┌──────────┐     ┌──────────┐     ┌──────────┐     ┌──────────┐
│ Planner  │ ──► │  Writer  │ ──► │ Reviewer │ ──► │  Editor  │
│ 生成大纲  │     │ 写初稿    │     │ 打分+反馈 │     │ 修订终稿  │
└──────────┘     └──────────┘     └──────────┘     └──────────┘
                                        │
                                        │ 分数 < 7
                                        ▼
                                  回到 Writer 重写
                                  （最多 3 轮）
```

| Agent | 职责 | 温度 |
|-------|------|------|
| **Planner** | 将自由文字拆解为 3-6 条大纲 bullet + 风格计划 | 0.5 |
| **Writer** | 根据大纲写 100-500 字初稿 | 0.7 |
| **Reviewer** | 对初稿打 0-10 分，给出修改意见（JSON 格式） | 0.2 |
| **Editor** | 根据审稿意见修订初稿，产出终稿 | 0.4 |
| **Chat** | 自由对话，讨论创意、回答问题 | 0.7 |

---

## 单次命令（非交互）

不进 REPL，直接在命令行跑：

```powershell
# 初始化 runtime 目录
python -m agens_novel init

# 单次跑 Writer Agent（旧模式，仅 Writer）
python -m agens_novel run --input "用50字写一段都市修仙开头"

# 查看最近运行
python -m agens_novel status
```

---

## 项目结构

```
agens-novel/
├── config/prompts/system/       # Agent 系统提示词
│   ├── chat.md                  # Chat Agent
│   ├── planner.md               # Planner Agent
│   ├── writer.md                # Writer Agent
│   ├── reviewer.md              # Reviewer Agent
│   └── editor.md                # Editor Agent
├── src/agens_novel/
│   ├── agents/
│   │   ├── chat/                # Chat Agent（自由对话）
│   │   ├── planner/             # Planner Agent
│   │   ├── writer/              # Writer Agent
│   │   ├── reviewer/            # Reviewer Agent
│   │   └── editor/              # Editor Agent
│   ├── orchestrator/            # 多 Agent 编排器
│   ├── repl/                    # 交互式 REPL
│   │   ├── commands.py          # 命令解析 + 意图检测
│   │   ├── loop.py              # REPL 主循环
│   │   ├── pipeline_session.py  # 逐步流水线会话
│   │   └── stage_runner.py      # 单阶段执行器
│   ├── llm/                     # LLM 客户端（httpx + SSE + 重试）
│   ├── state/                   # TypedDict 状态 Schema
│   ├── artifacts/               # runtime 产物管理
│   └── cli.py                   # Typer CLI 入口
├── runtime/                     # 产物输出目录（gitignored）
├── tests/                       # 125 个测试
├── scripts/                     # 辅助脚本
└── docs/                        # 文档
```

---

## 开发

```powershell
# 安装开发依赖
pip install -e ".[dev]"

# 跑测试（125 个）
python -m pytest -q

# 代码检查
ruff check src tests

# 格式化
ruff format src tests
```

---

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `AGNES_API_KEY` | （必填） | API 密钥 |
| `AGNES_BASE_URL` | `https://apihub.agnes-ai.com/v1` | API 端点 |
| `AGNES_MODEL` | `agnes-2.0-flash` | 模型名称 |
| `PYTHONPATH` | `src` | Python 模块搜索路径 |
