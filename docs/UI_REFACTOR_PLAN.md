# UI 重构计划：编年史原型落地

日期：2026-06-23

本文记录已审核通过的 UI 原型图和后续前端重构计划。后续 UI 改造以本文和 `docs/ui-prototypes/` 下图片为准，不再按旧页面视觉继续扩展。

## 已确认原型

| 编号 | 文件 | 对应范围 |
| --- | --- | --- |
| 1 | `docs/ui-prototypes/2026-06-23-home-approved.png` | 首页 |
| 2 | `docs/ui-prototypes/2026-06-23-character-create-approved.png` | 角色创建页 |
| 3 | `docs/ui-prototypes/2026-06-23-desktop-chronicle-approved.png` | 桌面端游戏页 |
| 4 | `docs/ui-prototypes/2026-06-23-mobile-chronicle-approved.png` | 移动端游戏页 |
| 5 | `docs/ui-prototypes/2026-06-23-component-board-approved.png` | 按钮、图标、状态条、时间轴、弹窗等组件规范 |

## 目标

- 将当前 React UI 重构为编年史式游玩界面。
- 首页按已确认首页原型重做，保持第一屏就是游戏入口。
- 角色创建页按三栏布局重做：主角、命数、六维。
- 游戏页按编年史时间轴重做：角色状态栏、往事时间轴、A/B/C/D 选择区。
- 移动端按 375px 原型重做：顶部角色摘要、时间轴优先、选项竖排。
- 组件样式按组件板统一：主按钮、次按钮、危险按钮、图标按钮、选择按钮、状态条、提示条、弹窗。

## 不做范围

- 不新增玩法系统。
- 不恢复自由输入 D。
- 不恢复 HP/MP、经验、感悟、灵石。
- 不新增游戏名称输入。
- 不把原型图直接作为页面底图。
- 不在前端写入 API key、隐藏规则或技术错误细节。

## 页面拆分

### HomePage

文件：`web/frontend-react/src/pages/HomePage.tsx`

- 保留 `jiayp` 品牌链接。
- 保留新游戏、读档、教程、设置、邀请码注册入口。
- 保留 BGM 小喇叭常驻入口。
- 首页标题为“文字修仙模拟器”，按钮竖排居中，主按钮为“新游戏”。
- 展示 QQ 群号 `985776771` 和 QQ 群二维码。
- 背景使用水墨山门与纸纹理，整体与编年史游戏页保持同一视觉语言。
- 校验首页素材路径，确保开发和生产环境都能加载。
- 1080p 和 2K 下首屏不出现页面级纵向滚动；移动端可自然滚动，但不得横向滚动。

### CharacterCreatePage

文件：`web/frontend-react/src/pages/CharacterCreatePage.tsx`

目标结构：

- `CreationHeroBar`：顶部品牌和 BGM。
- `CharacterPanel`：角色名、难度、随机角色、开始修行。
- `FatePanel`：天赋、灵根、家世。
- `AttributePanel`：六维属性，体魄、神魂、气运、悟性、心性、根骨。

关键要求：

- 不出现“游戏名称”。
- 天赋、灵根、家世显示为“名称 · 颜色字”。
- 玩家可见颜色只允许：白、绿、蓝、紫、橙、红。
- 不显示“稀有、传说、地、天”等旧等级词。
- 手选不出现橙/红；随机可出现更高颜色。
- 气运视觉可突出，但不得明示隐藏触发规则。
- 1080p 和 2K 下不出现页面级纵向滚动。

### GamePage Desktop

文件：`web/frontend-react/src/pages/GamePage.tsx`

目标结构：

- `GameTopBar`：品牌、BGM、设置、存档。
- `StatusRail`：头像、姓名、年龄、境界、寿元、天赋、灵根、家世、气运。
- `ChronicleTimeline`：编年史时间轴。
- `FallbackBanner`：模型不可用提示和继续/结束按钮。
- `ChoiceGrid`：A/B/C/D 两列选择。

