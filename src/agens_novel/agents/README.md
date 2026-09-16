# agents/

两个 Agent 通过项目内 `SequentialAgentGraph` 协作：Narrator（叙事）、World Builder（开局）。
权威状态由规则引擎结算（`engine/turn_rules.py` 的 `settle_turn_outcome`），Agent 不拥有状态结算权。

## 子目录

| Agent | 目录 | 系统提示词 | 职责 |
|-------|------|-----------|------|
| **Narrator** | `narrator/` | `config/prompts/system/narrator.md` | 生成每回合短叙事与 A/B/C/D 选项建议；`<state_update>` 仅作传输契约与诊断，内容不落库 |
| **World Builder** | `world_builder/` | `config/prompts/system/world_builder.md` | 初始化角色、世界开局、初始 A/B/C/D 选项建议 |

## 每个 Agent 目录结构

```
agents/<name>/
├── __init__.py
├── graph.py        # SequentialAgentGraph 节点编排
└── nodes.py        # LLM 调用 + 响应解析（含 _parse_xxx_output）
```

## 协作流程

```
World Builder  ← 启动新游戏
       ↓
    GameSession 已初始化
       ↓
规则引擎 settle_turn_outcome  ← 玩家每回合输入（先结算权威结果）
       ↓
Narrator  ← 基于规则结果生成叙事与 A/B/C/D 选项
       ↓
GameEngine._rule_only_delta → GameSession.apply_delta  ← 只应用规则结果
```

普通回合的权威顺序是 `ChoiceIntentV1 -> RuleTurnOutcomeV1 -> NarratorEnvelopeV1 -> persistence`。
模型输出的 `state_update` 会被解析为诊断（记 `model_state_update_ignored`），但不能改变任何权威字段。

## 主要 API

| 名称 | 签名 | 说明 |
|------|------|------|
| `run_turn_sync(agent_name, input, session)` | `(str, str, GameSession) -> dict` | 调用指定 Agent（narrator / world_builder），详见 `engine/turn_runner.py` |
| `_parse_narrator_output(text)` | `str -> (narrative, delta, choices)` | Narrator 解析器，提取 `<state_update>` 和 `<choices>` |
| `build_<agent>_graph()` | `() -> SequentialAgentGraph` | 构建项目内顺序 Agent 图 |

## 测试位置

- `tests/unit/agents/test_narrator_parse.py` — Narrator 输出解析（含 `<state_update>` 过滤）
- `tests/unit/agents/test_world_builder_parse.py` — World Builder 解析
- `tests/unit/agents/test_common.py` — 共享节点工具

## 注意事项

- **提示词与代码同步改**：`config/prompts/system/<agent>.md` 改动时，相应 `nodes.py` 解析逻辑可能也要调整。
- **输出格式约束**：Narrator 必须用 `<state_update>` 块输出 JSON delta 作为传输契约，否则解析器返回空 delta 并计入诊断；该 delta 不会被应用到权威状态。
- **历史说明**：旧架构中存在 Judge 审核与模型 delta 应用（见 CHANGELOG），现已由规则引擎权威结算取代，judge 模块与相关接线已删除。
