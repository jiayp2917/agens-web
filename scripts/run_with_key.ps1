param(
    [Parameter(Mandatory = $true)]
    [string]$ApiKey,

    [string]$BaseUrl = "https://apihub.agnes-ai.com/v1",
    [string]$Model   = "agnes-2.0-flash"
)

$ErrorActionPreference = "Stop"

# Inject env for the child process. The values are visible only to this
# process and its children; we wipe them in the finally block.
$env:AGNES_API_KEY  = $ApiKey
$env:AGNES_BASE_URL = $BaseUrl
$env:AGNES_MODEL    = $Model

try {
    # Launch the Web backend with the provided model configuration.
    & python -m uvicorn web.backend.app:app --host 127.0.0.1 --port 8000 @args
    exit $LASTEXITCODE
}
finally {
    # Always clear, even on Ctrl+C.
    Remove-Item Env:\AGNES_API_KEY  -ErrorAction SilentlyContinue
    Remove-Item Env:\AGNES_BASE_URL -ErrorAction SilentlyContinue
    Remove-Item Env:\AGNES_MODEL    -ErrorAction SilentlyContinue
}
