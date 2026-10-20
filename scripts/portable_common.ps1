# Helpers for the portable ZIP distribution. Dot-source from its entry scripts.
$ErrorActionPreference = 'Stop'
$CascadeProjectRoot = Split-Path -Parent $PSScriptRoot

function Get-CascadeEnvPath([string]$Path) {
    if (-not $Path) { return Join-Path $CascadeProjectRoot '.env' }
    if ([IO.Path]::IsPathRooted($Path)) { return [IO.Path]::GetFullPath($Path) }
    return [IO.Path]::GetFullPath((Join-Path $CascadeProjectRoot $Path))
}

function Get-CascadeSettings([string]$Path) {
    $settings = @{}
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "Local configuration missing: $Path. Run scripts/setup.ps1 first."
    }
    foreach ($line in Get-Content -LiteralPath $Path) {
        if ($line -match '^\s*(#.*)?$') { continue }
        if ($line -notmatch '^([A-Z][A-Z0-9_]*)=(.*)$') { throw "Invalid configuration line in $Path. Use KEY=value without executable PowerShell." }
        $settings[$Matches[1]] = $Matches[2]
    }
    foreach ($name in @('COMPOSE_PROJECT_NAME','FRONTEND_PORT','BACKEND_PORT','POSTGRES_PORT','POSTGRES_DB','POSTGRES_USER','POSTGRES_PASSWORD')) {
        if (-not $settings.ContainsKey($name) -or -not $settings[$name]) { throw "Set $name in $Path." }
    }
    if ($settings.COMPOSE_PROJECT_NAME -notmatch '^[a-z0-9][a-z0-9_-]*$') { throw 'COMPOSE_PROJECT_NAME must contain lowercase letters, digits, hyphens or underscores.' }
    foreach ($name in @('FRONTEND_PORT','BACKEND_PORT','POSTGRES_PORT','ML_PORT')) {
        if ($name -eq 'ML_PORT' -and -not $settings.ContainsKey($name)) { $settings.ML_PORT = '8090' }
        $number = 0
        if (-not [int]::TryParse($settings[$name], [ref]$number) -or $number -lt 1024 -or $number -gt 65535) { throw "$name must be between 1024 and 65535." }
    }
    if (@($settings.FRONTEND_PORT,$settings.BACKEND_PORT,$settings.POSTGRES_PORT,$settings.ML_PORT | Select-Object -Unique).Count -ne 4) { throw 'Frontend, backend, PostgreSQL and optional ML ports must be distinct.' }
    foreach ($name in @('POSTGRES_DB','POSTGRES_USER')) {
        if ($settings[$name] -notmatch '^[a-z][a-z0-9_]{0,62}$') { throw "$name must be a lowercase PostgreSQL identifier." }
    }
    if ($settings.POSTGRES_PASSWORD -notmatch '^[A-Za-z0-9_-]{24,128}$') { throw 'POSTGRES_PASSWORD must contain 24-128 letters, digits, underscores or hyphens. setup.ps1 generates a suitable random value.' }
    # Shell variables otherwise take precedence over --env-file in Docker Compose.
    # Refuse discrepancies so the script and Compose always address the same instance.
    foreach ($name in $settings.Keys) {
        $value = [Environment]::GetEnvironmentVariable($name, 'Process')
        if ($null -ne $value -and $value -cne $settings[$name]) { throw "Environment variable $name conflicts with $Path. Clear the shell variable or make it match the file." }
    }
    return $settings
}

function Invoke-CascadeCompose([string]$Path, [string[]]$ComposeArguments) {
    & docker compose --env-file $Path -f (Join-Path $CascadeProjectRoot 'compose.yaml') @ComposeArguments
    if ($LASTEXITCODE -ne 0) { throw "Docker Compose command failed (exit $LASTEXITCODE). Inspect docker compose logs using the same --env-file and -f options." }
}

function Assert-CascadeNetwork {
    $expected = @{
        'road_graph.json' = 'c943bac278192042b22342d8e1be898cc68512fb936e314633645bc3e0304e60'
        'roads.geojson' = 'd714bab06c2eeb022eab54dac8a8224ca6c5330579579fa66938e35c6497f478'
    }
    foreach ($name in $expected.Keys) {
        $path = Join-Path $CascadeProjectRoot "data/processed/chennai_osm/$name"
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Required Chennai network asset missing: $path. Download and extract the complete repository ZIP." }
        if ($expected[$name] -and (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expected[$name]) { throw "Chennai network checksum mismatch: $name. Restore the versioned file from the release ZIP." }
    }
}

function Wait-CascadeHttp([string]$Url, [int]$Seconds = 180, [switch]$Backend) {
    $deadline = (Get-Date).AddSeconds($Seconds)
    do {
        try {
            if ($Backend) {
                $health = Invoke-RestMethod -Uri $Url -TimeoutSec 5
                if ($health.status -eq 'UP') { return $health }
            } else {
                $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 5
                if ($response.StatusCode -eq 200) { return }
            }
        } catch { }
        Start-Sleep -Seconds 2
    } while ((Get-Date) -lt $deadline)
    throw "Service did not become ready: $Url. Inspect Compose logs; no existing database volume was reset."
}
