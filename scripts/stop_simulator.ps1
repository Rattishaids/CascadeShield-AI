[CmdletBinding()]
param([string]$EnvFile)
. (Join-Path $PSScriptRoot 'portable_common.ps1')
$path = Get-CascadeEnvPath $EnvFile
$settings = Get-CascadeSettings $path
Invoke-CascadeCompose $path @('--profile','ml','stop')
$record = Join-Path $CascadeProjectRoot '.runtime/maven-relay-process.json'
if (Test-Path -LiteralPath $record) {
    $saved = Get-Content -LiteralPath $record -Raw | ConvertFrom-Json
    $process = Get-Process -Id $saved.pid -ErrorAction SilentlyContinue
    if ($process -and $process.ProcessName -match '^python' -and $process.StartTime.ToUniversalTime().ToString('o') -eq $saved.startedUtc) { Stop-Process -Id $process.Id }
}
Write-Host "Stopped $($settings.COMPOSE_PROJECT_NAME). Its database volume, simulation and saved scenarios are preserved."
