# Android 高保真原型落地执行报告

## 目标

依据 `docs/prototypes/index.html` 和 `docs/prototypes/prototype.css`，将 Android/Kivy 移动端改造为水墨极简风格，并覆盖主页、主页弹窗、游戏主界面、角色创建、设置、读档、教程、死亡重开等原型状态。

## Phase 用户故事与验收

### Phase 1：水墨视觉基础

用户故事：作为玩家，我打开 APK 时能看到与原型一致的水墨背景、宣纸白/墨绿/暗夜主题和右上角 BGM 开关。

验收：
- Given 启动移动端，When 进入主页，Then 显示水墨山门背景、标题和 BGM 开关。
- Given 设置主题，When 选择三套主题之一，Then 色值与原型 CSS 的宣纸白、青灰、淡金体系一致。

实现：
- `mobile/theme.py` 重写三套水墨主题。
- `mobile/assets/images/ink_home_bg.png` 从原型资产复制。
- `mobile/audio_manager.py` 新增音频开关骨架，缺音频资源时 no-op。

### Phase 2：主页弹窗化

用户故事：作为玩家，我在主页点击读档、教程、设置时，应在主页内看到宣纸质感弹窗，而不是跳转离开主页。

验收：
- Given 在主页，When 点击“读档”，Then 主页内展示自动档和五个手动档。
- Given 在主页，When 点击“教程”，Then 主页内展示可翻页教程。
- Given 在主页，When 点击“设置”，Then 主页内展示模型、主题、游玩模式和音频配置。

实现：
- `mobile/screens/home_screen.py` 重构为水墨主页和三类内嵌弹窗。
- 设置弹窗默认提供 Agens 模型配置入口，可添加 OpenAI 兼容模型。
- API key 只注入当前进程环境变量，不写入 `settings.json`。

### Phase 3：自由度模式

用户故事：作为玩家，我可以选择高/中/低自由度，游戏界面按模式决定是否显示选项和是否允许自由输入。

验收：
- Given 高自由度，Then 只显示叙事和自由输入框。
- Given 中自由度，Then 显示建议选项，同时允许自由输入。
- Given 低自由度，Then 显示选项并弱化输入框。

实现：
- `GameMode`、`GAME_MODE_LABELS` 和 `game_mode` 字段加入数据层。
- `mobile/widgets/action_bar.py` 根据模式切换输入行为。
- `mobile/widgets/narrative_view.py` 支持选项渲染。
- `GameEngine` 记录 `last_choices`，模型未返回选项时提供符合场景的兜底选项。

### Phase 4：顶部信息栏

用户故事：作为玩家，我在游戏顶部看到角色基础信息和回合数，而不是 HP/MP/EXP 厚重状态条。

验收：
- Given 游戏已开始，Then 顶部显示姓名、回合数、年龄、境界、灵根、天赋、家世、气运。
- Given 旧存档被加载，Then 新字段使用默认值且不崩溃。

实现：
- `GameSession` 新增 `age/talent/family_background/luck/difficulty/game_mode/attributes/last_choices`。
- `mobile/widgets/status_bar.py` 重写为 6 格 stat-grid。
- `to_save_dict()` / `from_save_dict()` 已同步兼容。

### Phase 5：角色创建

用户故事：作为玩家，我点击新游戏后进入独立角色创建页，填写信息、选择天赋/灵根/家世/难度、随机属性后开始游戏。

验收：
- Given 点击“新游戏”，Then 进入 `character_create` 独立页面。
- Given 点击“随机”，Then 六项基础属性重新分配。
- Given 游戏名称输入 `2917`，Then 界面不出现显式说明，只在确认开局后体现为阿清、满属性、顶级家世、顶级天赋、顶级灵根和特殊开场叙事。

实现：
- `mobile/screens/character_create_screen.py` 新增完整角色创建页。
- `GameEngine.start_from_profile()` 统一通过游戏引擎落入 `GameSession`，移动端不绕过逻辑入口。

### Phase 6：死亡界面与收尾

用户故事：作为玩家，角色死亡后看到全屏“道途已断”界面，可重新开始、读取存档或返回主页。

验收：
- Given 角色死亡，Then 跳转全屏死亡页。
- Given 在死亡页，Then 三个按钮分别可进入重开、读档和主页流程。

实现：
- `mobile/screens/death_screen.py` 新增全屏死亡页。
- `mobile/screens/game_screen.py` 的 game-over 回调改为跳转死亡页。

## 原型对齐核查

- 主页：标题、背景图、BGM 开关、五个主按钮已实现。
- 主页读档弹窗：自动档 + 5 手动档 + 读取/删除已实现。
- 主页教程弹窗：玩法、自由度、境界、死亡重开、AI 逻辑约束已实现。
- 主页设置弹窗：模型连接、主题色、游玩模式、音频控制已实现。
- 游戏主界面：顶部信息栏、中部叙事/选项、底部 10 工具按钮和输入框已实现。
- 高/中/低自由度：三种模式均有 UI 行为差异。
- 角色创建：表单、随机属性、隐藏触发结果态已实现。
- 死亡态：全屏死亡页和三操作已实现。
- 境界：实现展示采用修正后的境界链，未引入已删除境界。

## 代码质量与安全

- 未修改 `src/agens_novel/llm/` 通用 LLM 组件。
- 移动端仍通过 `EngineAdapter -> GameEngine` 调用游戏逻辑。
- 新增字段已进入 `GameSession.as_game_state()`、`to_save_dict()` 和 `from_save_dict()`。
- API key 不写入移动端设置文件；`save_settings()` 会剔除 `api_key`。
- 所有 screen/widget 文件均低于 500 行。

## 代码权重

| 模块 | 行数 | 占比 |
|---|---:|---:|
| `mobile/screens/` | 2197 | 13.8% |
| `mobile/widgets/` | 883 | 5.5% |
| `mobile/service/` | 271 | 1.7% |
| `src/agens_novel/` | 5271 | 33.0% |
| `tests/` | 7356 | 46.0% |

说明：`tests/` 超过 40% 是测试代码占比，不是运行时代码架构失衡。运行时代码中无单一模块超过 40%。

## 验证结果

执行命令：

```powershell
.\.venv\Scripts\python.exe -m compileall -q src tests mobile
.\.venv\Scripts\python.exe -m pytest -q
rg -n "<已删除境界名>|<显式隐藏模式文案>" mobile src tests docs\prototypes
rg -n "<隐藏触发直白说明>" mobile src tests docs\prototypes
```

结果：
- 编译检查通过。
- 全量测试：`570 passed in 24.13s`。
- 禁用境界/显式提示检查：目标实现文件与原型目录无命中。
