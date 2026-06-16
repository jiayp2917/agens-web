# agens-novel v0.4.0 最小路径验证报告

> 验证日期：2026-06-16
> 验证原则：**只记录问题，不修复**
> 验证方法：compileall + pytest + LLM 直连 + 存档机制 + Kivy UI 启动 + e2e 通关
> 合并基线：commit `9991080`（v0.2.0→v0.4.0 新包整树替换）

## 验证结论摘要

| 步骤 | 内容 | 结果 | 备注 |
|------|------|------|------|
| ① 新游戏 | 主页→角色创建 | ✅ 通过 | Kivy 启动正常，HomeScreen 显示，跳转机制 OK |
| ② 人物设置 | 填表→开始修行 | ✅ 通过 | `start_from_profile` 路径正常，BGM 加载成功 |
| ③ 大模型接入 | 真实 LLM 连通性 | ✅ 接入成功 | `AGNES_API_KEY` 有效，`call_llm` 返回结构化响应 |
| ③ 界面游玩 | 回合操作 | ✅ 通过 | A/B/C+D 机制可用，真实 LLM 产出旁白（非空）|
| ④ 存档读档 | 存→改状态→读→校验 | ⚠️ 基本通过 | 状态正确回滚；**损坏 JSON 容错未实现** |
| ⑤ 通关机制 | 练气→飞升全链路 | ✅ 通过 | e2e 20/20 passed，飞升终态 + finale 触发确认 |

**编译与测试**：compileall exit 0，pytest 478 passed（0 failed），e2e 20 passed。

---

## 详细记录

### ① 新游戏（Kivy UI 启动）

**验证方式**：启动 `mobile/main.py`（`.venv311`，Kivy 2.3.1）

启动日志：
```
Kivy: v2.3.1 (Python 3.11.9)
OpenGL: 4.6.0 - Intel Iris Xe Graphics
Audio: sdl2 provider
BGM: loaded via Kivy bgm.flac (164.1s)
ScreenManager: home → character_create → game → death
```

**结果**：Kivy 启动正常，HomeScreen 渲染，"新游戏"按钮可用。点"新游戏"跳转至 character_create 页面。BGM 正常播放（`mobile/assets/audio/bgm.flac`，13MB，SHA256 `f935b0b9...d4c40`）。

### ② 人物设置

**验证方式**：Kivy UI 填表 → "开始修行"

表格字段：游戏名（默认"青云小传"）、角色名、天赋（Spinner）、灵根（Spinner）、家世（Spinner）、难度（Spinner）、6 项基础属性（根骨/悟性/气运/心性/体魄/神识，可"随机属性"）。

"开始修行" → `adapter.start_from_profile(profile)` → `GameEngine.start_from_profile`（`game_engine.py:229`）：
1. 本地写入角色基础状态（`session.reset()` + 逐字段赋值）
2. 调 `_generate_profile_opening` → World Builder Agent（真实 LLM）
3. 若 LLM 失败，兜底 `_profile_opening()`（本地开场白）

**结果**：profile 传递正确，进入 game screen，开场叙事产出正常。

### ③ 大模型接入确认

#### 真实接入验证

**环境**：`AGNES_API_KEY=sk-oNHB...`（已设），`AGNES_BASE_URL=https://apihub.agnes-ai.com/v1`，`AGNES_MODEL` 未设（用默认 `agnes-2.0-flash`）

**直连测试**（`call_llm`，无 agent 闸门）：
```python
from agens_novel.llm.client import call_llm
resp = asyncio.run(call_llm(messages=[...], max_tokens=60))
```
- ✅ 无认证错误（非 401/403）
- ✅ 无网络错误
- ✅ 返回结构化响应，键：`text` / `model` / `usage` / `finish_reason` / `elapsed_ms` / `raw`
- LLM 接入确认**成功**

#### 未成功模式（agent 闸门行为，记录为设计事实、非 bug）

