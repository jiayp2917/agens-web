# Agent 工作流详解

> 修仙模拟器的三个 Agent 都遵循相同的 4 节点线性图模式。本文档以 **Narrator Agent** 为主例，对比说明三个 Agent 的异同。

## 1. 状态机全景

```
START
  │
  ▼
load_settings      读 env → model / base_url / run_id
  │
  ▼
build_prompt       读 system prompt + game state → messages
  │
  ▼
call_agnes_llm     httpx POST → output_text
  │
  ▼
save_artifact      解析输出 → structured fields / write artifacts
  │
  ▼
END
```

4 个节点，**纯线性**。三个 Agent 共享前三个节点的模式，`save_artifact` 的解析逻辑各不同。

## 2. LangGraph 概念映射

| 概念        | 代码位置                            | 关键代码 |
|-------------|-------------------------------------|----------|
| StateGraph  | `agents/*/graph.py`                 | `g = StateGraph(GameState)` |
| Node        | `agents/*/nodes.py`                 | 4 个独立 `def` / `async def` 函数 |
| State       | `state/game_schema.py`              | `class GameState(TypedDict, total=False)` |
| Edge        | `agents/*/graph.py`                 | `g.add_edge(START, "load_settings")` 等 |
| Checkpoint  | `agents/*/graph.py`                 | `MemorySaver()` |

## 3. Narrator Agent — 天道叙述者

**目录**: `agents/narrator/`
**温度**: 0.8（高创意），**max_tokens**: 1536
**系统提示词**: `config/prompts/system/narrator.md`

**输入**: 游戏状态 JSON + 玩家行动 + 最近 20 回合聊天历史

**`build_prompt` 特殊逻辑**:
- 注入 `game_state_json`（当前角色/世界状态）作为上下文
- 拼接 `chat_history`（最近回合的 user/assistant 对）
- 校验 `user_input` 非空，否则抛 `ValueError`

**`save_artifact` 解析**:
```python
# 从 LLM 输出中提取 <state_update>...</state_update> 标签
match = re.search(r'<state_update>(.*?)</state_update>', text, re.DOTALL)
narrative = text before tag
state_delta = json.loads(match content)
```

**输出字段**: `narrative`, `state_delta`, `choices`

**错误处理**: JSON 解析失败时 delta 设为 `{}`，叙事仍正常显示。不阻塞游戏。

## 4. World Builder Agent — 世界设计师

**目录**: `agents/world_builder/`
**温度**: 0.6（中等创意），**max_tokens**: 1024
**系统提示词**: `config/prompts/system/world_builder.md`

**输入**: 角色设定文本 + `generation_type`

**支持 4 种生成类型**:
| type | 用途 | 触发命令 |
|------|------|----------|
| `new_game` | 完整角色+世界初始化 | `/new` |
| `new_region` | 新区域探索 | `/expand new_region` |
| `new_encounter` | 随机遭遇 | `/expand new_encounter` |
| `new_technique` | 新功法获取 | `/expand new_technique` |

**`save_artifact` 解析**: 从 `<world_data>...</world_data>` 标签提取 JSON。

**输出字段**: `generated_data`, `world_description`, `opening_narrative`

## 5. Judge Agent — 规则仲裁者

**目录**: `agents/judge/`
**温度**: 0.2（严格、确定性），**max_tokens**: 512
**系统提示词**: `config/prompts/system/judge.md`

**输入**: 游戏状态 + 玩家行动 + 叙事文本 + 建议的 state_delta

**`build_prompt` 特殊逻辑**:
- 将 `narrative`（Narrator 的输出叙事）和 `state_delta`（建议状态变化）注入上下文
- Judge 需要同时看到"发生了什么"和"状态怎么变了"才能审核

**`save_artifact` 解析** — 三策略 JSON 提取:
1. `` ```json ... ``` `` 围栏块
2. 整个文本是 JSON（`{...}` 包裹）
3. 第一个 `{` 到最后一个 `}` 子串

**输出字段**: `approved`（bool）, `corrected_delta`（修正后的 delta）, `judgment_note`, `review_score`（0-10）

**关键设计**: 解析失败时 **自动批准**（auto-approve），不阻塞游戏流程。

**审核维度**:
- 数值合理性（HP/MP 变化幅度）
- 境界逻辑（境界提升是否合理）
- 世界一致性（地点/NPC 是否匹配）
- 资源平衡（金币/经验获取是否合理）

## 6. 回合流程总览

```
玩家输入 "修炼吐纳"
    │
    ▼
REPL._handle_action()
    │
    ├── turn_count += 1
    │
    ├── Narrator Agent
    │   输入: 游戏状态 + "修炼吐纳" + 聊天历史
    │   输出: 叙事文本 + state_delta + choices
    │
    ├── Judge Agent（仅当 state_delta 非空时）
    │   输入: 叙事 + delta + 游戏状态
    │   输出: approved? + corrected_delta
    │   ┌─ approved=True  → 使用原始 delta
    │   └─ approved=False → 使用 corrected_delta
    │
    ├── session.apply_delta(最终_delta)
    │   ┌─ "+N" 字符串 → 增量
    │   ├─ "-N" 字符串 → 减量（floor 0）
    │   ├─ int          → 绝对赋值
    │   └─ 其他类型     → 忽略
    │
    ├── 记录回合历史 + 聊天历史（截断到 20）
    ├── 显示叙事 + 状态栏
    ├── 自动存档
    └── 检查 game_over
```

## 7. 节点函数设计原则

每个节点都是**纯函数**形式：

```python
def load_settings(state: dict) -> dict:
    # 1. 读 state 中需要的字段
    # 2. 做工作（读文件、调 LLM、写文件）
    # 3. 返回**新字段**字典 — 不要修改入参 state
    return {"model": "...", "run_id": "..."}
```

**不要**做以下事情：
- ❌ `state["x"] = ...`（直接修改入参）
- ❌ 返回整个 state（只返回增量）
- ❌ 跨节点共享变量（应该走 state）
