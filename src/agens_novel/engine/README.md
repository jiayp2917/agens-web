# engine/

游戏引擎核心。负责回合执行、UI 文本渲染、流式回调上下文。

## 关键文件

- `game_engine.py` — 唯一游戏逻辑入口（`GameEngine`）。Web 后端通过服务层调用。
- `turn_runner.py` — LangGraph Agent 调用器，每回合执行 `run_turn_sync`。
- `render.py` — UI 无关的文本格式化（角色状态、物品列表等）。
- `_stream_context.py` — Thread-local 流式回调上下文，**不要**写入 LangGraph state（msgpack 无法序列化 callable）。

## 主要 API

| 名称 | 签名 | 说明 |
|------|------|------|
| `GameEngine.new_game(char_name)` | `str -> None` | 启动新游戏，初始化 session 并触发 world_builder |
| `GameEngine.handle_action(input)` | `str -> None` | 处理玩家 A/B/C/D 行动 |
| `GameEngine.attempt_breakthrough()` | `() -> None` | 触发境界突破 |
| `GameEngine.save(name)` / `load(name)` | `str -> bool` | 存档 / 读档 |
| `GameEngine.get_status()` 等 | `() -> str` | 查询状态文本（UI 渲染用） |
| `run_turn_sync(agent, input, session)` | `-> dict` | 调用 LLM Agent（LangGraph 节点入口） |

## 测试位置

- `tests/unit/engine/test_game_engine_setup.py` — 初始化、查询、重置
- `tests/unit/engine/test_game_engine_turn.py` — 回合执行、阶段推进、突破、感悟门控
- `tests/unit/engine/test_game_engine_state.py` — 存档读档、飞升终局
- `tests/unit/engine/test_stream_context.py` — 流式回调上下文
- `tests/unit/engine/test_engine_render.py` — 文本渲染

## 注意事项

- **唯一入口**：`GameEngine` 是 UI 唯一调用点，UI 不直接改 `GameSession`。
- **回调不写入 state**：流式回调通过 `_stream_context` 传递，不要塞进 LangGraph state。
- **LangGraph state 字段必须 msgpack 可序列化**：所有 dict / list / int / str / bool / float；不可存 callable、file handle、threading.Lock 等。
