# CascadeShield simulation control center

React, TypeScript, Vite, and MapLibre GL JS frontend for the first simulator milestone and Milestone 2 operational resources. The Spring Boot service owns simulation time, truck movement, incident effects, routing, risk scores, recommendations, recorded commands, and KPIs. This frontend polls authoritative `/api/state` at most every 150 ms with one outstanding request and sends explicit operator commands. Backend database/persistence health is checked every three seconds and degraded persistence is shown visibly.

Milestone 3 adds an independent **Benchmark Lab** below the operational panel. The live simulator keeps its existing controls, resources and polling. Benchmark jobs use only `/api/benchmarks` endpoints and do not reset or modify the live scenario.

From this directory, with the backend listening at `127.0.0.1:8080`:

```powershell
npm ci
npm run dev
```

Open http://127.0.0.1:5173. Vite proxies `/api` to the backend. See the simulator-level launch instructions for the required PostgreSQL/PostGIS and real Chennai road-network setup.

```powershell
npm run test
npm run build
```

The test suite checks backend command submission, server error handling, tested-pair demo assignment creation, faithful formatting of clocks, risks, signed intervention estimates, operational commands, warehouse/dock relationships, actual delivery load aggregation and deterministic typed graph layout. The production build compiles all TypeScript. Integrated simulation/browser tests belong to the simulator-level suite.

MapLibre 6 uses an explicitly bundled worker imported with Vite's `?worker&url` and configured through `setWorkerUrl`. A map load event alone does not prove vector rendering works. The map's `data-road-network-ready` attribute becomes true only after its real road-hit layer has rendered geometries. Unchanged source data is not resubmitted on every backend poll.

With the backend running, at least one truck configured, and Python Playwright/Chromium installed, verify real vector-road rendering, actual route rendering and road selection without mutating backend operations:

```powershell
..\..\.venv\Scripts\python.exe scripts/map_worker_smoke.py
```

The smoke check writes JSON evidence and a screenshot under `smoke-output/`. Worker/vector errors and public raster-tile failures have distinct messages in the UI.

## Demonstration

1. Use **Add truck**. Select a start and destination on the map, optionally select up to eight intermediate stops, then calculate a road route. Select points close to the visible imported roads; the backend snaps points to real graph nodes and rejects disconnected routes. Configure cargo, speed, driver label, departure and deadline, and add the truck. Repeat to create at least three trucks. The optional **10 trucks** and **20 trucks** convenience buttons submit explicitly simulated assignments using the backend's tested real OSM route pairs. Repeated assignments reuse those verified pairs, reverse them only when the source metadata confirms a return route, and stagger departures by five simulated seconds. Routing still runs in the backend, and rejected routes are reported. Missing tested-pair metadata is reported instead of selecting arbitrary or synthetic locations.
2. Start, pause, resume, step 30 seconds, reset, restart, or change clock speed. Select a fleet row or truck marker to inspect the actual route, speed, load, remaining distance and SLA.
3. Click a road segment. Inject a closure or a severity-based slowdown with a simulation-time duration. The right panel shows active incidents, directly affected trucks and backend-generated wait, continue and reroute alternatives. Approve a feasible action. Watch the actual recorded events and simulated run metrics update.
4. Open **Scenarios**, save the initial trucks, configured operational resources and recorded incident/decision/availability schedule, export saved JSON, or replay a saved scenario. Replay starts paused and executes the saved command schedule on Resume or Step. Operator edits are locked until Reset, which creates an editable branch.

The basemap is attributed public OpenStreetMap raster imagery for low-traffic local development. The imported OSM road layer remains available if basemap requests fail, and the layer button can hide raster imagery. Map rendering requires WebGL. No frontend animation advances or invents simulation state.

Visible labels distinguish **REAL OSM GEOGRAPHY**, **SIMULATED OPERATIONS**, and **RULE-BASED ESTIMATE**. Risk values are uncalibrated scores, not trained predictions or probabilities. Arrival and option comparisons are estimates; the bottom KPIs and timeline reflect recorded simulated state. Missing OSM speed limits use documented backend assumptions.

## Milestone 2 operational resources

