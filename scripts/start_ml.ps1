[CmdletBinding()]
param([string]$Models = 'models/milestone4/v1', [int]$Port = 8090)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$runtime = Join-Path $projectRoot '.runtime'
$modelPath = if ([IO.Path]::IsPathRooted($Models)) { $Models } else { Join-Path $projectRoot $Models }
if (-not (Test-Path -LiteralPath (Join-Path $modelPath 'manifest.json'))) { throw "Trained model manifest is unavailable at $modelPath; train/validate the bundle before starting ML. The simulator can use deterministic fallback." }
$python = Join-Path $projectRoot '.venv-ml/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'Create the isolated CPU ML environment using requirements-ml-cpu.txt first.' }
$expectedManifest = (Get-FileHash -LiteralPath (Join-Path $modelPath 'manifest.json') -Algorithm SHA256).Hash.ToLowerInvariant()
$bundle = Get-Content -LiteralPath (Join-Path $modelPath 'manifest.json') -Raw | ConvertFrom-Json
foreach ($source in $bundle.implementationSha256.PSObject.Properties) {
    $sourcePath = [IO.Path]::GetFullPath((Join-Path $projectRoot $source.Name))
    if (-not $sourcePath.StartsWith($projectRoot + [IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)) { throw 'Invalid model source-provenance path.' }
    if (-not (Test-Path -LiteralPath $sourcePath) -or (Get-FileHash -LiteralPath $sourcePath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $source.Value) { throw "Frozen model implementation changed: $($source.Name). Use a new versioned training/evaluation bundle." }
}
try { $existing = Invoke-RestMethod "http://127.0.0.1:$Port/health" -TimeoutSec 3 } catch { $existing = $null }
if ($existing -and $existing.status -eq 'UP') {
    if ($existing.selectionManifestSha256 -ne $expectedManifest) { throw 'The running ML service contains a different model bundle; stop it explicitly before switching bundles.' }
    Write-Host "ML service already running at http://127.0.0.1:$Port"; exit 0
}
New-Item -ItemType Directory -Force -Path $runtime | Out-Null
$entry = Join-Path $PSScriptRoot 'serve_ml.py'
$process = Start-Process -FilePath $python -ArgumentList @(('"{0}"' -f $entry),'--models',('"{0}"' -f $modelPath),'--host','0.0.0.0','--port',"$Port") -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $runtime 'ml.log') -RedirectStandardError (Join-Path $runtime 'ml-error.log')
@{pid=$process.Id;startedUtc=$process.StartTime.ToUniversalTime().ToString('o');port=$Port;models=$modelPath} | ConvertTo-Json | Set-Content (Join-Path $runtime 'ml-process.json')
$deadline = (Get-Date).AddSeconds(90)
do {
    try { $health = Invoke-RestMethod "http://127.0.0.1:$Port/health" -TimeoutSec 3; if ($health.status -eq 'UP') { break } } catch { }
    if ($process.HasExited) { throw 'ML service exited; inspect .runtime/ml-error.log' }
    Start-Sleep -Seconds 2
} while ((Get-Date) -lt $deadline)
if (-not $health -or $health.status -ne 'UP') { throw 'ML service did not become healthy; inspect .runtime/ml-error.log' }
if ($health.selectionManifestSha256 -ne $expectedManifest) { throw 'The ML service did not load the requested checksum-bound model manifest.' }
Write-Host "CPU-compatible ML inference ready: http://127.0.0.1:$Port ($($health.modelsLoaded) loaded models)"
