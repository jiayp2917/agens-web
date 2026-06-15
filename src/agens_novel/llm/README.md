# llm/

LLM 集成层。OpenAI 兼容 HTTP 客户端与 SSE 流式响应。

## 关键文件

- `client.py` — `LLMClient`：OpenAI 兼容 HTTP 客户端（`/v1/chat/completions`）。
- `sse.py` — SSE（Server-Sent Events）流式响应解析器。
- `retry.py` — 重试与退避策略。
- `types.py` — 共享类型定义（`ChatMessage`、`ChatResponse` 等）。

## 主要 API

| 名称 | 签名 | 说明 |
|------|------|------|
| `LLMClient(base_url, api_key)` | 构造 | 创建客户端 |
| `client.chat(messages, **kwargs)` | `list[Message] -> Response` | 同步聊天完成调用 |
| `client.stream_chat(messages, **kwargs)` | `list[Message] -> Iterator[Chunk]` | 流式聊天 |
| `parse_sse(data)` | `bytes -> Iterator[dict]` | 解析 SSE 数据 |

## 测试位置

- `tests/unit/llm/test_llm_client.py` — 客户端基础测试
- `tests/unit/llm/test_sse_parser.py` — SSE 解析

## 注意事项

- **通用 LLM 层**：本模块非必要不改，跨项目可复用。
- **API key 从环境变量读取**：不写入代码 / 文档 / 日志。
- **支持 OpenAI 兼容协议**：`/v1/chat/completions` + Bearer Auth。
- **流式响应**：通过 `agens_novel.engine._stream_context` 传递回调给调用方。
