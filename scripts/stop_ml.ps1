[CmdletBinding()]
param([string]$EnvFile)
. (Join-Path $PSScriptRoot 'portable_common.ps1')
$path = Get-CascadeEnvPath $EnvFile
$settings = Get-CascadeSettings $path
Invoke-CascadeCompose $path @('--profile','ml','stop','ml')
Write-Host "Stopped only optional CPU inference for $($settings.COMPOSE_PROJECT_NAME)."
Write-Host 'The simulator and saved database remain available. Unavailable trained predictions use explicit deterministic fallback.'