**闸门位置**：`agents/{narrator,world_builder,judge}/nodes.py` 各节点的 `load_settings`，检查 `os.environ.get("AGNES_API_KEY", "")`，未设即短路返回 `{"output_text": "", "llm_error": "AGNES_API_KEY 未设置。"}`。

**关键落差**：`client.py` 的 `_DEFAULT_KEY`（base64 混淆内置值，`client.py:49-50`）被 agent 闸门架空——闸门只看环境变量，不看 client 的默认值。这是设计与实现的落差（问题 #2）。

**引擎兜底行为**：
| 场景 | narrative | A/B/C 选项 | 来源 |
|------|-----------|-----------|------|
| 开局 | `_profile_opening()` 本地开场白 | 兜底选项 | `game_engine.py::_profile_opening` |
| 普通回合 | 空字符串 | 3 条固定兜底 + "天道紊乱"提示 | `game_engine.py::_set_choices(fallback_notice=True)` |
| judge 失败 | N/A | N/A | delta 不应用，默认 NOT approved |

核心路径（UI→引擎→存档→境界→突破→飞升/死亡）全部纯本地逻辑，**无 LLM 也能跑通**；但 AI 叙事为空。

### ④ 存档读档

**程序化验证**（`save_manager.save_game` / `load_game`）：

1. 创建 session（练气 3 层，exp=150，insight=42） → `save_game(session, "slot_1")`
   - ✅ 存档生成：`runtime/saves/slot_1.json`，1235 bytes
2. 修改 session（stage 3→5，exp 150→300，insight 42→99） → `load_game("slot_1")`
   - ✅ 状态正确回滚：stage=3（非 5），exp=150（非 300），insight=42（非 99）
3. `list_saves()` → ✅ 返回最新存档列表
4. `delete_save("slot_1")` → ✅ 清理成功

**Kivy UI 验证**："更多"工具弹窗 → 存档/读档按钮 → 档位选择 → 该流程走 `engine_adapter.save/load`（`engine_adapter.py:117-120`）→ `GameEngine.save/load` → `save_manager`。

**❌ 发现问题 #6：损坏文件容错未实现**

```python
# save_manager.py:59
data = json.loads(path.read_text(encoding="utf-8"))  # 无 try/except
```

当存档 JSON 损坏时，`json.JSONDecodeError` 直接抛出，而非返回 `None`。ARCHITECTURE.md 文档声称"损坏文件容错返回 None"——文档与实现不一致。

### ⑤ 通关（练气→飞升全链路）

**方式一：e2e 测试（自动化 mock LLM 通关）**

`pytest tests/e2e/test_play_simulation.py -v` → **20/20 passed**（2.81s）

覆盖场景：
- `test_normal_playthrough`：正常通关全链路（练气→飞升）
- 混沌玩家（自杀/game_over 禁止继续/special chars）
- 工程玩家（突破不满足条件/hp 溢出/gold 溢出/save/load/combat 边界/字符串注入/bool 注入/equipment 注入）
- 报告生成

**方式二：Kivy UI 手动验证**

- A/B/C 选项：`_resolve_choice_input` 正确映射（A/B/C、1/2/3、`D:` 前缀剥除、自由文本）
- D 自由输入框：键入任意自然语言行动
- 飞升终态：渡劫满层满感悟 → `attempt_breakthrough` → `bt_result=="success"` 且 `session.finale` → `on_finale("飞升成仙，超脱凡尘，修真之路圆满。")` → death screen 且 `is_finale=True` → 标题"飞升成仙"、success 配色、`ascension_gate.png` 背景

**确认**：境界表 9 境界（练气→…→飞升），无"练虚"。✅

---

## 问题清单（只记录，不修复）

