# CascadeShield simulator

This simulator provides real Chennai OSM routing, simulated trucks, deterministic road travel, closure/slowdown injection, operational resources, manual approval, recorded outcomes, PostgreSQL persistence and scenario replay. Milestone 4 adds trained simulated-domain prediction providers and a separate read-only CPU inference service. Historical GB/Brazil/England data is retained in separate research schemas and is not presented as Chennai operations.

## Launch on Windows

Prerequisites: Docker Desktop with its Linux engine, Node/npm, the existing Python virtual environment and prepared project data. The current workspace already has these dependencies and downloaded files.

From the repository root in PowerShell:

```powershell
# First build, or rebuild after Java changes:
powershell -ExecutionPolicy Bypass -File scripts/start_simulator.ps1 -Build
# This machine needs the official Maven Central relay for Docker outbound HTTPS:
powershell -ExecutionPolicy Bypass -File scripts/start_simulator.ps1 -UseMavenRelay
# Later launches reuse the image and saved PostgreSQL state:
powershell -ExecutionPolicy Bypass -File scripts/start_simulator.ps1
# Include the existing, checksum-bound trained models:
powershell -ExecutionPolicy Bypass -File scripts/start_simulator.ps1 -WithML
# Rebuild and launch all services on this host:
powershell -ExecutionPolicy Bypass -File scripts/start_simulator.ps1 -UseMavenRelay -WithML
```

Open **http://127.0.0.1:5173**. Backend health: http://127.0.0.1:8080/api/health. The startup script verifies the eligible imports, preserves database volumes and scenarios, and runs the frontend in a hidden background process. Logs are in `.runtime/`; backend logs use `docker compose -f simulator/compose.yaml logs backend`. Stop the script-managed frontend/backend with `powershell -File scripts/stop_simulator.ps1`. PostgreSQL remains available. A frontend launched manually with `npm run dev` is stopped with Ctrl+C in its own terminal.

For separate frontend development:

```powershell
cd simulator/frontend
npm ci
npm run dev
```

The local demonstration database is on `127.0.0.1:55432`, database/user/password `cascadeshield`. Database setup and import evidence: [SIMULATOR_DATABASE_SETUP.md](../reports/SIMULATOR_DATABASE_SETUP.md). The dashboard/backend bind to localhost; the ML helper's explicit development binding is described below. The Maven relay is an optional build helper restricted to the official artifact repository; see [MAVEN_CENTRAL_RELAY.md](../reports/MAVEN_CENTRAL_RELAY.md).

The canonical project directory is `D:\CascadeShield-AI`. Invoke each relocated environment's `Scripts\python.exe` directly; copied activation scripts or package launchers can retain old C-drive paths. `-WithML` launches the CPU Python service with the frozen bundle at `models/milestone4/v1` and verifies its manifest identity. The ML service explicitly listens on `0.0.0.0:8090` so the Docker backend can reach `host.docker.internal:8090`; it is an unauthenticated trusted-local-development service, not a public deployment. `scripts/stop_ml.ps1` stops only its recorded process. `scripts/stop_simulator.ps1` does not stop PostgreSQL or the separate ML service. Run these scripts only after isolated policy experiments have finished if those experiments need the service.

## Demonstration

1. Reset the current run. Remove existing assignments if you want an empty fleet.
2. Add at least three trucks. Click start and destination on the map; optionally select delivery stops. Calculate the route and save the truck. Points must lie within 200 m of a permitted graph node, and all stops must be routable. Vehicle capacity/load, speed and times are validated by the backend.
3. Start; pause, resume, restart or advance 30 seconds. Select 1x/2x/5x/10x. All rendered positions come from backend state.
4. Click a route segment ahead of a truck. Choose closure or slowdown and duration. The incident changes backend travel conditions in both directions of the physical segment. A truck already occupying a newly closed edge finishes it before holding at a safe node.
5. Inspect directly affected trucks, current ETA, bounded rule-based scores and the feasible Continue/Wait/Reroute comparisons. Choose an action and approve it. The current truck position is preserved; no intervention teleports a truck.
6. Inspect events and run outcomes. Delay/late deliveries count completed arrivals; risk and ETA are estimates, not outcomes. Save a named scenario, export its JSON or replay it. Replay starts paused with the original assignments and recorded incident/action schedule. Resume or step to execute it; Reset enables editing a new branch.

