[CmdletBinding()]
param(
    [string]$EnvFile,
    [string]$ProjectName = 'cascadeshield-demo',
    [ValidateRange(1024,65535)][int]$FrontendPort = 5173,
    [ValidateRange(1024,65535)][int]$BackendPort = 8080,
    [ValidateRange(1024,65535)][int]$PostgresPort = 55433,
    [ValidateRange(1024,65535)][int]$MlPort = 8090,
    [switch]$SkipBuild,
    [switch]$UseMavenRelay,
    [switch]$WithML
)
. (Join-Path $PSScriptRoot 'portable_common.ps1')
& (Join-Path $PSScriptRoot 'check_prerequisites.ps1')
Assert-CascadeNetwork
$path = Get-CascadeEnvPath $EnvFile
if (-not (Test-Path -LiteralPath $path)) {
    if ($ProjectName -notmatch '^[a-z0-9][a-z0-9_-]*$') { throw 'Use a lowercase Compose project name.' }
    $random = New-Object byte[] 32
    $generator = [Security.Cryptography.RandomNumberGenerator]::Create()
    try { $generator.GetBytes($random) } finally { $generator.Dispose() }
    $password = [BitConverter]::ToString($random).Replace('-','').ToLowerInvariant()
    $lines = @('# Local generated settings. Keep this file private and preserve it with its database volume.',
        "COMPOSE_PROJECT_NAME=$ProjectName", "FRONTEND_PORT=$FrontendPort", "BACKEND_PORT=$BackendPort", "POSTGRES_PORT=$PostgresPort", "ML_PORT=$MlPort",
        'POSTGRES_DB=cascadeshield_demo', 'POSTGRES_USER=cascadeshield_demo', "POSTGRES_PASSWORD=$password", 'MAVEN_MIRROR_URL=', 'SIMULATOR_ML_URL=http://127.0.0.1:8090')
    [IO.File]::WriteAllLines($path, $lines, (New-Object Text.UTF8Encoding $false))
    Write-Host "Created private local configuration: $path (generated password is not displayed)."
} else { Write-Host "Preserving existing configuration: $path. Edit it to change ports; generation flags apply only to a new file." }
$settings = Get-CascadeSettings $path
if ($UseMavenRelay) {
    & (Join-Path $PSScriptRoot 'start_maven_relay.ps1')
    $lines = Get-Content -LiteralPath $path
    $lines = $lines | ForEach-Object { if ($_ -match '^MAVEN_MIRROR_URL=') { 'MAVEN_MIRROR_URL=http://host.docker.internal:18090/maven2' } else { $_ } }
    [IO.File]::WriteAllLines($path, $lines, (New-Object Text.UTF8Encoding $false))
    $settings = Get-CascadeSettings $path
}
Invoke-CascadeCompose $path @('config','--quiet')
if (-not $SkipBuild) {
    if ($WithML) { Invoke-CascadeCompose $path @('--profile','ml','build','backend','frontend','ml') }
    else { Invoke-CascadeCompose $path @('build','backend','frontend') }
}
Write-Host 'Setup complete. No historical data import or database reset was performed.'
Write-Host "Start: powershell -ExecutionPolicy Bypass -File scripts/start_simulator.ps1 -EnvFile `"$path`""
