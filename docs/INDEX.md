# 项目文档索引

后续智能体先读本文，再按任务读取对应文档。文档保持少量权威入口，避免重复和历史材料误导。

## 必读入口

- `AGENTS.md`：项目硬约束、玩法契约、技术栈、关键文件和常用命令。
- `docs/PROJECT_AUDIT.md`：当前结构边界、三层职责、冗余清理结论和技术债队列。
- `docs/RUNTIME_FLOW.md`：当前业务逻辑和代码调用链。
- `docs/AGENT_OPERATION_RULES.md`：PowerShell、WSL、Buildozer、ADB、日志、密钥和产物目录规则。

## 按任务读取

| 任务 | 优先阅读 |
| --- | --- |
| 理解项目边界或做架构审核 | `docs/PROJECT_AUDIT.md` |
| 分析游戏运行流程 | `docs/RUNTIME_FLOW.md` |
| APK 打包、USB 真机、截图、logcat | `docs/AGENT_OPERATION_RULES.md` |
| 迁移到另一台电脑 | `docs/ZIP_TRANSFER.md` |
| 安全与密钥边界 | `docs/security.md`、`AGENTS.md` |
| Agent 提示词或调用链 | `config/prompts/system/*.md`、`src/agens_novel/agents/` |

## 当前执行边界

- 产品入口只保留 Android/Kivy/Buildozer。
- 验证只走 USB 真机 + ADB，不再使用 Windows 桌面真实点击。
- 默认模型仍是 Agens；DeepSeek 是可选测试项。
- API key 只允许来自当前进程环境变量或 app-private 设置，不写入仓库或日志。
- `D:\chat\plan` 是外部证据和 APK 目录，不属于仓库内容。