The demo fleet button creates connected assignments from three verified real origin/destination pairs. These repeated journeys are explicitly simulated demonstration assignments, not real freight records or research evaluation observations.

## State, routing and estimates

`SimulationEngine` is the single authority. Its clock advances in fixed 0.1 s steps; scheduler ticks apply the selected speed as an integer number of those steps. Pausing freezes clock and movement. Wall-clock scheduler performance can slow playback under load without skipping physical simulation steps. Routes follow connected directed OSM edges, permitted access, one-way directions and supported node-via turn restrictions. Original waypoints retain their order during rerouting. A route query reports impossible connections explicitly.

Snapshot bounds are south 13.04, west 80.24, north 13.095, east 80.29. The network contains 12,386 nodes, 23,907 directed edges and 10 supported node-via restrictions. Unsupported restrictions are conservatively excluded. Source and graph hashes, exact date, filtering and speed assumptions are documented in [CHENNAI_NETWORK.md](../reports/CHENNAI_NETWORK.md) and `data/metadata/chennai_network_provenance.json`. Road geometry is licensed ODbL 1.0 with OpenStreetMap attribution. The basemap needs internet; the downloaded graph and routing remain local.

An edge without an OSM speed tag uses an explicit `SIMULATION_ASSUMPTION`. A slowdown uses `max(0.15, 1 - 0.85 * severity)`; overlapping factors multiply with a 0.05 floor. A closure prevents edge entry. These are demonstration rules, not calibrated traffic/weather models. Known scheduled changes affect ETA calculations. The bounded score combines direct travel delay and deadline exposure and is not a probability. The default decision weights are elapsed time 0.65, extra distance 0.20 and SLA exposure 0.15, normalized across feasible candidates. `PredictionService` and `PreventionService` are interfaces for later validated model/optimization integrations.

PostGIS stores the real graph in `cascadeshield_sim.road_nodes/road_edges`, an immutable network version and provenance, the current state checkpoint, saved scenario configurations and structured events. State writes and events are transactional; a persistence failure pauses the service and is exposed by health. Each operator command is checkpointed, with periodic checkpoints during playback. Backend restart restores the latest checkpoint paused so downtime cannot move trucks. Saved scenarios preserve original assignments and quantized operator command clocks; replay reproduces physical states and KPIs. Run UUIDs, database timestamps and replay loading events are administrative identifiers and are not expected to match.

## REST contract

All endpoints begin with `/api`. Typed DTOs are in `backend/src/main/java/io/cascadeshield/sim/Models.java`; frontend types mirror the exposed state. Errors return a non-success status and `{"error":"message"}`.

| Endpoint | Behavior |
| --- | --- |
| `GET /health`, `/network`, `/network/roads` | Database readiness, network metadata and real road GeoJSON |
| `GET /state`, `/recommendations` | Authoritative clock, truck positions, incidents, estimates, events and KPIs |
| `POST /routes/preview` | `{start,destination,waypoints,maxSpeedKph}`; returns snapped connected geometry and unconditioned baseline distance/time |
| `POST /trucks`, `PUT /trucks/{id}`, `DELETE /trucks/{id}` | Create/edit/remove initial assignments in DRAFT at clock zero |
| `POST /control` | `{action}`: START, PAUSE, RESUME, RESET, RESTART; SET_SPEED with `speed`; STEP with `stepSec` |
| `POST /incidents`, `DELETE /incidents/{id}` | Add scheduled/current physical-segment closure or slowdown; resolve an existing incident |
| `POST /decisions` | `{truckId,action,recommendationId}`; apply a current feasible CONTINUE/WAIT/REROUTE approval |
| `GET/POST /scenarios`, `GET /scenarios/{id}` | List/save/export original assignments and command schedules |
| `POST /scenarios/{id}/replay` | Restore original conditions paused and execute the recorded schedule |
| `GET /stream` | Server-sent authoritative state events; the current UI uses single-flight polling |

## Verification

