# artifacts/

工件存储。每次 LLM 调用的原始输入 / 输出 / 错误都保存为可审计的工件。

## 关键文件

- `store.py` — `ArtifactStore`：写入 / 读取 JSONL 工件。

## 主要 API

| 名称 | 签名 | 说明 |
|------|------|------|
| `ArtifactStore.record(agent, payload)` | `(str, dict) -> None` | 记录一次 Agent 调用的输入输出 |
| `ArtifactStore.recent(limit)` | `(int) -> list[dict]` | 读取最近 N 条工件 |

## 注意事项

- **不在版本控制**：`runtime/artifacts/` 被 `.gitignore` 忽略。
- **可观测性**：用于回放 LLM 决策、调试、审计。
- **可禁用**：默认开启；测试中可通过 monkeypatch 关闭。