关键要求：

- 编年史为主，不做聊天记录式长文本。
- 每条记录包含纪年、年龄、短叙事。
- 最新记录高亮，旧记录弱化。
- A/B/C/D 按钮紧凑两列，字母徽标和文案同行。
- A 固定稳妥，B 固定机遇，C 固定风险，D 固定气运。
- 不显示经验、感悟、灵石、HP、MP。
- 寿元显示使用 `remaining_lifespan/lifespan`，例如 `82/100`。

### GamePage Mobile

文件：`web/frontend-react/src/pages/GamePage.tsx`

目标结构：

- `MobileTopSummary`：头像、姓名、境界、年龄、寿元、BGM、设置。
- `MobileChronicleTimeline`：移动端时间轴。
- `MobileChoiceList`：A/B/C/D 竖排选择。

关键要求：

- 375px 下无横向滚动。
- 顶部摘要不重叠。
- A/B/C/D 按钮高度不少于 44px。
- 时间轴文本短句优先，避免长段模型输出撑爆移动端。
- 底部选择区不得遮挡时间轴正文。

## 组件样式落地

优先从组件板提取这些样式：

- `InkButton`：主按钮、次按钮、危险按钮、禁用态。
- `IconButton`：BGM、设置、存档。
- `ChoiceButton`：A/B/C/D 选择按钮。
- `CharacterStatusCard`：角色状态条。
- `LifespanBar`：寿元 `82/100`。
- `RarityDot`：白、绿、蓝、紫、橙、红色点。
- `ChronicleItem`：时间轴条目。
- `FallbackNotice`：模型不可用提示。
- `ConfirmDialog`：确认弹窗和遮罩。

样式集中在 `web/frontend-react/src/styles.css`，必要时再拆为组件级 CSS 文件。本轮先控制改动面，不引入新的 UI 框架。

## 实施顺序

1. 建立设计 token
   - 纸色、墨色、青玉、朱砂、浅金、边框、阴影、圆角、按钮高度。
   - 验证：组件板中的按钮、状态条、色点能复用同一套变量。

2. 重构首页
   - 按首页原型重做首屏构图、竖排按钮、BGM、QQ群和二维码。
   - 验证：1080p/2K 首屏无异常下滑，移动端无横向滚动。

3. 重构角色创建页
   - 先完成桌面三栏。
   - 再压缩 1080p 高度。
   - 最后做移动端自然滚动。
   - 验证：无游戏名称，无旧等级词，无横向滚动。

4. 重构桌面游戏页
   - 先做左侧状态栏和时间轴。
   - 再重做 A/B/C/D 两列选择。
   - 最后接入模型不可用提示条。
   - 验证：叙事区为主体，选项区不再过大。

5. 重构移动端游戏页
   - 按 375px 原型做顶部摘要、时间轴和竖排选项。
   - 验证：按钮高度、无重叠、无横向滚动。

6. 收尾测试
   - 更新前端契约测试。
   - 浏览器人工验收 375px、1080p、2K。

## 验收标准

- `npm run build` 通过。
- `pytest -q tests\web` 通过。
- 首页素材、QQ 二维码、BGM 图标正常显示。
- 角色创建页：
  - 不出现“游戏名称”。
  - 不出现玩家可见的“稀有、传说、地、天”。
  - 六维属性完整。
- 游戏页：
  - 不出现经验、感悟、灵石、HP、MP。
  - A/B/C/D 语义稳定。
  - 寿元显示为剩余寿元/寿元上限。
  - 模型失败时只显示脱敏提示。
- 375px、1080p、2K：
  - 无横向滚动。
  - 无文字重叠。
  - 主要按钮高度不少于 44px。

## 可能遗漏

当前 5 张图已经覆盖首页、角色创建、桌面游戏页、移动端游戏页和组件样式板，足以开始本轮 UI 重构。暂未发现必须补充的新原型。
