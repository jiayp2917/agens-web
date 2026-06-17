# 项目文档索引

本文是后续智能体的入口索引。先按任务类型读对应文档，再修改代码或执行验证。

## 必读入口

- `AGENTS.md`：项目硬约束、玩法契约、技术栈、常用命令。
- `docs/AGENT_OPERATION_RULES.md`：非玩法类执行规则，包括编码、PowerShell、WSL、Buildozer、ADB、日志、密钥和产物目录。
- `docs/LESSONS_LEARNED_2026-06-17.md`：成功/失败经验，尤其是 APK 打包、USB 真机验证、不要再尝试的路线。
- `docs/RUNTIME_FLOW.md`：当前业务逻辑和代码调用链。
- `docs/ARCHITECTURE_DIAGRAM.md`：当前整体架构图、主流程图、单回合调用链和数据归属图。
- `docs/OPEN_ISSUES_STATUS_2026-06-17.md`：当前遗留问题处理状态、已落地修复和仍需真机验证项。
- `docs/PROJECT_RETRO_2026-06-17.md`：项目复盘、冗余清理、USB 经验、架构风险队列。

## 按任务读取

| 任务 | 优先阅读 |
| --- | --- |
| APK 打包、自行安装验证 | `docs/LESSONS_LEARNED_2026-06-17.md` |
| USB 真机调试、截图、logcat | `docs/LESSONS_LEARNED_2026-06-17.md`、`docs/PROJECT_RETRO_2026-06-17.md` |
| PowerShell 编码、WSL、产物目录、密钥操作 | `docs/AGENT_OPERATION_RULES.md` |
| 分析游戏运行流程 | `docs/RUNTIME_FLOW.md` |
| 迁移到另一台电脑 | `docs/ZIP_TRANSFER.md` |
| 修复已记录问题 | `docs/problem.md`、`docs/problem_fix_suggestions.md` |
| 查看当前遗留项状态 | `docs/OPEN_ISSUES_STATUS_2026-06-17.md` |
| 架构审查 | `docs/ARCHITECTURE_DIAGRAM.md`、`src/agens_novel/ARCHITECTURE.md`、`docs/ARCHITECTURE.md` |
| Agent 提示词或调用链 | `docs/agents.md`、`config/prompts/system/*.md` |
| 安全与密钥边界 | `docs/security.md`、`AGENTS.md` |

## 当前执行边界

- 产品入口只保留 Android/Kivy/Buildozer。
- 验证只走 USB 真机 + ADB，不再使用 Windows 桌面真实点击。
- 默认模型仍是 Agens；DeepSeek 是可选测试项。
- API key 只允许来自当前进程环境变量或 app-private 设置，不写入仓库或日志。
- `D:\chat\plan` 是外部证据和 APK 目录，不属于仓库内容。
