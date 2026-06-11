# Writer Agent

A minimal LangGraph Agent that produces a short prose snippet from a user's
request. This directory is the **canonical learning template** for adding
new Agents to the project.

## How to copy this for a new Agent

```bash
# 1. Copy the directory
cp -r src/agens_novel/agents/writer src/agens_novel/agents/reviewer

# 2. Edit src/agens_novel/agents/reviewer/__init__.py
#    - Change the import to point at the new graph module.
#    - Change build_writer_graph() to build_reviewer_graph().

# 3. Replace nodes.py with your own node functions.
# 4. Replace graph.py with your StateGraph assembly.
# 5. Create config/prompts/system/reviewer.md with the new system prompt.
# 6. Wire it up in cli.py.
```

## State machine (4 nodes, linear)

```
START -> load_settings -> build_prompt -> call_agnes_llm -> save_artifact -> END
```

| Node              | Reads from state     | Writes to state                       | Calls LLM? |
|-------------------|----------------------|----------------------------------------|------------|
| `load_settings`   | env vars             | `model`, `base_url`, `api_key_set`, `run_id`, `started_at` | No         |
| `build_prompt`    | `user_input`, `style_hint` | `system_message`, `user_message`, `messages`     | No         |
| `call_agnes_llm`  | `messages`, `model`  | `output_text`, `usage`, `elapsed_ms`, `llm_error`  | Yes        |
| `save_artifact`   | `output_text`, `run_id` | `output_path`, `audit_path`, `finished_at`     | No         |

## How LangGraph concepts are exercised

| Concept       | File                                      | Lines / function |
|---------------|-------------------------------------------|-------------------|
| `StateGraph`  | `graph.py`                                | `g = StateGraph(WriterState)` |
| `Node`        | `nodes.py`                                | `load_settings`, `build_prompt`, `call_agnes_llm`, `save_artifact` |
| `State`       | `state/schema.py`                         | `class WriterState(TypedDict, total=False)` |
| `Edge`        | `graph.py`                                | `g.add_edge(START, "load_settings")` etc. |
| `Checkpoint`  | `graph.py`                                | `MemorySaver()` in `build_writer_graph` |

## Run

```bash
$env:AGNES_API_KEY = "<your key>"
python -m agens_novel.cli run --input "用 50 字写一段都市修仙的开头,主角叫许满"
```

Output goes to `runtime/artifacts/writer/<run-id>/output.md`.
