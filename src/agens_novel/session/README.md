# session/

游戏会话管理。`GameSession` 是运行时状态持有者。

## 关键文件

- `game_session.py` — `GameSession` 类：角色属性、世界状态、背包、装备、回合计数等。

## 主要 API

| 名称 | 签名 | 说明 |
|------|------|------|
| `GameSession()` | 构造 | 默认值初始化（hp=100, mp=50, realm="练气" 等） |
| `session.apply_delta(delta)` | `dict -> None` | 接受 narrator / world_builder 输出，应用状态变更（含防御性守卫） |
| `session.to_save_dict()` | `() -> dict` | 序列化为可 JSON 化的 dict（存档） |
| `GameSession.from_save_dict(data)` | `dict -> GameSession` | 反序列化（读档） |
| 属性：`char_name` / `realm` / `hp` / `mp` / `inventory` / `techniques` / `combat` / `turn_count` 等 | | 直接读写 |

## 测试位置

- `tests/unit/session/test_apply_delta_guards.py` — `apply_delta` 防御性守卫（白名单、类型拒绝、值钳制）
- `tests/unit/session/test_session_serialization.py` — `to_save_dict` / `from_save_dict` 往返

## 注意事项

- **直接属性读写**：Web 服务层可能直接读 `session.realm` 等属性（用于显示）。
- **`apply_delta` 是有守卫的**：传入的 realm 不在 `REALM_ORDER` 中会被忽略；非 bool 的 `game_over` 会被拒绝。
- **可序列化状态**：session 字段必须可 JSON 序列化，避免存 datetime / custom class。
