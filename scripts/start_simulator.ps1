[CmdletBinding()]
param(
    [string]$EnvFile,
    [switch]$Build,
    [switch]$UseMavenRelay,
    [switch]$WithML,
    [switch]$NoDemo
)
. (Join-Path $PSScriptRoot 'portable_common.ps1')
$path = Get-CascadeEnvPath $EnvFile
if (-not (Test-Path -LiteralPath $path) -or $Build -or $UseMavenRelay) {
    & (Join-Path $PSScriptRoot 'setup.ps1') -EnvFile $path -UseMavenRelay:$UseMavenRelay -WithML:$WithML
} else { & (Join-Path $PSScriptRoot 'check_prerequisites.ps1') }
$settings = Get-CascadeSettings $path
Assert-CascadeNetwork
$priorMlUrl = [Environment]::GetEnvironmentVariable('SIMULATOR_ML_URL','Process')
try {
    if ($WithML) {
        $env:SIMULATOR_ML_URL = 'http://ml:8090'
        Invoke-CascadeCompose $path @('--profile','ml','up','-d','--wait','--wait-timeout','240','database','ml','backend','frontend')
    } else {
        $env:SIMULATOR_ML_URL = 'http://127.0.0.1:8090'
        Invoke-CascadeCompose $path @('up','-d','--wait','--wait-timeout','180','database','backend','frontend')
    }
} finally { [Environment]::SetEnvironmentVariable('SIMULATOR_ML_URL', $priorMlUrl, 'Process') }
$api = "http://127.0.0.1:$($settings.BACKEND_PORT)/api"
$ui = "http://127.0.0.1:$($settings.FRONTEND_PORT)"
$health = Wait-CascadeHttp "$api/health" -Backend
Wait-CascadeHttp $ui
Wait-CascadeHttp "$ui/api/health" -Backend | Out-Null
if (-not $NoDemo) { & (Join-Path $PSScriptRoot 'load_demo.ps1') -EnvFile $path -SkipIfConfigured }
Write-Host "Dashboard: $ui"
Write-Host "Backend: $api/health ($($health.directedEdges) real directed road edges)"
Write-Host "Database project: $($settings.COMPOSE_PROJECT_NAME); persistent volume is separate from the original research database."
if ($WithML) { Write-Host "Optional CPU ML service: http://127.0.0.1:$($settings.ML_PORT)/health. Trained simulation models retain deterministic fallback." }
else { Write-Host 'Default prediction: deterministic rule-based simulation. Optional ML is disabled.' }
Write-Host 'SIMULATED DEMO operations only. Start/Pause in the dashboard; existing state and saved scenarios are preserved.'
