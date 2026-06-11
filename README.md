# agens-novel (langgraph-novel)

> **学习项目**:用 LangGraph 构建单个 Agent 的最小可运行闭环,作为后续多 Agent 系统的开发模板。

## 重要安全提示

🔒 **API key 永远不要写入任何文件**。本项目只从环境变量读取 `AGNES_API_KEY`、`AGNES_BASE_URL`、`AGNES_MODEL`,并通过 `SecretRedactor` 在日志/输出中屏蔽任何形如 `sk-...` 的字符串。

## 快速开始

```powershell
cd D:\2917\agens\langgraph-novel

# 1. 创建虚拟环境并安装依赖
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"

# 2. 注入环境变量(只在当前 shell 有效)
$env:AGNES_BASE_URL = "https://apihub.agnes-ai.com/v1"
$env:AGNES_MODEL    = "agnes-2.0-flash"
$env:AGNES_API_KEY  = "<你的 key>"

# 3. 初始化 runtime 目录
python -m agens_novel.cli init

# 4. 跑 Writer Agent
python -m agens_novel.cli run --input "用 50 字写一段都市修仙的开头,主角叫许满"

# 5. 查看最近一次运行
python -m agens_novel.cli status
```

或者用封装好的 PowerShell 脚本(自动清理 env):

```powershell
.\scripts\run_with_key.ps1 -ApiKey "<你的 key>" -- run --input "..."
```

## 当前进度

- [x] 项目骨架 + pyproject + .env.example + .gitignore
- [ ] 基础设施(settings / paths / logging)
- [ ] API 客户端(httpx + SSE)
- [ ] WriterState Schema
- [ ] Writer Agent 4 节点
- [ ] CLI(init / run / status)
- [ ] 测试
- [ ] 学习笔记

## 项目结构

```
langgraph-novel/
├── config/prompts/system/    # Agent 系统提示词(Markdown)
├── src/agens_novel/
│   ├── llm/                  # OpenAI 兼容 httpx 客户端 + SSE
│   ├── state/                # TypedDict State Schema
│   ├── graph/                # StateGraph 装配
│   ├── agents/writer/        # ★ Writer Agent: 4 节点
│   └── artifacts/            # runtime 产物管理
├── runtime/                  # 全部产物落这里(gitignored)
├── tests/                    # 单元 + 节点 + 集成
├── scripts/                  # run_with_key.ps1 等
└── docs/                     # 学习笔记
```

详见 [docs/writer_agent.md](docs/writer_agent.md)。
