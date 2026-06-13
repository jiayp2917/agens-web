# LangGraph 4-node 模式速查

> 修仙模拟器所有 Agent 共用的 4 节点线性图模式。配合 [agents.md](agents.md) 阅读。

## 1. StateGraph — 状态图容器

```python
from langgraph.graph import StateGraph, START, END

g = StateGraph(GameState)   # 创建一个图，声明其状态类型
```

`StateGraph(T)` 中 `T` 是一个 `TypedDict`，定义了图里**所有节点共享的状态形状**。
三个 Agent（Narrator / World Builder / Judge）都使用 `GameState`。

## 2. Node — 节点

```python
def my_node(state: dict) -> dict:
    return {"some_field": "new value"}   # 返回要合并进 state 的字段

g.add_node("my_node", my_node)
```

- 节点函数接收**整个 state 字典**，只读它需要的字段。
- 返回**部分 state 字典**，LangGraph 自动 merge。
- 节点可以是同步 `def` 或异步 `async def`。
- 节点**永远不应该修改入参 state**；只返回要新增/覆盖的字段。

## 3. State — 状态 Schema

```python
from typing import TypedDict, Annotated
from operator import add

class GameState(TypedDict, total=False):
    user_input: str                      # 普通字段：后写覆盖
    messages: Annotated[list, add]       # 带 reducer 的字段：列表自动追加
    narrative: str
    state_delta: dict
```

- `total=False` 表示所有字段都是可选的（节点按需写入）。
- `Annotated[list, add]` 表示节点返回 `{"messages": [...]}` 时，会自动 `existing + new` 拼接，而不是覆盖。
- 不带 `Annotated` 的字段：**后写覆盖**（last-write-wins）。

## 4. Edge — 边

```python
g.add_edge(START, "load_settings")          # 普通边
g.add_edge("load_settings", "build_prompt") # 节点到节点
g.add_edge("save_artifact", END)            # 节点到结束
```

- 普通边：固定流向。
- 本项目三个 Agent 都**只用普通边**（纯线性 4 节点链）。

## 5. Checkpoint — 状态持久化

```python
from langgraph.checkpoint.memory import MemorySaver

checkpointer = MemorySaver()
graph = g.compile(checkpointer=checkpointer)
result = graph.invoke(state, config={"configurable": {"thread_id": "..."}})
```

- `thread_id` 用于区分不同的"对话/运行"。
- 本项目用 `MemorySaver`（单进程），存档功能由 `save_manager.py` 独立实现。

---

## 节点间数据流总览（Narrator Agent 示例）

```
input { user_input, game_state_json, chat_history }
       │
       ▼
[load_settings] → state += { model, base_url, api_key_set, run_id, started_at }
       │
       ▼
[build_prompt]  → state += { system_message, user_message, messages }
       │
       ▼
[call_agnes_llm]→ state += { output_text, usage, elapsed_ms, llm_error? }
       │
       ▼
[save_artifact] → state += { narrative, state_delta, choices, output_path, audit_path, finished_at }
       │
       ▼
END
```

`state` 在节点之间**累积**，每一步只返回**新增字段**。LangGraph 自动 merge。

---

## 三 Agent 对比

| Agent | 温度 | max_tokens | 输入 | 关键输出 |
|-------|------|------------|------|----------|
| Narrator | 0.8 | 1536 | 游戏状态 + 玩家行动 + 历史叙事 | `narrative` + `state_delta` + `choices` |
| World Builder | 0.6 | 1024 | 角色设定 + 生成类型 | `generated_data` + `opening_narrative` |
| Judge | 0.2 | 512 | 游戏状态 + 叙事 + 建议delta | `approved` + `corrected_delta` + `score` |
