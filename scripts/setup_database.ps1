[CmdletBinding()]
param(
    [switch]$SkipImport,
    [switch]$SkipDependencyInstall
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$composePath = Join-Path $projectRoot 'infrastructure/compose.yaml'
$pythonPath = Join-Path $projectRoot '.venv/Scripts/python.exe'

function Assert-LastExit([string]$Operation) {
    if ($LASTEXITCODE -ne 0) { throw "$Operation failed (exit $LASTEXITCODE)." }
}

function Test-DockerEngine {
    try {
        & docker info --format '{{.ServerVersion}}' 2>$null | Out-Null
        return $LASTEXITCODE -eq 0
    } catch { return $false }
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw 'Install Docker Desktop, enable its Linux engine, then rerun this script.'
}
if (-not (Test-DockerEngine)) {
    $desktopPath = Join-Path $env:ProgramFiles 'Docker/Docker/Docker Desktop.exe'
    if (-not (Test-Path -LiteralPath $desktopPath)) {
        throw 'Docker engine is unavailable. Start Docker Desktop, then rerun this script.'
    }
    Start-Process -FilePath $desktopPath -WindowStyle Hidden
    $engineDeadline = (Get-Date).AddSeconds(120)
    do {
        Start-Sleep -Seconds 3
        if (Test-DockerEngine) { break }
    } while ((Get-Date) -lt $engineDeadline)
    if (-not (Test-DockerEngine)) { throw 'Docker engine did not become ready within 120 seconds.' }
}

# Docker Compose reads infrastructure/.env automatically. No existing volume is removed.
& docker compose -f $composePath up -d --wait --wait-timeout 120 database
Assert-LastExit 'Starting PostgreSQL/PostGIS'

if (-not (Test-Path -LiteralPath $pythonPath)) {
    & python -m venv (Join-Path $projectRoot '.venv')
    Assert-LastExit 'Creating Python virtual environment'
}
if (-not $SkipDependencyInstall) {
    & $pythonPath -m pip install -r (Join-Path $projectRoot 'requirements-db.txt')
    Assert-LastExit 'Installing database dependencies'
}

if (-not $env:DATABASE_URL) {
    # Parse only the four documented local Compose settings; never execute an env file.
    $settings = @{ POSTGRES_DB = 'cascadeshield'; POSTGRES_USER = 'cascadeshield'; POSTGRES_PASSWORD = 'cascadeshield'; POSTGRES_PORT = '55432' }
    $envPath = Join-Path $projectRoot 'infrastructure/.env'
    if (Test-Path -LiteralPath $envPath) {
        foreach ($line in Get-Content -LiteralPath $envPath) {
            if ($line -match '^\s*(POSTGRES_DB|POSTGRES_USER|POSTGRES_PASSWORD|POSTGRES_PORT)\s*=\s*(.*?)\s*$') {
                $settings[$Matches[1]] = $Matches[2].Trim([char[]]@('"', "'"))
            }
        }
    }
    foreach ($key in @('POSTGRES_DB','POSTGRES_USER','POSTGRES_PASSWORD','POSTGRES_PORT')) {
        $override = [Environment]::GetEnvironmentVariable($key)
        if ($override) { $settings[$key] = $override }
    }
    $dbUser = [uri]::EscapeDataString($settings.POSTGRES_USER)
    $dbPassword = [uri]::EscapeDataString($settings.POSTGRES_PASSWORD)
    $dbName = [uri]::EscapeDataString($settings.POSTGRES_DB)
    $env:DATABASE_URL = "postgresql://${dbUser}:${dbPassword}@127.0.0.1:$($settings.POSTGRES_PORT)/${dbName}"
}

if (-not $SkipImport) {
    & $pythonPath (Join-Path $projectRoot 'scripts/load_postgis.py') --execute
    Assert-LastExit 'Importing eligible processed datasets'
}
& $pythonPath (Join-Path $projectRoot 'scripts/verify_database.py')
Assert-LastExit 'Verifying PostgreSQL/PostGIS and dataset imports'
Write-Host 'Database is ready. Verification: reports/simulator_database_execution.json'