The **Operational dependencies** panel extends the existing map and truck controls. Select **Configure resources** while the run is draft at time zero. Create warehouses, docks, drivers and deliveries in order, then use **Assignments** to connect a truck to one driver, one dock and its deliveries. Warehouse locations can be typed or copied from an existing truck's snapped destination. The backend requires that assigned truck destinations and delivery warehouses match the dock warehouse and validates capacity, dock hours, driver shifts and connected driver transfers. Shared dock reservation overlap is forecast and queued during simulation; overlapping reservations are not silently interpreted as independent dock capacity. Errors appear inside the resource dialog.

Driver availability has a separate toggle usable during a run. Configuration edits are locked during active simulation and scenario replay. All resources carry simulated provenance; warehouse/dock map markers do not imply real freight facilities. Docks share their warehouse's configured location. Resource cards display backend driver duty, dock occupancy and delivery status. Assignment cards show configured reservations, predicted service timing, recorded starts and completed service timing. Predicted timing is masked when operational arrival is unknown; ongoing service displays its expected finish without claiming completion. Service starts and completions are also recorded in the backend event timeline and realized consequences.

The directed heterogeneous dependency graph is separate from the real OSM road graph. Select a graph node to inspect available features and risk causes. Arrows show backend dependency direction, validity and weight in tooltips. The affected-resource list uses the backend's threshold. A direct risk is seeded by an identified travel or resource constraint; indirect risk propagates through dependency edges. This classification does not imply every direct seed physically touches a disrupted road. **Predicted** and **Realized** tabs keep forecasts separate from recorded consequences. Operational KPIs count delivered loads only after dock service; a truck's **Road arrival** label is a separate movement outcome. Unknown operational arrivals display explicitly, while road travel estimates remain conditional.

**Graph snapshot** downloads the backend's versioned JSON export from `/api/ai/graph-snapshot`. No graph prediction, truck movement or autonomous action is performed in the frontend. Trained ML/GNN models, autonomous LLM tools and research effectiveness experiments remain outside this milestone.

## Milestone 3 Benchmark Lab

Select a generated scenario profile, configure trucks, simulated warehouses and docks, deadlines, driver availability, road closures and simulated rain slowdowns. Enter distinct random seeds. Every generated case is labelled **SIMULATED RESEARCH EXPERIMENT**, with real OSM roads and configured operational assumptions. No weather observation or historical freight record is implied.

Choose benchmark policies B0 through B4 and inspect their supported actions. **Full policy comparison** uses each method's documented actions. **Equal action set** holds available interventions constant to compare the decision methods. B4 controls expose full enhancement and temporal, threshold and counterfactual ablations. The backend validates all submitted parameters and runs every selected policy from equivalent scenario inputs.

**Run benchmark comparison** submits an isolated queued job, with progress polled independently of live simulation. Completed jobs can be reopened from the history list. The measured comparison includes SLA violations, lateness, downstream resources, reroutes, signed and positive additional distance, modeled cost, recovery, decision computation time, constraint violations and delivery completion. Unfinished deliveries and censored recovery remain visible. Mean ± sample standard deviation cards describe executed cases; no winner, significance or real-world improvement is inferred by the frontend.

Select a result row to inspect the backend's before/after dependency snapshots at the first observed disruption and final outcome and recorded decision trace. Snapshot risk scores remain labelled predictions. Candidate branch outcomes describe simulated projections from that decision's information; final experiment rows describe realized simulated results. Missing snapshots or metrics are reported as unavailable. **Export CSV** and **Export JSON** download actual backend result files.

For a real browser verification of the isolated lab workflow, after the Milestone 3 backend is running:

```powershell
..\..\.venv\Scripts\python.exe ..\..\scripts\test_benchmark_browser.py
```

The test checks lab configuration, job completion, actual metric rows, decision/graph inspection, exports and preservation of the live scenario. It writes separate Milestone 3 evidence and screenshots. No GNN training or autonomous LLM is introduced.

After every benchmark job has finished and the live simulator is stationary, verify persistence with an actual backend container restart:

```powershell
..\..\.venv\Scripts\python.exe ..\..\scripts\test_benchmark_restart.py
```

This harness refuses active benchmark jobs or a running live clock. It makes no scenario or fleet commands and verifies completed benchmark results, the exact live checkpoint, saved scenarios, audit events and historical import counts after restarting only the backend service.
