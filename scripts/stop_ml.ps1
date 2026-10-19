$ErrorActionPreference = 'Stop'
$recordPath = Join-Path (Split-Path -Parent $PSScriptRoot) '.runtime/ml-process.json'
if (Test-Path -LiteralPath $recordPath) {
    $record = Get-Content -LiteralPath $recordPath -Raw | ConvertFrom-Json
    $process = Get-Process -Id $record.pid -ErrorAction SilentlyContinue
    if ($process -and [Math]::Abs(($process.StartTime.ToUniversalTime() - [DateTime]::Parse($record.startedUtc).ToUniversalTime()).TotalSeconds) -lt 1) {
        # Windows virtual-environment redirectors can launch the base Python as a child.
        $entry = Join-Path $PSScriptRoot 'serve_ml.py'
        $children = Get-CimInstance Win32_Process -Filter "ParentProcessId = $($process.Id)" | Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -like ('*' + $entry + '*') }
        foreach ($child in $children) { Stop-Process -Id $child.ProcessId -ErrorAction SilentlyContinue }
        Stop-Process -Id $process.Id -ErrorAction SilentlyContinue
        Write-Host 'Stopped the recorded ML inference process.'
    }
    Remove-Item -LiteralPath $recordPath
}
