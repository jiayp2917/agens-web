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
    # Launch the Android/Kivy product path. Extra args are passed through for
    # local debugging helpers, but the app normally does not require them.
    & python mobile\main.py @args
    exit $LASTEXITCODE
}
finally {
    # Always clear, even on Ctrl+C.
    Remove-Item Env:\AGNES_API_KEY  -ErrorAction SilentlyContinue
    Remove-Item Env:\AGNES_BASE_URL -ErrorAction SilentlyContinue
    Remove-Item Env:\AGNES_MODEL    -ErrorAction SilentlyContinue
}
