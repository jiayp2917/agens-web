# Security — API Key Handling

## Hard Rules

1. API key 不写入仓库、日志、运行产物或文档。
2. 运行时只从当前进程环境变量、应用内临时输入或内置兜底读取。
3. `SecretRedactor` 必须继续屏蔽 `sk-...` 形态的密钥。
4. 存档路径必须经过 sanitizer，禁止路径穿越。

## Local Debug Pattern

`scripts/run_with_key.ps1` 只在当前 PowerShell 进程及其子进程中注入环境变量，随后在 `finally` 中清理：

```powershell
.\scripts\run_with_key.ps1 -ApiKey "<your key>"
```

该脚本启动 Android/Kivy 产品入口：

```powershell
python mobile\main.py
```

## Verify

```powershell
$env:AGNES_API_KEY = "sk-leaked"
.\scripts\run_with_key.ps1 -ApiKey $env:AGNES_API_KEY
echo "after script: $env:AGNES_API_KEY"

select-string -Path runtime\logs\*.jsonl,runtime\artifacts\**\*.json -Pattern "sk-[A-Za-z0-9]{8,}" -List
.\.venv\Scripts\python.exe -m pytest -q
```
