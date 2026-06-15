# Agent Workflow

## Shared Graph Pattern

Narrator、World Builder、Judge 都使用线性 LangGraph 节点模式：

```text
load_settings -> build_prompt -> call_agnes_llm -> save_artifact
```

每个节点返回增量 state，不直接修改入参 state。

## Agents

### World Builder

- Trigger: character creation start.
- Input: profile from Android character creation.
- Output: opening narrative, world fields, A/B/C choices.
- Failure behavior: engine emits fallback notice and uses grounded fallback choices.

### Narrator

- Trigger: player selects A/B/C or submits D typed action.
- Input: current `GameSession`, player action, recent history.
- Output: narrative, state delta, next A/B/C choices.
- Rule: choices should match current scene, NPCs, resources, bottlenecks, and risk.

### Judge

- Trigger: after Narrator proposes state delta.
- Input: current state, action, narrative, proposed delta.
- Output: approved/corrected delta and review note.
- Rule: malformed or unreasonable deltas fail closed and do not corrupt session state.

## Android Integration

```text
GameScreen / CharacterCreateScreen
    -> EngineAdapter
    -> GameEngine
    -> turn_runner
    -> Agent graph
```

`EngineAdapter` runs blocking engine calls off the Kivy UI thread and posts callbacks back with `Clock.schedule_once`.

## UI Contract

- A/B/C are rendered by `mobile/widgets/narrative_view.py`.
- D typed input is handled by `mobile/widgets/action_bar.py`.
- Secondary tools are opened from `GameScreen` through the “更多” popup.
- Combat remains typed-input based; `CombatBar` is status-only.
