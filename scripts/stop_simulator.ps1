$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$record = Join-Path $projectRoot '.runtime/frontend-process.json'
if (Test-Path -LiteralPath $record) {
    $saved = Get-Content -LiteralPath $record -Raw | ConvertFrom-Json
    $process = Get-Process -Id $saved.pid -ErrorAction SilentlyContinue
    if ($process -and $process.ProcessName -eq 'node' -and $process.StartTime.ToUniversalTime().ToString('o') -eq $saved.startedUtc) { Stop-Process -Id $process.Id }
}
& docker compose -f (Join-Path $projectRoot 'simulator/compose.yaml') stop backend
if ($LASTEXITCODE -ne 0) { throw 'Backend stop failed.' }
Write-Host 'Backend stopped. Database, existing volumes and saved scenarios are preserved.'
