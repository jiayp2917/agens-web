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
& $PgCtl start -D $DataDir -l $LogFile -o "-p $Port -h $HostName"
if ($LASTEXITCODE -ne 0) {
    throw "pg_ctl start failed. Check log: $LogFile"
}

& $PgIsReady -h $HostName -p $Port
if ($LASTEXITCODE -ne 0) {
    throw "PostgreSQL started but is not accepting connections yet. Check log: $LogFile"
}

Write-Host "Local PostgreSQL started on ${HostName}:$Port."
Write-Host '$env:TEST_DATABASE_URL = "postgresql+psycopg://agens_test@127.0.0.1:55432/agens_web_test"'