```powershell
.venv\Scripts\python.exe scripts/check_milestone4_legacy.py
.venv-ml\Scripts\python.exe -m unittest discover -s tests -p 'test_ml_*.py' -v
.venv-ml\Scripts\python.exe -m unittest discover -s tests -p 'test_milestone4*.py' -v
$env:DATABASE_URL='postgresql://cascadeshield:cascadeshield@127.0.0.1:55432/cascadeshield'
.venv\Scripts\python.exe scripts/verify_database.py
.venv\Scripts\python.exe scripts/test_simulator_integration.py
# Optional real backend-container restart check (also changes the test fleet):
.venv\Scripts\python.exe scripts/test_simulator_integration.py --restart-only --report reports/simulator_restart_tests.json
.venv\Scripts\python.exe -m pip install -r requirements-simulator-test.txt
.venv\Scripts\python.exe -m playwright install chromium
.venv\Scripts\python.exe scripts/test_simulator_browser.py
cd simulator/frontend
npm test
npm run build
```

The API/browser harnesses replace only the local simulated fleet and save test scenarios; they preserve research tables and source files. Do not run them simultaneously or during an operator demonstration. Java tests run in the Maven Docker image; the command and actual executed results are recorded in [MILESTONE_1_RESULTS.md](../reports/MILESTONE_1_RESULTS.md). Small unit fixtures are explicitly TESTONLY, outside acquired data and research evaluation.

## Milestone 2 operational resources and AI boundary

Use **Configure resources** below the map to create manually simulated warehouses, docks, drivers and deliveries. Copy a truck's snapped destination when placing its receiving warehouse. Assign each truck to a driver, dock reservation and deliveries from that warehouse. Times are elapsed simulation seconds; resource definitions and assignments are editable in a draft before movement. Driver availability can change during an active run and is recorded for replay. Existing unassigned trucks keep the original road-only behavior.

Road arrival and delivery completion are separate: deliveries complete after actual dock service, with sequential shared-dock queues. Driver availability, shift windows and connected consecutive trips constrain movement at road nodes. A truck already on an edge can finish that edge safely. Driver shifts here are configured simulation windows; statutory duty/break rules are not implemented.

The operational panel displays directed dependencies, seeded and propagated risk, current road-impact trucks, resource timings, and separate predicted/realized consequence timelines. Graph risk is deterministic and uncalibrated. Definitions, semantics, fields, persistence and REST contracts are in [OPERATIONAL_GRAPH.md](../docs/OPERATIONAL_GRAPH.md), [OPERATIONAL_API.md](../docs/OPERATIONAL_API.md), [AI_ARCHITECTURE.md](../docs/AI_ARCHITECTURE.md), [GNN_TRAINING_READINESS.md](../docs/GNN_TRAINING_READINESS.md) and [AGENTIC_WORKFLOW_DESIGN.md](../docs/AGENTIC_WORKFLOW_DESIGN.md).

The future AI tool boundary exposes typed read/evaluation operations and a separate frozen proposal workflow. Pause before requesting review. Request and explicit operator approval are stored in PostgreSQL; execution revalidates the exact current state and publishes a prepared engine only after the approval/checkpoint transaction commits. Unapproved, stale, forged and consumed proposals are rejected. The local operator label is an audit label; production authentication and authorization remain future work.

```powershell
# Tests replace the local simulated demonstration; run sequentially.
.venv\Scripts\python.exe scripts/test_simulator_integration.py --report reports/milestone_2_legacy_integration.json
.venv\Scripts\python.exe scripts/test_operational_integration.py
.venv\Scripts\python.exe scripts/test_simulator_browser.py --report reports/milestone_2_legacy_browser.json --screenshot-prefix milestone-2-legacy
.venv\Scripts\python.exe scripts/test_operational_browser.py
```

The operational integration harness includes a real container restart and exact replay checks. Each run's JSON snapshots are preserved under `reports/milestone_2_exports/<run-id>/`; conversion refuses to overwrite an existing tensor output. The current results and actual screenshots are in [MILESTONE_2_RESULTS.md](../reports/MILESTONE_2_RESULTS.md). Earlier reports remain historical evidence.

## Milestone 3 Benchmark Lab

The **Benchmark Lab** below the operational panel runs isolated seeded experiments on the same real Chennai network. Select a scenario, seeds, B0–B4 methods, full/equal action comparison and optional ablations. Advanced controls bound decision intervals, rollout horizons and decision counts. The lab polls a persistent background job, displays realized SLA/cost/resource outcomes, before/after dependency graphs and observed decision traces, and exports CSV/JSON. It preserves the existing live fleet and approval workflow.

