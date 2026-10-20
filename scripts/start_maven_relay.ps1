[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
try {
    $ready = (Invoke-WebRequest 'http://127.0.0.1:18090/maven2/org/springframework/boot/spring-boot-starter-parent/3.5.16/spring-boot-starter-parent-3.5.16.pom' -Method Head -UseBasicParsing -TimeoutSec 10).StatusCode -eq 200
} catch { $ready = $false }
if ($ready) { Write-Host 'Official Maven relay is already reachable on port 18090.'; return }
$python = Get-Command python.exe -ErrorAction SilentlyContinue
if (-not $python) { throw 'The optional host Maven relay requires Python 3.11 or later. Normal setup does not require Python.' }
& $python.Source -c "import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)"
if ($LASTEXITCODE -ne 0) { throw 'The optional host Maven relay requires Python 3.11 or later.' }
$runtime = Join-Path $projectRoot '.runtime'
New-Item -ItemType Directory -Force -Path $runtime | Out-Null
$spawn = & $python.Source (Join-Path $PSScriptRoot 'spawn_maven_relay.py')
if ($LASTEXITCODE -ne 0) { throw 'Unable to launch the optional Maven relay.' }
$started = $spawn | ConvertFrom-Json
$process = Get-Process -Id $started.pid -ErrorAction Stop
@{ pid = $process.Id; startedUtc = $process.StartTime.ToUniversalTime().ToString('o') } | ConvertTo-Json | Set-Content (Join-Path $runtime 'maven-relay-process.json')
Start-Sleep -Seconds 2
if ($process.HasExited) { throw 'Maven relay failed; inspect .runtime/maven-relay-error.log.' }
Write-Host 'Official-only Maven relay started on port 18090. It relays fixed Maven Central HTTPS artifact paths and uses a local verified cache.'
