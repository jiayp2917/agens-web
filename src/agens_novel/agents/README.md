# agents/

三个 LangGraph Agent 协作：Narrator（叙事）、World Builder（开局）、Judge（审核）。

## 子目录

| Agent | 目录 | 系统提示词 | 职责 |
|-------|------|-----------|------|
| **Narrator** | `narrator/` | `config/prompts/system/narrator.md` | 生成每回合叙事、状态变化、A/B/C 选项 |
| **World Builder** | `world_builder/` | `config/prompts/system/world_builder.md` | 初始化角色、世界开局、初始选项 |
| **Judge** | `judge/` | `config/prompts/system/judge.md` | 审核状态变化与世界逻辑是否合理 |

## 每个 Agent 目录结构

```
agents/<name>/
├── __init__.py
├── graph.py        # LangGraph 节点编排（START → 节点 → END）
└── nodes.py        # LLM 调用 + 响应解析（含 _parse_xxx_output）
```

## 协作流程

```
World Builder  ← 启动新游戏
       ↓
    GameSession 已初始化
       ↓
Narrator  ← 玩家每回合输入
       ↓
Judge    ← 审核 narrator 输出
       ↓
GameEngine.apply_delta  ← 应用审核后的 delta
```

## 主要 API

| 名称 | 签名 | 说明 |
|------|------|------|
| `run_turn_sync(agent_name, input, session)` | `(str, str, GameSession) -> dict` | 调用指定 Agent，详见 `engine/turn_runner.py` |
| `_parse_narrator_output(text)` | `str -> (narrative, delta, choices)` | Narrator 解析器，提取 `<state_update>` 和 `<choices>` |
| `build_graph_<agent>()` | `() -> CompiledGraph` | LangGraph 编译图 |

## 测试位置

- `tests/unit/agents/test_narrator_parse.py` — Narrator 输出解析（含 `<state_update>` 过滤）
- `tests/unit/agents/test_judge.py` / `test_judge_parse.py` — Judge 行为与解析
- `tests/unit/agents/test_world_builder_parse.py` — World Builder 解析

## 注意事项

- **提示词与代码同步改**：`config/prompts/system/<agent>.md` 改动时，相应 `nodes.py` 解析逻辑可能也要调整。
- **输出格式约束**：Narrator 必须用 `<state_update>` 块输出 JSON delta，否则解析器返回空 delta。
- **Judge 默认 NOT approve**：异常时默认 `approved=False`（安全默认，不应用 delta）。
