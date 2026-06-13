$ErrorActionPreference = "Stop"

$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$exports = Join-Path $root "exports"
New-Item -ItemType Directory -Force $exports | Out-Null

$chrome = "D:\UserData\dev-cache\ms-playwright\chromium-1223\chrome-win64\chrome.exe"
if (-not (Test-Path $chrome)) {
    throw "Chromium not found at $chrome"
}

$names = @(
    "home",
    "home-save-modal",
    "home-settings-modal",
    "home-tutorial-modal",
    "game-mid-freedom",
    "game-high-freedom",
    "game-low-freedom",
    "character-create",
    "character-2917-result",
    "game-over"
)

$html = (Resolve-Path (Join-Path $root "index.html")).Path.Replace("\", "/")

foreach ($name in $names) {
    $out = Join-Path $exports "$name.png"
    $url = "file:///${html}?export=${name}"
    & $chrome `
        --headless=new `
        --no-sandbox `
        --disable-gpu `
        --hide-scrollbars `
        --force-device-scale-factor=2 `
        --window-size=390,844 `
        --screenshot="$out" `
        "$url" | Out-Null
}

$all = Join-Path $exports "all-screens.png"
& $chrome `
    --headless=new `
    --no-sandbox `
    --disable-gpu `
    --hide-scrollbars `
    --force-device-scale-factor=1 `
    --window-size=1700,3000 `
    --screenshot="$all" `
    "file:///$html" | Out-Null

Write-Host "Exported $($names.Count) screens to $exports"
