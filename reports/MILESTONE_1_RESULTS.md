# First simulator milestone: executed results

Completed on 2026-10-09. The local demonstration is running at **http://127.0.0.1:5173**, with Spring Boot at **http://127.0.0.1:8080/api/health**. The active demonstration is paused at 140.0 simulated seconds, with 20 explicitly simulated trucks and one operator-injected road closure. Resume advances the authoritative backend clock. Reset restores original assignments for a new run.

## Preserved research work and database

The original raw datasets, processed cohorts, acquisition scripts, manifests and historical reports are preserved. PostgreSQL 17.5 / PostGIS 3.5.2 is now running locally. The existing checksum-verified loader imported and validated **18 eligible tables, 2,414,128 rows**. Repeated startup/import checks did not alter those research rows. Porto and NYC remain quarantined and have no research-use imports. GB accidents, England/Wales sites, Brazil e-commerce and Birmingham geography/weather are separate cohorts; they are not joined to simulated Chennai freight operations.

The initial repository had no simulator services, trained model, conference-paper PDF or dataset-strategy PDF to reuse. The acquisition/ETL/quality/PostGIS work was reused, with a separate `cascadeshield_sim` schema for this milestone.

## Real Chennai network

A new immutable OSM Overpass extract was acquired for bounds `[13.04, 80.24, 13.095, 80.29]`. Source timestamp: **2026-10-09T05:33:21Z**; original file: `data/raw/chennai_osm/central_chennai.json`, **7,984,665 bytes**. Its SHA-256 is `38ab5bdea18ca7859daea5a3801f1a5d138d320e29a841aa8d67f00c1c87e80d`.

Prepared graph: **12,386 nodes, 23,907 directed edges, 14,147 physical map segments and 10 supported node-via turn restrictions**. The road graph, map geometry and PostGIS geometry are consistent. All imported Chennai geometries passed validity/SRID checks. ODbL 1.0 licensing, attribution, original bytes, access filtering, supported/unsupported restrictions, date and missing-speed assumptions are recorded separately in [CHENNAI_NETWORK.md](CHENNAI_NETWORK.md) and `data/metadata/chennai_network_provenance.json`. Missing speed values are labelled simulation assumptions, not observations.

## Working vertical slice

- Manual truck creation, vehicle/load/speed/deadline validation, snapped starts/destinations and optional ordered stops on real connected road routes.
- Backend-owned fixed 0.1 second movement, start/pause/resume/reset/restart/step and 1x/2x/5x/10x controls.
- Clicked physical-road closure/slowdown injection, duration/severity effects, direct truck impact and incident resolution. Occupied edges can be exited safely; inaccessible edges are never entered.
- Labelled rule-based ETA/risk and normalized Continue/Wait/Reroute comparisons, explanations and explicit operator approval. Rerouting preserves actual position and incoming-way restrictions; approved waits release when their incidents resolve.
- React/TypeScript/MapLibre dashboard with correctly bundled map worker, real vector roads/routes, nearest-road selection, truck tracking, actual event timeline and realized simulated KPIs.
- PostgreSQL network persistence, transactional state/event checkpoints, scenario save/JSON export and deterministic command-schedule replay. Real container restart restores paused state without clock movement during downtime.

Prediction and prevention service interfaces provide extension points for later validated model and operational-graph integration. Frontend polling visualizes backend positions and submits commands; it does not run a separate truck simulation.

## Executed checks

| Check | Actual result |
| --- | --- |
| Existing acquisition/ETL and Chennai Python tests | 16 passed |
| Java road routing, movement/interventions/replay and regression tests | 24 passed; 0 failures/errors/skips, including real Chennai graph |
| Frontend API, formatting, demo assignments, worker setup and nearest-road tests | 21 passed |
| Frontend production build | Passed, including emitted MapLibre worker asset |
| HTTP + PostgreSQL/PostGIS integration | 15 passed |
| Real backend-container restart persistence | 1 passed |
| Complete browser workflow | 7 passed; no console/page errors |
| Local startup script | Executed successfully; API UP and hidden frontend serving HTTP 200 |

