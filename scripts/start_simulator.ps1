[CmdletBinding()]
param([switch]$Build, [switch]$UseMavenRelay, [switch]$BackendOnly, [switch]$WithML)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$runtime = Join-Path $projectRoot '.runtime'
$python = Join-Path $projectRoot '.venv/Scripts/python.exe'
$compose = Join-Path $projectRoot 'simulator/compose.yaml'
New-Item -ItemType Directory -Force -Path $runtime | Out-Null
if ($WithML) { & (Join-Path $PSScriptRoot 'start_ml.ps1') }
if (-not (Test-Path -LiteralPath (Join-Path $projectRoot 'data/processed/chennai_osm/road_graph.json'))) {
    throw 'Prepare the real Chennai network first: python scripts/prepare_chennai_network.py'
}
& (Join-Path $PSScriptRoot 'setup_database.ps1') -SkipDependencyInstall | Out-Null
if ($UseMavenRelay) {
    $Build = $true
    try { $relayReady = (Invoke-WebRequest 'http://127.0.0.1:18090/maven2/org/springframework/boot/spring-boot-starter-parent/3.5.16/spring-boot-starter-parent-3.5.16.pom' -Method Head -UseBasicParsing -TimeoutSec 15).StatusCode -eq 200 } catch { $relayReady = $false }
    if (-not $relayReady) {
        $relayScript = Join-Path $PSScriptRoot 'maven_central_relay.py'
        $relay = Start-Process -FilePath $python -ArgumentList @(('"{0}"' -f $relayScript),'--bind','0.0.0.0','--port','18090') -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $runtime 'maven-relay.log') -RedirectStandardError (Join-Path $runtime 'maven-relay-error.log')
        $relay.Id | Set-Content (Join-Path $runtime 'maven-relay.pid')
        Start-Sleep -Seconds 2
    }
}
if ($Build) {
    if ($UseMavenRelay) { & docker compose -f $compose build --build-arg 'MAVEN_MIRROR_URL=http://host.docker.internal:18090/maven2' backend }
    else { & docker compose -f $compose build backend }
    if ($LASTEXITCODE -ne 0) { throw 'Backend build failed; see reports/MAVEN_CENTRAL_RELAY.md for the Docker networking fallback.' }
}
& docker compose -f $compose up -d backend
if ($LASTEXITCODE -ne 0) { throw 'Backend startup failed.' }
$deadline = (Get-Date).AddSeconds(90)
do {
    try { $health = Invoke-RestMethod 'http://127.0.0.1:8080/api/health' -TimeoutSec 5; if ($health.status -eq 'UP') { break } } catch { }
    Start-Sleep -Seconds 2
} while ((Get-Date) -lt $deadline)
if (-not $health -or $health.status -ne 'UP') { throw 'Backend did not become healthy. Run docker compose -f simulator/compose.yaml logs backend' }
Write-Host "Backend ready: http://127.0.0.1:8080/api/health ($($health.directedEdges) real directed edges)"
if (-not $BackendOnly) {
    $frontend = Join-Path $projectRoot 'simulator/frontend'
    if (-not (Test-Path -LiteralPath (Join-Path $frontend 'node_modules/vite/bin/vite.js'))) {
        Push-Location $frontend
        try { & npm.cmd ci; if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed.' } } finally { Pop-Location }
    }
    try { $frontendReady = (Invoke-WebRequest 'http://127.0.0.1:5173' -UseBasicParsing -TimeoutSec 3).StatusCode -eq 200 } catch { $frontendReady = $false }
    if (-not $frontendReady) {
        $vite = Join-Path $frontend 'node_modules/vite/bin/vite.js'
        $process = Start-Process -FilePath (Get-Command node.exe).Source -ArgumentList @(('"{0}"' -f $vite),'--host','127.0.0.1','--port','5173','--strictPort') -WorkingDirectory $frontend -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $runtime 'frontend.log') -RedirectStandardError (Join-Path $runtime 'frontend-error.log')
        @{pid=$process.Id; startedUtc=$process.StartTime.ToUniversalTime().ToString('o')} | ConvertTo-Json | Set-Content (Join-Path $runtime 'frontend-process.json')
        Start-Sleep -Seconds 2
    }
    Write-Host 'Dashboard: http://127.0.0.1:5173'
}
Write-Host 'The current simulated fleet/scenarios are preserved. Reset in the dashboard to begin a new run.'
