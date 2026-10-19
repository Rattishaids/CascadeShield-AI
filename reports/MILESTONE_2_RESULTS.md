# Milestone 2: executed operational dependency and AI architecture results

Completed on **2026-10-13**. The dashboard is running at **http://127.0.0.1:5173** and Spring Boot is healthy at **http://127.0.0.1:8080/api/health**. The current demonstration is a **paused recorded replay at 1000.0 simulated seconds, 1x**, with two simulated trucks, one occupied dock and one queued truck. Both trucks have reached the warehouse; their assigned deliveries have not yet completed. Resume advances the authoritative backend to recorded delivery completion. Reset restores the initial definitions and unlocks manual editing.

The mode remains **REAL GEOGRAPHIC DATA + SIMULATED OPERATIONS + RULE-BASED ESTIMATES**. No observed freight relationships, trained GNN, deep-learning inference, autonomous LLM, calibrated risk probability or field-effectiveness result is claimed.

## Preserved work

Original raw datasets, processed research cohorts, acquisition/ETL scripts, provenance, the Chennai network, Milestone 1 reports and existing tests are preserved. The unchanged historical import evidence covers **18 eligible tables and 2,414,128 rows**. Porto and NYC remain quarantined from research-use imports. Separate GB safety, England/Wales sites, Brazilian e-commerce and Birmingham geography/weather cohorts are not joined to simulated Chennai freight operations.

The physical road graph still uses the original 2026-10-09 OSM extract: 12,386 nodes and 23,907 directed edges. Raw SHA-256: `38ab5bdea18ca7859daea5a3801f1a5d138d320e29a841aa8d67f00c1c87e80d`. Graph SHA-256: `c943bac278192042b22342d8e1be898cc68512fb936e314633645bc3e0304e60`. Geographic provenance and ODbL attribution remain in [CHENNAI_NETWORK.md](CHENNAI_NETWORK.md). New operational provenance is in the [checksummed manifest](../data/metadata/milestone_2_operational_provenance.json).

## Implemented behavior

- Manual simulated warehouses, docks, drivers with availability/shift windows, deliveries with deadlines/priorities, and truck-to-driver/dock/delivery assignments. Validation covers references, warehouse endpoint, cargo/capacity, reservation duration/hours, baseline driver overlap and adjacent connected driver trips. Referenced resources cannot be removed; definitions are editable in a draft.
- Actual sequential dock service, warehouse queues, accumulated driver duty and realized delivery completion/lateness. Occupied road edges finish safely; unavailable/busy/exhausted drivers prevent another edge entry. Piecewise ETA is recalculated at driver-ready time. Unknown availability produces an unknown operational ETA and masked dock forecast.
- Separate JGraphT directed heterogeneous dependency graph with typed/timed/weighted assignment and resource-conflict edges. The deterministic graph baseline uses bounded maximum-product paths per cause, independent-cause combination, safe cycles and a severity-sensitive threshold. Scores are exposure estimates, not calibrated probabilities. Current road-impact trucks are distinguished from seeded constraints and propagated graph risk.
- All seven typed AI interfaces with working local fallback: prediction, graph risk, candidate generation, copied counterfactual evaluation, validation, deterministic action selection and explanations. Before/after consequences are recomputed; read tools do not execute commands.
- Persistent frozen proposal workflow: request, explicit operator approval, exact-state/source validation, and execution once. The actual action is prepared on a separate engine and published only after approval consumption plus state/event/resource checkpoint commit. Rollback/commit failure preserves the previous engine and pending events. Stale, forged, unapproved and consumed proposals fail.
- Versioned graph snapshots with simulation time, schemas, typed directed edges, available-value masks, scenario/seed, predictions and measurable simulated labels. Conversion preserves separate labels/provenance and rejects premature outcomes. No future dock completion is exported as realized.
- Dashboard resource configuration, simulated warehouse/dock markers, driver/assignment timing, directed dependency/risk inspection, and separate predicted/realized consequence timelines. Existing map routing, controls, intervention approval, save/export and replay remain working.

