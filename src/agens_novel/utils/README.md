# utils/

跨模块工具函数。

## 关键文件

- `secrets.py` — 密钥 / token 脱敏（日志中用 `***` 隐藏敏感字段）。
- `timing.py` — 计时器、节流、防抖。

## 主要 API

| 名称 | 签名 | 说明 |
|------|------|------|
| `redact(value)` | `str -> str` | 字符串脱敏，保留前缀和后 4 字符 |
| `redact_dict(d)` | `dict -> dict` | 递归脱敏 dict 中的敏感字段 |
| `Timer` | 类 | 上下文管理器，统计代码块耗时 |

## 测试位置

- `tests/unit/settings/test_secrets_redactor.py` — `redact` / `redact_dict`

## 注意事项

- **脱敏必须无副作用**：`redact_*` 是纯函数，不修改原对象。
- **性能敏感路径慎用**：`Timer` 在热路径会增加开销，按需启用。