These are **SIMULATED RESEARCH EXPERIMENTS**. Candidate metrics are current-knowledge executed rollout forecasts; final rows are realized simulator outcomes. Rain, workloads, operational cost rates and resources are declared assumptions. Unsupported driver/vehicle transfers and priority changes are not offered.

```powershell
# Execute the fixed research protocol; resumable persistent jobs and raw exports:
.venv\Scripts\python.exe scripts/run_benchmarks.py
# Isolated infrastructure/browser checks; preserve the live run:
.venv\Scripts\python.exe scripts/test_benchmark_integration.py
.venv\Scripts\python.exe scripts/test_benchmark_browser.py
```

Do not restart the backend while an experiment job is active: interrupted jobs are recorded as failed. Completed results persist. The reusable runner refuses a changed protocol in the same output directory and reports failures without substituting outcomes. Implementation, constraints, methods, REST contract and uncertainty are in [COUNTERFACTUAL_ENGINE.md](../docs/COUNTERFACTUAL_ENGINE.md) and [BENCHMARK_PROTOCOL.md](../docs/BENCHMARK_PROTOCOL.md). Actual batch results belong in [MILESTONE_3_RESULTS.md](../reports/MILESTONE_3_RESULTS.md) and its linked raw evidence.

## Milestone 4 prediction and operator review

The **Learned predictions** panel offers the deterministic rule provider, XGBoost, XGBoost without the three graph summaries, a static heterogeneous GNN and a short-history temporal GNN. Click **Predict current snapshot** to evaluate a copied backend state. The display identifies the actual provider/model version, simulated provenance, remaining road-arrival estimate and interval, delivery SLA probability, new adverse-event probability, calibration, latency and warnings. Realized outcomes remain separate. Missing/inapplicable targets remain null. Cold-start temporal context and unsupported resource regimes are disclosed rather than treated as validated observations.

The **ML-assisted operator review** panel compares existing incident-response candidates on state copies. Request review, explicitly approve as an operator and execute through the existing guarded transaction; prediction alone cannot move a truck or approve an action. Revalidation rejects stale state or consumed approval. Live review uses the original three operator actions; the isolated B5 research runner has a distinct five-action repertoire and is not a promise of identical UI behavior.

If Python is unavailable, slow, incompatible or returns invalid values, the complete comparison uses the labelled deterministic fallback, with no calibrated probabilities or fabricated confidence interval. The backend remains authoritative. CPU inference is supported even though the tabular fitting experiment used the GPU. The graph study used CPU after an actual workload comparison found CUDA slower for these small graphs.

```powershell
# Read-only ML/API verification; the live run must already be stationary:
.venv-ml\Scripts\python.exe scripts/verify_milestone4_inference.py --report .runtime/ml-integration-repeat.json
# Read-only browser inference/provider check; requires the documented completed demo:
.venv\Scripts\python.exe scripts/test_milestone4_browser.py
```

The browser script writes its named current evidence files and assumes a completed live run with no incident candidate; use the API verifier for another stationary scenario. It does not reset the simulation. Acquisition/operational API harnesses above do change the test fleet, as documented separately.

Full commands, environment setup, pretraining gates, immutable model selection, exact resumption rules, final assessment and inventory scope are in [MILESTONE_4_REPRODUCE.md](../docs/MILESTONE_4_REPRODUCE.md). See also [ML_INFERENCE_API.md](../docs/ML_INFERENCE_API.md), [ML_TRAINING_PIPELINE.md](../docs/ML_TRAINING_PIPELINE.md), [GNN_ARCHITECTURE.md](../docs/GNN_ARCHITECTURE.md) and the [frozen policy protocol](../docs/MILESTONE_4_BENCHMARK_PROTOCOL.md). Actual final prediction metrics are separate from policy experiments; launching the app does not train, retune or run a benchmark.

## Remaining scope

The system uses real geographic data with simulated operational inputs and realized simulator outcomes. It does not have linked observed Chennai freight records, calibrated field probabilities, an autonomous LangGraph/LLM runtime, legal driver hours certification, global joint route/schedule optimization, field-effectiveness evidence or blockchain auditing. Historical cohorts remain separate and do not become operational training truth. The ML study is a bounded fleet-size transfer experiment on one graph and a small shared OD/template library; adverse learned or policy results must remain visible. Only four final seed groups are independently resampled. Work excludes Milestone 5.
