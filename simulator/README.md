# Simulator developer guide

Use the [root README](../README.md) for Download ZIP setup, configuration, demo, optional ML and stop/start commands. The supported release runs the frontend, Java backend and a fresh PostgreSQL/PostGIS database in Docker. No original developer path, virtual environment, populated database or historical data import is needed for the default demo.

## Authoritative state and routing

`SimulationEngine` owns time, positions, road access, drivers, docks and delivery completion. It advances in fixed 0.1-second steps. Frontend polling renders snapshots and submits commands; it does not independently move trucks. Pause freezes simulated time. Host load may slow playback without skipping physical steps.

Routes use connected directed OSM edges, access filtering, one-way rules and supported node-via turns. Closures affect a physical segment; a truck already occupying an edge finishes safely before holding at a node. Rerouting preserves position, incoming-way history and ordered waypoints. This bounded conservative network is not certified commercial truck navigation.

Road arrival and dock-completed delivery are separate. Driver availability/configured windows constrain edge entry. Shared docks provide sequential service and queues. Unknown availability remains unknown. Graph risk is an uncalibrated deterministic exposure score; forecasts and realized events remain separate.

## Persistence and approval

Flyway migrations under `backend/src/main/resources/db/migration/` create simulator, operational/approval and benchmark tables. The included graph is persisted in PostGIS. State/events are transactional. A persistence failure degrades health and pauses unsafe commands. Restart restores a stationary checkpoint; downtime cannot advance operations.

Scenarios preserve initial definitions and quantized command schedules. Replay starts paused. Administrative run IDs and database timestamps are not expected to match across replays.

Frozen approvals separate request, explicit approval and execution. Execution revalidates the exact paused non-replay state, consumes a one-use approval and publishes a prepared engine only after transaction commit. Unapproved, forged, stale or consumed proposals fail. Local operator IDs are audit labels, not authentication.

## Core REST surface

Endpoints begin with `/api`; Java DTOs/controllers are authoritative. Errors use a non-success HTTP status and an `error` message.

| Endpoint | Behavior |
| --- | --- |
| `GET /health`, `/network`, `/network/roads` | Persistence readiness, metadata and road GeoJSON |
| `GET /state`, `/recommendations` | Authoritative snapshots and current feasible estimates |
| `POST /routes/preview` | Snap/validate connected routing with optional ordered stops |
| `POST /trucks`, `PUT/DELETE /trucks/{id}` | Draft truck creation/edit/removal |
| `POST /control` | START, PAUSE, RESUME, RESET, RESTART, SET_SPEED or STEP |
| `POST /incidents`, `DELETE /incidents/{id}` | Inject or resolve physical-road incidents |
| `POST /decisions` | Approve current feasible CONTINUE/WAIT/REROUTE |
| `GET/POST /scenarios`, `GET /scenarios/{id}` | List/save/export original definitions and schedule |
| `POST /scenarios/{id}/replay` | Restore recorded conditions paused |
| `GET /stream` | Authoritative SSE; current UI uses single-flight polling |

See [operational API](../docs/OPERATIONAL_API.md), [graph semantics](../docs/OPERATIONAL_GRAPH.md) and [typed AI boundaries](../docs/AI_ARCHITECTURE.md) for resources, snapshots and approvals.

## Benchmark and ML boundaries

Benchmark Lab runs isolated B0–B4 engines, persists jobs/traces and exports results without replacing the live fleet. Full/equal-action comparisons differ; see [protocol](../docs/BENCHMARK_PROTOCOL.md) and [counterfactual engine](../docs/COUNTERFACTUAL_ENGINE.md). Restart during an active job records interruption/failure.

Optional CPU ML reads copied states. The backend checks graph/schema/version, clock/fingerprint, truck IDs and finite valid outputs. Missing/invalid/slow inference gives explicit rule fallback with null trained probabilities/intervals. Prediction cannot approve or execute actions. Live operator advice has three actions; the isolated B5 study has a separate five-action repertoire. [ML protocol](../docs/ML_INFERENCE_API.md) documents the contracts.

M4 fitting and assessment are complete, but the primary prevention-success criterion failed. Offline prediction gains did not establish policy benefit. [M4 results](../reports/MILESTONE_4_RESULTS.md) preserve negative findings and limits. Startup never trains or retunes models.

## Development and research reproduction

Container test commands appear in the [root README](../README.md#testing-and-research-reproduction). Optional frontend development with a compatible host Node/npm:

```powershell
Set-Location simulator/frontend
npm ci
npm test
npm run build
npm run dev
```

The Vite development configuration proxies API requests to its configured backend. The container frontend remains the supported release installation.

Legacy API/browser harnesses may replace fleets, save scenarios or restart services; run sequentially against a separate test project/database. Some assume the original container names/ports/scenarios. Artifact-completion validators require omitted raw outputs, corpora and historical source freezes and are not clean-install checks. See [release research scope](../docs/RELEASE_RESEARCH_SCOPE.md).

Historical reports retain original dates, results, hashes and environment commands. They do not supersede current startup. Missing operational labels must never be replaced by unrelated national datasets or reclassified simulated observations.
