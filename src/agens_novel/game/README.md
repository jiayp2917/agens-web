# game/

游戏规则定义：境界、战斗、常量。

## 关键文件

- `realm.py` — 境界系统：境界顺序、阶段推进（`try_advance_stage`）、突破规则、感悟门槛。
- `combat.py` — 回合制战斗：开始战斗（`start_combat`）、玩家回合、敌人回合、胜负判定。
- `constants.py` — 游戏常量：`REALM_ORDER`（境界顺序）、境界 stage 上限、突破所需经验 / 感悟阈值。

## 主要 API

| 名称 | 签名 | 说明 |
|------|------|------|
| `RealmSystem.try_advance_stage(session)` | `-> dict \| None` | 尝试在当前境界内推进一个小阶段，消耗经验；达到上限返回 None |
| `CombatEngine.start_combat(session, enemy)` | `-> dict` | 初始化战斗状态 |
| `CombatEngine.player_action(session, action)` | `-> dict` | 处理玩家战斗行动 |
| `REALM_ORDER` | `list[str]` | 境界顺序：练气 → 筑基 → 金丹 → 元婴 → 化神 → 合体 → 大乘 → 渡劫 → 飞升 |

## 测试位置

- `tests/unit/game/test_realm.py` / `test_realm_full.py` — 境界系统
- `tests/unit/game/test_combat.py` — 战斗系统
- `tests/unit/game/test_constants.py` — 常量

## 注意事项

- **境界顺序不可改**：`REALM_ORDER` 是 UI 契约的一部分，删除境界会破坏终局文本。
- **战斗不走 LLM**：战斗是纯逻辑，由 `CombatEngine` 处理；LLM 只负责叙事。
- **纯 `random.random()` 用于概率**：境界突破、战斗暴击等用 `random.random()` 与阈值比较。
