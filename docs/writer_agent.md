# Writer Agent — 工作流详解(学习笔记)

> 这份文档对应 `src/agens_novel/agents/writer/`,目的是让读者**对照代码**理解 LangGraph 的 5 个核心概念。

## 1. 状态机全景

```
START
  │
  ▼
load_settings      读 env → model / base_url / run_id
  │
  ▼
build_prompt       读 writer.md + user_input → messages
  │
  ▼
call_agnes_llm     httpx POST → output_text
  │
  ▼
save_artifact      写 runtime/artifacts/writer/<run-id>/
  │
  ▼
END
```

4 个节点,**纯线性**。这正是我们学习时该用的图——把所有精力放在理解 LangGraph 概念上,而不是路由条件。

## 2. 五个 LangGraph 概念如何映射到代码

| 概念        | 代码位置                            | 关键代码 |
|-------------|-------------------------------------|----------|
| StateGraph  | `agents/writer/graph.py`             | `g = StateGraph(WriterState)` |
| Node        | `agents/writer/nodes.py`             | 4 个独立 `def` 函数 |
| State       | `state/schema.py`                    | `class WriterState(TypedDict, total=False)` |
| Edge        | `agents/writer/graph.py`             | `g.add_edge(START, "load_settings")` 等 |
| Checkpoint  | `agents/writer/graph.py`             | `MemorySaver()` |

## 3. 节点函数设计原则

每个节点都是**纯函数**形式:

```python
def load_settings(state: dict) -> dict:
    # 1. 读 state 中需要的字段
    # 2. 做工作(读文件、调 LLM、写文件)
    # 3. 返回**新字段**字典 — 不要修改入参 state
    return {"model": "...", "run_id": "..."}
```

**不要**做以下事情:
- ❌ `state["x"] = ...`(直接修改入参)
- ❌ 返回整个 state(只返回增量)
- ❌ 跨节点共享变量(应该走 state)

## 4. 异步节点的注意

`call_agnes_llm` 是 `async def`。LangGraph 支持:

- `g.ainvoke(state)` — 异步触发整图
- `g.invoke(state)` — 同步触发;内部会 `asyncio.run` 每个节点

如果图中**任何**节点是 `async`,整图必须用 `ainvoke` 或在 `invoke` 内自动调度(在最新版本 LangGraph 中已支持)。

## 5. 失败处理

当前 Writer Agent 用最简单的方式处理失败:

```python
async def call_agnes_llm(state):
    try:
        resp = await call_llm(...)
    except LLMError as e:
        return {"llm_error": str(e), "output_text": ""}
    return {"output_text": resp["text"], "usage": resp["usage"]}
```

下游 `save_artifact` 节点会看到 `llm_error` 字段,把它写进 audit。**图不会因为一个节点失败而中断**——状态机会继续走完。

> 这是有意的:学习阶段,我们更希望"看到一个失败 + 完整的 audit",而不是"图直接崩"。

## 6. 扩展练习

| 目标 | 步骤 |
|---|---|
| 加一个 `retry` 节点 | 在 `nodes.py` 加一个函数,在 `graph.py` 加 `add_edge("call_agnes_llm", "retry")` + `add_conditional_edges` |
| 加条件路由 | `g.add_conditional_edges("call_agnes_llm", route_after_llm, {...})` |
| 加第二个 Agent | 复制 `agents/writer/` 为 `agents/reviewer/`,改 nodes.py + graph.py + writer.md → reviewer.md |
| 持久化到 SQLite | 把 `MemorySaver()` 换成 `SqliteSaver.from_conn_string(...)` |
| 让用户改 system prompt | 加一个 `build_prompt` 节点的参数,允许传入自定义 prompt 路径 |
