[CmdletBinding()]
param([string]$EnvFile, [switch]$Build, [switch]$UseMavenRelay)
# Reuse the portable lifecycle and the frozen CPU model bundle.
& (Join-Path $PSScriptRoot 'start_simulator.ps1') -EnvFile $EnvFile -WithML -NoDemo -Build:$Build -UseMavenRelay:$UseMavenRelay
if ($LASTEXITCODE -ne 0) { throw 'ML-enabled simulator startup failed.' }
