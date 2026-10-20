[CmdletBinding()]
param([string]$EnvFile, [switch]$SkipIfConfigured)
. (Join-Path $PSScriptRoot 'portable_common.ps1')
$path = Get-CascadeEnvPath $EnvFile
$settings = Get-CascadeSettings $path
$api = "http://127.0.0.1:$($settings.BACKEND_PORT)/api"
function Invoke-Demo([string]$Endpoint, $Body = $null) {
    if ($null -eq $Body) { return Invoke-RestMethod -Uri "$api$Endpoint" -TimeoutSec 60 }
    return Invoke-RestMethod -Uri "$api$Endpoint" -Method Post -ContentType 'application/json' -Body ($Body | ConvertTo-Json -Depth 30 -Compress) -TimeoutSec 60
}
$state = Invoke-Demo '/state'
$resources = $state.operations
$configured = $state.trucks.Count -gt 0 -or $state.incidents.Count -gt 0 -or $resources.warehouses.Count -gt 0 -or $resources.docks.Count -gt 0 -or $resources.drivers.Count -gt 0 -or $resources.deliveries.Count -gt 0
if ($configured -or $state.clockSec -ne 0 -or $state.status -ne 'DRAFT' -or $state.replaying) {
    if ($SkipIfConfigured) { Write-Host 'Existing simulation preserved; automatic demo loading skipped.'; return }
    throw 'Demo loading requires an empty DRAFT simulation at time zero. Existing state was preserved. Use a new Compose project/database for a separate demo.'
}
$graph = Get-Content -LiteralPath (Join-Path $CascadeProjectRoot 'data/processed/chennai_osm/road_graph.json') -Raw | ConvertFrom-Json
$pair = $graph.metadata.demoPairs[0]
$nodes = @{}
foreach ($node in $graph.nodes) { $nodes[[string]$node.id] = $node }
$first = $nodes[[string]$pair.startNodeId]
$last = $nodes[[string]$pair.destinationNodeId]
if (-not $first -or -not $last) { throw 'The bundled graph does not contain the tested demo nodes.' }
$origin = @{longitude=$first.longitude; latitude=$first.latitude}
$destination = @{longitude=$last.longitude; latitude=$last.latitude}
$route = Invoke-Demo '/routes/preview' @{start=$origin; destination=$destination; waypoints=@(); maxSpeedKph=40}
$baseline = [Math]::Ceiling($route.baseTravelSec * 10) / 10
foreach ($suffix in @('A','B')) {
    $departure = 0
    if ($suffix -eq 'B') { $departure = 200 }
    Invoke-Demo '/trucks' @{id="DEMO-$suffix"; name="SIMULATED shared-dock truck $suffix"; start=$origin; destination=$destination; waypoints=@(); maxSpeedKph=40; capacityKg=1000; loadKg=500; driverName="Simulated driver $suffix"; priority='NORMAL'; departureSec=$departure; deadlineSec=4000} | Out-Null
}
$snapped = (Invoke-Demo '/state').trucks[0].destination
Invoke-Demo '/operations/warehouses' @{id='DEMO-W'; name='SIMULATED Chennai receiving facility'; location=$snapped; dockCapacity=1} | Out-Null
Invoke-Demo '/operations/docks' @{id='DEMO-D'; name='SIMULATED shared receiving dock'; warehouseId='DEMO-W'; serviceSec=300; openFromSec=0; openUntilSec=10000} | Out-Null
foreach ($suffix in @('A','B')) {
    $reservation = $baseline
    $deadline = $baseline + 600
    $priority = 'NORMAL'
    if ($suffix -eq 'B') { $reservation += 300; $deadline += 30; $priority = 'HIGH' }
    Invoke-Demo '/operations/drivers' @{id="DEMO-DR$suffix"; name="SIMULATED driver $suffix"; available=$true; shiftStartSec=0; shiftEndSec=10000} | Out-Null
    Invoke-Demo '/operations/deliveries' @{id="DEMO-L$suffix"; name="SIMULATED delivery $suffix"; warehouseId='DEMO-W'; loadKg=200; deadlineSec=$deadline; priority=$priority} | Out-Null
    Invoke-Demo '/operations/assignments' @{truckId="DEMO-$suffix"; driverId="DEMO-DR$suffix"; dockId='DEMO-D'; deliveryIds=@("DEMO-L$suffix"); reservationStartSec=$reservation; reservationEndSec=($reservation+300)} | Out-Null
}
$saved = Invoke-Demo '/scenarios' @{name='SIMULATED DEMO - Chennai shared dock'}
$firstEdge = $graph.edges | Where-Object { $_.id -eq $route.edgeIds[0] } | Select-Object -First 1
$midLongitude = ($firstEdge.geometry[0][0] + $firstEdge.geometry[-1][0]) / 2
$midLatitude = ($firstEdge.geometry[0][1] + $firstEdge.geometry[-1][1]) / 2
Write-Host "Loaded explicit SIMULATED DEMO: two trucks, one warehouse/dock, two drivers and two deliveries. Saved scenario: $($saved.id)."
Write-Host "Cascade closure segment: $($firstEdge.physicalId), midpoint $midLongitude, $midLatitude; closure duration 90 seconds (1.5 minutes) at time 0."
Write-Host "Uninterrupted route baseline: $baseline seconds; shared dock service: 300 seconds; DEMO-B departure: 200 seconds; DEMO-B delivery deadline: $($baseline + 630) seconds."
Write-Host 'Inspect predicted DOCK OVERLAP and DELIVERY DEADLINE, then start/step to observe actual dock queue and delivery delay. These are simulated consequences; no intervention is applied automatically.'
