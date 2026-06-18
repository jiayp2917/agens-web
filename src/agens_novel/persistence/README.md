# persistence/

存档系统。负责 JSON 存读档。

## 关键文件

- `save_manager.py` — `SaveManager`：列出 / 读取 / 写入 / 删除存档。

## 主要 API

| 名称 | 签名 | 说明 |
|------|------|------|
| `SaveManager.list_saves()` | `() -> list[dict]` | 列出所有存档（按时间倒序） |
| `SaveManager.save(name, data)` | `(str, dict) -> bool` | 写入存档到 `runtime/saves/<name>.json` |
| `SaveManager.load(name)` | `str -> dict \| None` | 读取存档 |
| `SaveManager.delete(name)` | `str -> bool` | 删除存档 |

## 测试位置

- 测试与 `tests/unit/session/test_session_serialization.py` 配合（session 序列化）— persistence 自身的单元测试在 `tests/unit/settings/test_settings.py` 等。

## 注意事项

- **存档位置**：`runtime/saves/`，被 `.gitignore` 忽略。
- **运行时路径**：通过 `agens_novel.paths.SAVE_DIR` 解析到 `runtime/saves/`，Web 数据库另存于 `runtime/web/`。
- **容错读取**：存档文件损坏时返回 `None` 而不是抛异常（避免游戏启动失败）。