REST fields, validations and V2 tables are documented in [OPERATIONAL_API.md](../docs/OPERATIONAL_API.md). Graph semantics are in [OPERATIONAL_GRAPH.md](../docs/OPERATIONAL_GRAPH.md); typed boundaries in [AI_ARCHITECTURE.md](../docs/AI_ARCHITECTURE.md); conversion/data limits in [GNN_TRAINING_READINESS.md](../docs/GNN_TRAINING_READINESS.md); future tool contracts in [AGENTIC_WORKFLOW_DESIGN.md](../docs/AGENTIC_WORKFLOW_DESIGN.md).

## Executed validation

| Check against final code/build | Actual result |
| --- | --- |
| Full Java suite, including real Chennai graph and all 24 original tests | **85 passed; 0 failures/errors/skips** |
| Original acquisition/ETL/geography plus snapshot-converter Python tests | **28 passed** |
| Frontend suite, including all 21 original tests | **36 passed** |
| Frontend production build with emitted MapLibre worker | Passed |
| Original HTTP/PostGIS workflow | **15 passed** |
| Operational HTTP/PostGIS workflow | **10 passed**, including actual backend restart and unchanged original version-1 scenario replay |
| Original browser workflow | **7 passed** |
| New operational browser workflow | **9 passed; no console/page errors** |
| Actual queue/completed snapshot conversion | Passed: 8 nodes, 12/9 directed edges, 5/12 realized labels |

The 85-test Java run includes 21 resource/runtime cases, 12 graph cases, 10 cascade cases, 11 AI-interface cases, 4 approval-guard cases, 3 transaction failure/success cases and 24 original routing/movement/regression cases. Tests cover multiple inputs, cycles, driver constraints, dock overlap, fractional service/window safety, deadline violations, provenance, deterministic replay and polling-independent completed projections. A non-failing Mockito/JDK instrumentation notice appeared during the Java run.

Browser checks manually created trucks and all operational resources/assignments, selected existing truck/warehouse markers as route endpoints, rendered computed graph and timeline consequences, toggled driver availability, verified a physically held truck and unknown ETA, observed a real queue, downloaded scenario/snapshot JSON, and replayed recorded availability changes exactly. Precise observation steps and the new scenario's closure were issued through the backend API; the original browser workflow separately verified clicked-road injection and operator rerouting.

Machine-readable evidence: [Java](milestone_2_java_tests.json), [Python](milestone_2_python_tests.json), [frontend](milestone_2_frontend_tests.json), [original HTTP](milestone_2_legacy_integration.json), [operational HTTP](milestone_2_integration_tests.json), [original browser](milestone_2_legacy_browser.json), [operational browser](milestone_2_browser_tests.json), [snapshot conversion](milestone_2_snapshot_conversion.json), [completion](MILESTONE_2_RESULTS.json). Actual screenshots: [dashboard](screenshots/milestone-2-dashboard.png), [predicted cascade](screenshots/milestone-2-predicted-cascade.png), [realized queue](screenshots/milestone-2-realized-queue.png).

## Actual computed example cascade

The HTTP example uses two simulated trucks on the same connected real Chennai route, separate drivers and a shared 300-second dock. Truck A departs at 0 s; B departs at 200 s. Their initial reservations are 662.6?962.6 s and 962.6?1262.6 s. B's delivery deadline is 1292.6 s. A manually injected 90-second closure on actual physical segment `1055336210:2` delays A; B encounters that segment after reopening. Only A is directly road-exposed.

| Measured simulator event | Actual time |
| --- | --- |
| A road arrival | 752.5 s |
| A actual dock service | 752.6?1052.6 s |
| B road arrival | 862.5 s |
| B actual dock service | 1052.6?1352.6 s |
| B delivery deadline / completion | 1292.6 / 1352.6 s |
| Realized B delivery lateness | **60.0 s** |

