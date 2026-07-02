param(
    [string]$PgBin = "F:\pg\bin",
    [string]$DataDir = "",
    [int]$Port = 55432,
    [string]$HostName = "127.0.0.1"
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
if (-not $DataDir) {
    $DataDir = Join-Path $RepoRoot ".tmp\pg-test-20260626-55432"
}

$PgIsReady = Join-Path $PgBin "pg_isready.exe"
$PgCtl = Join-Path $PgBin "pg_ctl.exe"
$PostmasterPid = Join-Path $DataDir "postmaster.pid"

if (-not (Test-Path -LiteralPath $PgIsReady)) {
    throw "pg_isready.exe not found at $PgIsReady"
}
if (-not (Test-Path -LiteralPath $PgCtl)) {
    throw "pg_ctl.exe not found at $PgCtl"
}

& $PgIsReady -h $HostName -p $Port
if ($LASTEXITCODE -eq 0) {
    Write-Host "Local PostgreSQL is already accepting connections on ${HostName}:$Port."
    Write-Host '$env:TEST_DATABASE_URL = "postgresql+psycopg://agens_test@127.0.0.1:55432/agens_web_test"'
    exit 0
}

if (-not (Test-Path -LiteralPath $DataDir)) {
    throw "PostgreSQL data directory not found: $DataDir"
}

& $PgCtl status -D $DataDir | Out-Host
$LogFile = Join-Path $DataDir "postgresql-$Port.log"
try {
    $portState = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue |
        Select-Object -First 5 LocalAddress,LocalPort,State,OwningProcess
    if ($portState) {
        Write-Host "Port $Port is already in use. Current listeners/connections:"
        $portState | Format-Table | Out-Host
        Write-Host "If this is PostgreSQL, use pg_isready/status instead of starting a second server."
    }
} catch {
    Write-Host "Could not inspect TCP port ${Port}: $($_.Exception.Message)"
}

try {
    & $PgCtl start -D $DataDir -l $LogFile -o "-p $Port -h $HostName"
} catch {
    Write-Host "pg_ctl start raised an exception: $($_.Exception.Message)"
}
if ($LASTEXITCODE -ne 0) {
    Write-Host "pg_ctl start failed."
    Write-Host "Check log: $LogFile"
    if (Test-Path -LiteralPath $PostmasterPid) {
        Write-Host "postmaster.pid exists: $PostmasterPid"
        Write-Host "Before deleting it, confirm no postgres.exe process is using this data directory and port $Port is free."
        Write-Host "Suggested checks:"
        Write-Host "  & `"$PgCtl`" status -D `"$DataDir`""
        Write-Host "  Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue"
        Write-Host "  Get-Process postgres -ErrorAction SilentlyContinue"
    }
    throw "pg_ctl start failed. Do not remove the data directory; inspect the diagnostics above first."
}

& $PgIsReady -h $HostName -p $Port
if ($LASTEXITCODE -ne 0) {
    throw "PostgreSQL started but is not accepting connections yet. Check log: $LogFile"
}

Write-Host "Local PostgreSQL started on ${HostName}:$Port."
Write-Host '$env:TEST_DATABASE_URL = "postgresql+psycopg://agens_test@127.0.0.1:55432/agens_web_test"'
