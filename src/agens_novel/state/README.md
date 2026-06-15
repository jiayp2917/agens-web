# state/

游戏状态定义：数据模型与 reducer 规则。

## 关键文件

- `game_schema.py` — Typed 数据模型（`Character` / `World` / `Meta` 三块）。
- `reducers.py` — LangGraph `Annotated` reducer：`last_wins` / `apply_combat_delta` / `Append` / `ReplaceList`。

## 与 session 的区别

- `state/` 是**类型化 schema 定义**（LangGraph `TypedDict` 兼容）。
- `session/` 是**运行时 mutation 入口**（`GameSession` 提供 `apply_delta` 等高层 API）。
- 二者协作：state 定义"形状"，session 提供"写入路径"。

## 主要 API

| 名称 | 签名 | 说明 |
|------|------|------|
| `last_wins(existing, new)` | `(list, list) -> list` | 列表 reducer：新列表完全替换旧列表，空列表视为"无更新" |
| `apply_combat_delta(existing, new)` | `(dict \| None, dict) -> dict` | 战斗状态 reducer：`_reset=True` 清空，否则新 dict 替换旧 dict |
| `Append` / `ReplaceList` | `Annotated` 别名 | 给 LangGraph state 字段打标记，决定 reducer 选择 |

## 测试位置

- `tests/unit/state/test_state_reducers.py` — 合并后的 reducer 测试（`last_wins` + `apply_combat_delta`）
- `tests/unit/state/test_game_schema.py` — 数据模型测试

## 注意事项

- **不要直接改 schema**：所有字段都在 `game_schema.py` 集中定义，session 中的属性必须与之对应。
- **reducer 必须幂等**：同一 delta 多次 apply 结果相同。
- **保留可序列化**：state 字段必须能被 msgpack 序列化（不要存 callable、datetime 对象等）。
