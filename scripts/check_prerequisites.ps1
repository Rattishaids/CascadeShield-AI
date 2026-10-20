[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSVersion.Major -lt 5) { throw 'PowerShell 5.1 or later is required.' }
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw 'Install Docker Desktop with Linux containers, then restart PowerShell: https://www.docker.com/products/docker-desktop/' }
& docker info --format '{{.ServerVersion}}' 2>$null
if ($LASTEXITCODE -ne 0) { throw 'Docker engine is unavailable. Start Docker Desktop, wait until it is ready, and select Linux containers.' }
$operatingSystem = & docker info --format '{{.OSType}}'
if ($LASTEXITCODE -ne 0 -or $operatingSystem.Trim() -ne 'linux') { throw 'This Compose distribution requires Docker Linux containers.' }
$version = & docker compose version --short
if ($LASTEXITCODE -ne 0 -or $version -notmatch '^v?(\d+)\.(\d+)') { throw 'Docker Compose v2 is required; update Docker Desktop.' }
if ([int]$Matches[1] -lt 2 -or ([int]$Matches[1] -eq 2 -and [int]$Matches[2] -lt 24)) { throw 'Docker Compose v2.24 or newer is required.' }
Write-Host "Prerequisites ready: PowerShell $($PSVersionTable.PSVersion), Docker Linux engine, Compose $version."
Write-Host 'Java 21, Maven, Node.js and PostgreSQL run inside containers. Python and ML packages are optional.'
