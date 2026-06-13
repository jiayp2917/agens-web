# Security — API Key Handling

## Hard rules

1. **The API key never touches disk.**
   - It is loaded from `AGNES_API_KEY` env var only.
   - It is never written to `.env`, `runtime/`, logs, or audit files.
   - `Settings.__repr__` and `Settings.public_summary()` always mask it.
2. **The API key never appears in stdout/stderr.**
   - A `SecretRedactor` log filter replaces any `sk-[A-Za-z0-9_-]{8,}` token with `sk-***`.
   - The same filter rewrites `AGNES_API_KEY=<value>` to `AGNES_API_KEY=***`.
3. **All AI outputs go to `runtime/artifacts/`.**
   - This is the sandbox. Nothing escapes it without an explicit human action.
4. **Save files are sandboxed in `runtime/saves/`.**
   - Save names are sanitized: only alphanumeric, hyphen, underscore allowed.
   - Path traversal (e.g. `../../etc/passwd`) is blocked by the sanitizer.
   - See `paths.save_path()` for the sanitization logic.

## The env-injection pattern

`scripts/run_with_key.ps1` is the canonical way to run any CLI command.
It sets the env var for the child Python process, then clears it in
`finally` — so the key disappears the moment the script exits (including
on Ctrl+C / errors).

```powershell
.\scripts\run_with_key.ps1 -ApiKey "<your key>" -- repl
```

## How to verify

```powershell
# 1. Run, then check the key is gone from the env.
$env:AGNES_API_KEY = "sk-leaked"
.\scripts\run_with_key.ps1 -ApiKey $env:AGNES_API_KEY -- status
echo "after script: $env:AGNES_API_KEY"   # should be empty

# 2. Scan the runtime tree for accidental leaks.
select-string -Path runtime\logs\*.jsonl,runtime\artifacts\**\*.json -Pattern "sk-[A-Za-z0-9]{8,}" -List
# (should return no matches)

# 3. Run the test suite — it asserts the key is never logged.
python -m pytest -q
```