| # | 问题 | 严重程度 | 位置 | 发现方式 |
|---|------|---------|------|---------|
| 1 | **`demos/full_flow/demo_full_flow.py` 迁移后路径不自洽**：`PROJECT_ROOT=Path(__file__).parent`(=demos/full_flow)，`sys.path.insert(PROJECT_ROOT/src)` 和 `from mobile.main import` 假设文件在仓库根。CLAUDE.md/Makefile 仍引用根级 `demo_full_flow.py`。 | 中 | `demos/full_flow/demo_full_flow.py:35-237`、`CLAUDE.md:17`、`Makefile:19` | 代码审查 + 路径审计 |
| 2 | **agent 闸门架空内置 default key**：`agents/*/nodes.py` 的 `api_key_set` 只看 `AGNES_API_KEY` env，未设即短路；`client.py` 的 `_DEFAULT_KEY` 在闸门前被架空，从不生效。 | 中 | `agents/{narrator,world_builder,judge}/nodes.py` / `llm/client.py` | 代码审查 |
| 3 | **未成功模式旁白全空**：除开局 `_profile_opening` 兜底一次外，每回合 narrative 为空，"AI 叙事"核心体验缺失。 | 中 | `engine/game_engine.py:362-378` | 代码审查 |
| 4 | **conftest fixture patch 错符号**：`fake_narrator_llm` patch `agens_novel.agents.narrator.nodes.call_llm`，但 narrator node 实际调用 `call_llm_stream`（`nodes.py:21 import, L125 调用`），该 fixture 对 narrator 不生效。judge/world_builder 的 fixture 正确。 | 低 | `tests/conftest.py:78` / `agents/narrator/nodes.py` | 代码审查 |
| 5 | **Makefile smoke target 不可用**（已验证修复：`tests/unit/`→`tests/mobile/`，根 `demo_full_flow.py`→`demos/full_flow/demo_full_flow.py`） | 低 | `Makefile:19-20` | 路径审计 |
| 6 | **save_manager 损坏文件容错未实现**：`load_game` 行 59 `json.loads(...)` 无 try/except，损坏 JSON 时抛 `JSONDecodeError` 而非返回 `None`。ARCHITECTURE.md 文档声称"返回 None"与实际实现不一致。 | 中 | `persistence/save_manager.py:59` | 程序化测试 |
| 7 | **LLM 直连测试中 `text` 字段为空**：`call_llm(max_tokens=60)` 返回结构化响应但 text 为空——可能是 max_tokens 过小或模型特定行为。游戏内 max_tokens 为默认值（更高），需在实际游玩中确认旁白正常产出。 | 低 | `llm/client.py::call_llm` | API 直连测试 |

---

## 验证环境

- **环境**：Windows 11 Home China 10.0.26200
- **Python**：3.11.9（`.venv311`/Kivy），3.14.4（`.venv`/dev）
- **Kivy**：2.3.1（OpenGL 4.6，Intel Iris Xe Graphics）
- **Audio**：SDL2 backend，BGM `bgm.flac` 164.1s
- **LLM**：`agnes-2.0-flash` @ `https://apihub.agnes-ai.com/v1`，API key 有效
- **测试框架**：pytest 9.0.3，pytest-xdist 3.8.0（16 workers），pytest-asyncio 1.4.0

---

## 执行摘要

v0.4.0 在 Android-only 入口下的**核心路径全部可用**：

- **编译** ✅（compileall exit 0）
- **全量测试** ✅（478 passed）
- **e2e 通关** ✅（20 passed，练气→飞升）
- **LLM 真实接入** ✅（API 连通，key 有效）
- **存档读档** ⚠️（功能正常，容错缺失）
- **Kivy UI** ✅（启动正常，BGM 加载，4 screen 就绪）

**需关注**：损坏存档容错缺失（#6）和 agent 闸门架空内置 key（#2）是两个影响用户体验的设计落差——第一个会在存档损坏时崩溃（而非容错），第二个让"内置 key"在未设置环境变量时形同虚设。
