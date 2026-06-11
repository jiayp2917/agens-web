# LangGraph 5 核心概念速查

> 这是给本项目学习者用的备忘。配合 [writer_agent.md](writer_agent.md) 阅读。

## 1. StateGraph — 状态图容器

```python
from langgraph.graph import StateGraph, START, END

g = StateGraph(WriterState)   # 创建一个图，声明其状态类型
```

`StateGraph(T)` 中 `T` 是一个 `TypedDict`,定义了图里**所有节点共享的状态形状**。

## 2. Node — 节点

```python
def my_node(state: dict) -> dict:
    return {"some_field": "new value"}   # 返回要合并进 state 的字段

g.add_node("my_node", my_node)
```

- 节点函数接收**整个 state 字典**,只读它需要的字段。
- 返回**部分 state 字典**,LangGraph 自动 merge。
- 节点可以是同步 `def` 或异步 `async def`。
- 节点**永远不应该修改入参 state**;只返回要新增/覆盖的字段。

## 3. State — 状态 Schema

```python
from typing import TypedDict, Annotated
from operator import add

class WriterState(TypedDict, total=False):
    user_input: str                      # 普通字段：后写覆盖
    messages: Annotated[list, add]       # 带 reducer 的字段：列表自动追加
```

- `total=False` 表示所有字段都是可选的(节点按需写入)。
- `Annotated[list, add]` 表示:节点返回 `{"messages": [...]}` 时,会自动 `existing + new` 拼接,而不是覆盖。
- 不带 `Annotated` 的字段:**后写覆盖**(last-write-wins)。

## 4. Edge — 边

```python
g.add_edge(START, "load_settings")          # 普通边
g.add_edge("load_settings", "build_prompt") # 节点到节点
g.add_edge("save_artifact", END)            # 节点到结束

# 条件边：根据 state 决定下一步
g.add_conditional_edges(
    "reviewer",
    lambda s: "fixer" if s["has_issues"] else "publisher",
    {"fixer": "fixer", "publisher": "publisher"},
)
```

- 普通边：固定流向。
- 条件边：传入一个**路由函数**,返回字符串,LangGraph 查表跳到对应节点。
- Writer Agent 当前**只用普通边**(流程固定)。

## 5. Checkpoint — 状态持久化

```python
from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.sqlite import SqliteSaver

# 内存版（开发）
checkpointer = MemorySaver()
graph = g.compile(checkpointer=checkpointer)

# SQLite 版（持久化）
with SqliteSaver.from_conn_string("runtime/checkpoints/writer.sqlite") as cp:
    graph = g.compile(checkpointer=cp)
    result = graph.invoke(state, config={"configurable": {"thread_id": "..."}})
```

- `thread_id` 用于区分不同的"对话/运行"。
- 同一个 `thread_id` 再次 `invoke` 时,**会从上次的状态继续**(允许断点续跑)。
- 本项目 Writer Agent 用 `MemorySaver`(单进程)。

---

## 节点间数据流总览(Writer Agent)

```
input { user_input, style_hint }
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
[save_artifact] → state += { output_path, audit_path, finished_at }
       │
       ▼
END
```

`state` 在节点之间**累积**,每一步只返回**新增字段**。LangGraph 自动 merge。