The browser test manually created three trucks by clicking starts/destinations, calculated routes, verified actual movement and pause freeze, clicked Anna Salai segment `567205827:4`, injected a closure and approved a reroute with exactly unchanged position. It saved/exported/replayed the recorded scenario, then created and moved 20 connected simulated trucks at 10x. The observed clock advanced 20 simulated seconds during the two-second browser observation. This is engineering test evidence, not a research baseline or field-effectiveness result.

The separate restart check preserved paused clock 17.3 s, three mid-route trucks, one active slowdown, a saved scenario and five persisted audit events. All historical imports remained intact.

Machine-readable evidence: [milestone completion](MILESTONE_1_RESULTS.json), [Java tests](simulator_java_tests.json), [frontend tests](simulator_frontend_tests.json), [database imports](simulator_database_execution.json), [API integration](simulator_integration_tests.json), [restart](simulator_restart_tests.json), [browser](simulator_browser_tests.json). Actual browser screenshots: [dashboard](screenshots/milestone-1-dashboard.png), [manual intervention](screenshots/milestone-1-intervention.png). The independent map-worker smoke script is `simulator/frontend/scripts/map_worker_smoke.py`; its generated evidence stays in ignored `smoke-output/`.

The browser checks found and corrected an actual Vite/MapLibre worker loading problem, passive overlays intercepting map clicks, and selection depending on rendered-feature order. Java regression checks corrected wait release, repeated-reroute turn history, invalid incident time inputs and held-truck speed display. These fixes were verified against the final running behavior.

## Launch and repeat checks

From the project root:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/start_simulator.ps1
```

The current image is already built. After Java changes, this host's Docker HTTPS restriction needs the documented official-only Maven relay:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/start_simulator.ps1 -UseMavenRelay
```

For a reusable Java test command, with the relay running on port 18090:

```powershell
$projectRoot = (Get-Location).Path
docker run --rm --mount "type=bind,source=$projectRoot,target=/workspace" `
  --mount type=volume,source=cascadeshield_maven_cache,target=/root/.m2 `
  -e MAVEN_MIRROR_URL=http://host.docker.internal:18090/maven2 `
  -e SIMULATOR_GRAPH_PATH=/workspace/data/processed/chennai_osm/road_graph.json `
  -w /workspace/simulator/backend maven:3.9-eclipse-temurin-21 `
  mvn -B -q -s mirror-settings.xml test
```

The executed 24-test run used the same source tree and real graph with a temporary Maven settings file whose mirror ID was `host-maven-central`. The repository settings file uses `local-official-central-relay`; cached artifacts may be revalidated when changing mirror IDs. Both target the same official Maven Central repository through the documented host relay.

Full prerequisites, demonstration steps, REST contract, test commands, persistence behavior, modelling assumptions and stop commands are in [simulator/README.md](../simulator/README.md). API/browser tests reset only the simulated fleet and must not run during an operator demonstration.

## Stop boundary and limitations

This is **REAL GEOGRAPHIC DATA + SIMULATED OPERATIONS + RULE-BASED ESTIMATES**. No trained ML model, calibrated risk probability, field logistics outcome, cascade effectiveness, synthetic research substitute or research-paper result is claimed. Historical acquisition limitations and missing real operational requirements remain documented in [MISSING_DATA_REQUIREMENTS.md](MISSING_DATA_REQUIREMENTS.md).

Operational dependencies, warehouses/docks, legal driver shifts, cascade propagation, automatic decision policy, real-data ML training, OR-Tools, counterfactual baseline experiments and blockchain remain later milestones. Geographic coverage is bounded; unsupported OSM restrictions are conservatively excluded. Routing and speed/incident rules are a demonstration model, without a global joint waiting/routing optimum or commercial navigation certification. Work stops here as requested.