The backend first forecast a shared-dock conflict and dependent deadline exposure, then recorded the queue and actual late completion. Both deliveries completed, with one late delivery and 60.0 s total delivery lateness. Exact road/resource/outcome replay passed. This is deterministic engineering evidence under configured simulated inputs; it is not a research prevention-benefit baseline or a field experiment.

The browser demonstration additionally records driver B becoming unavailable at 1 s and returning at 220 s. At its current 1000 s pause, the dock remains occupied and B is queued; the displayed realized lateness is correctly zero until delivery completion. Demonstration scenario ID: `0964c8fe-cc1a-4bac-ace3-50b55670c38f`. Its saved inputs and command schedule are in [the exported scenario](../reports/milestone_2_exports/dda07d32-e70c-442e-8061-04df155d3578/browser_demonstration_scenario.json).

Immutable per-run engineering exports are in `reports/milestone_2_exports/dda07d32-e70c-442e-8061-04df155d3578/`: [queue snapshot](../reports/milestone_2_exports/dda07d32-e70c-442e-8061-04df155d3578/queue_snapshot.json), [completed snapshot](../reports/milestone_2_exports/dda07d32-e70c-442e-8061-04df155d3578/completed_snapshot.json), [completed tensor pack](../reports/milestone_2_exports/dda07d32-e70c-442e-8061-04df155d3578/completed_tensor_pack.json), and [HTTP scenario](../reports/milestone_2_exports/dda07d32-e70c-442e-8061-04df155d3578/cascade_scenario.json). Existing earlier exports are retained. These artifacts are explicitly simulated engineering evidence and do not enter the main research cohorts.

## Corrected failures and limitations

The first operational replay failed because completed assignment forecast fields retained values from their last polling interval. Completed fields now derive from actual service times; both a polling-frequency regression and real-road replay pass. Browser testing found a real existing-truck marker intercepting a second truck's start selection; marker clicks now choose route endpoints during picking. A separate test-harness close-button selector was corrected. Earlier failed-run evidence is retained in [initial integration failure](milestone_2_integration_initial_failure.json), [marker failure](milestone_2_browser_initial_failure.json) and [selector failure](milestone_2_browser_selector_failure.json). All final checks pass.

Final review also corrected rounded dock closing-time enforcement, edits invalidating existing reservations, three-trip driver transfers, double-counted incident waiting after driver release, the graph's 48-hour validity horizon, premature converter labels and publication before database commit. Regression tests cover these cases.

Torch and PyTorch Geometric are absent. Standard-library tensor conversion was executed; the optional `--heterodata` serialization path is prepared but has not been executed here. Target column names must be aligned across snapshots before a future training corpus is assembled. No dependency is installed automatically and no training or dataset split is performed.

The project still lacks linked observed regional dispatch/telemetry, driver/dock/warehouse assignments, receiving schedules and delivery outcomes. Historical cohorts cannot substitute for that corpus. Priorities are recorded inputs, while the current queue is ordered by ready time and truck ID. Driver windows are simulation constraints, not statutory duty/break rules. Counterfactuals are deterministic projections, not full alternative future experiments or a global joint optimum. The local operator identity is an unauthenticated audit label; production authorization and proposal expiry remain future deployment work.

## Launch and stop boundary

```powershell
powershell -ExecutionPolicy Bypass -File scripts/start_simulator.ps1
# After Java edits on this host:
powershell -ExecutionPolicy Bypass -File scripts/start_simulator.ps1 -UseMavenRelay
```

Use [simulator/README.md](../simulator/README.md) for prerequisites, commands and repeatable checks. API/browser tests replace the simulated demonstration and must run sequentially outside an operator session. Resume the saved replay to finish the recorded cascade; reset to branch and edit its initial resources.

Milestone 2 is complete and ready for later validated inference adapters, graph-dataset tooling and operator-controlled orchestration integration. Real-data ML evaluation remains blocked by missing linked observed operations. **Work stops here: no GNN/deep-learning training or autonomous LLM agent is developed.**
