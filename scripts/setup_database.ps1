[CmdletBinding()]
param([string]$EnvFile)

. (Join-Path $PSScriptRoot 'portable_common.ps1')
$path = Get-CascadeEnvPath $EnvFile
if (-not (Test-Path -LiteralPath $path)) {
    & (Join-Path $PSScriptRoot 'setup.ps1') -EnvFile $path -SkipBuild
} else {
    & (Join-Path $PSScriptRoot 'check_prerequisites.ps1')
}
$settings = Get-CascadeSettings $path
Invoke-CascadeCompose $path @('config','--quiet')
Invoke-CascadeCompose $path @('up','-d','--wait','--wait-timeout','180','database')
Invoke-CascadeCompose $path @('exec','-T','database','psql','-v','ON_ERROR_STOP=1',
    '-U',$settings.POSTGRES_USER,'-d',$settings.POSTGRES_DB,'-At','-c',
    'SELECT current_database(), current_setting(''server_version''), postgis_lib_version();')
Write-Host "PostgreSQL/PostGIS is ready for $($settings.COMPOSE_PROJECT_NAME). Existing records and its persistent volume are preserved."
Write-Host 'Backend startup applies simulator migrations and imports the included Chennai network. Historical research datasets are not imported.'
Write-Host "Start the application: powershell -ExecutionPolicy Bypass -File scripts/start_simulator.ps1 -EnvFile `"$path`""
