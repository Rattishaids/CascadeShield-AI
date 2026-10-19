# Milestone 2 resource API and persistence

The local service is `http://127.0.0.1:8080/api`. Existing road, truck, control, incident, direct operator decision and scenario endpoints remain available. Every manually configured operational resource, relationship, incident and outcome is simulated. Resource definitions are not observed Chennai freight records. Physical geometry continues to come from the immutable Chennai OSM extract.

## Resource contracts

`POST /operations/{kind}` creates a resource, `PUT /operations/{kind}/{id}` edits it, and `DELETE /operations/{kind}/{id}` removes it. Kinds are `warehouses`, `docks`, `drivers` and `deliveries`. Mutations return the authoritative `Models.State`; errors return an HTTP status and `{"error":"..."}`. IDs contain 1–32 letters, digits, underscores or hyphens. Definitions and assignments are editable only at clock zero in a draft; referenced resources cannot be removed. The demonstration is bounded to 50 trucks and 300 operational resources.

| Kind | Actual request columns | Additional runtime columns |
| --- | --- | --- |
| Warehouse | `id`, `name`, `location: {longitude,latitude}`, `dockCapacity` | `nodeId`, `provenance` |
| Dock | `id`, `name`, `warehouseId`, `serviceSec`, `openFromSec`, `openUntilSec` | `status`, `occupiedBy`, `provenance` |
| Driver | `id`, `name`, `available`, `shiftStartSec`, `shiftEndSec` | `status`, `occupiedBy`, `dutySec`, `provenance` |
| Delivery | `id`, `name`, `warehouseId`, `loadKg`, `deadlineSec`, `priority` | `status`, `truckId`, `deliveredAtSec`, `lateSec`, `provenance` |

`dockCapacity` is the permitted number of explicitly configured docks, from 1 to 20; each dock serves one truck at a time. Warehouse placement snaps to a real road node. Its assigned trucks must end at that same node. Resource windows use finite elapsed simulation seconds up to 172800. Dock service is 0.1–86400 seconds. Dock start/end use the engine's 0.1-second grid, rounded up; service cannot start if its rounded finish exceeds closing time. Editing a dock must preserve existing reservation feasibility. Driver windows must contain the baseline road trips; overlapping baseline duties are rejected. Consecutive trips sharing a driver must connect at their adjacent endpoint/start nodes. Driver transfer journeys are not fabricated.

Delivery load is nonnegative; deadlines are positive elapsed seconds, and priority is `NORMAL` or `HIGH`. Priorities are exposed as configured inputs. The current dock queue orders ready time, then truck ID; it does not implement priority scheduling or a global optimizer. Assigned delivery load must fit both truck capacity and its configured cargo. Delivery deadlines apply to completed unloading, whereas the legacy truck deadline/KPI contract applies to road arrival.

`POST /operations/assignments` accepts exactly:

```json
{
  "truckId": "T01",
  "driverId": "DR1",
  "dockId": "D1",
  "deliveryIds": ["DEL1"],
  "reservationStartSec": 900,
  "reservationEndSec": 1200
}
```

This is an example manually simulated input, not a freight observation. IDs must already exist. Assign 1–20 distinct deliveries from the dock's warehouse, with a reservation fitting its opening window and tick-rounded service duration. Shared dock overlaps are modeled as forecast conflicts and actual queues. `DELETE /operations/assignments/{truckId}` removes pre-start dependencies. Assignment runtime columns are `status`, `predictedDockStartSec`, `predictedDockEndSec`, `actualDockStartSec`, `actualDockEndSec`, `queueSec` and `provenance`. A negative unset time is displayed as unavailable. A scheduled `actualDockEndSec` while unloading is an expected service finish; it becomes a realized completion only when the engine reaches that time and completes service. Snapshot export enforces this distinction.

`PATCH /operations/drivers/{id}/availability` accepts `{"available":true}` or `{"available":false}`. Availability must be explicit. This intervention is allowed during a run, recorded for replay, and blocked during a locked replay. Unavailable drivers hold trucks at safe nodes; an occupied edge finishes safely. Arrival can become unknown: `Truck.etaKnown=false`, nullable AI operational ETA, and masked dock forecasts. No restoration time is invented. Piecewise route forecasts are recalculated at a known driver-ready time so a shift/driver wait does not count an expired road closure twice.

## Inspection and AI contracts

| Method/path | Actual output or input |
| --- | --- |
| `GET /operations` | Resources, assignments, predicted/realized impacts, graph, cascade and operational KPIs |
| `GET /operations/graph` | `GraphView` with `schemaVersion`, `clockSec`, `networkId`, typed nodes/edges and provenance |
| `GET /operations/cascade` | `CascadeView` with provider, threshold, iterations, bounded node risks and affected IDs |
| `GET /operations/affected?incidentId=I001` | Above-threshold typed nodes, attributed risks and their directed edges; optional incident filter |
| `GET /incidents/{id}` | Actual simulated incident, directly exposed truck IDs and attributed resource risks |
| `POST /ai/predict` | `PredictionBatch`, fallback source/version and ETA certainty |
| `POST /ai/candidates/{truckId}` | Feasible typed candidates and exact current-state fingerprint |
| `POST /ai/counterfactual` | Exact `CandidateAction` body; copied before/after travel, graph risk and operational projections |
| `POST /ai/validate` | Exact candidate body; blocking errors and disclosed planning warnings |
| `POST /ai/explain` | Exact candidate body; explanation derived from a freshly validated evaluation |
| `GET /ai/recommendations/{truckId}` | Evaluations, deterministic selection and calculated explanation |
| `GET /ai/graph-snapshot` | Read-only `cascadeshield.graph-snapshot/1.0` JSON |
| `POST /ai/graph-snapshots` | Persist snapshot; return its ID, schema, clock and full snapshot |
| `GET /ai/approvals` | Up to 100 approval audit summaries for the current run |
| `POST /ai/approvals` | Exact candidate body; persist `REQUESTED` and its evaluation |
| `POST /ai/approvals/{id}/approve` | `{"approvedBy":"local-operator"}`; explicit local operator review |
| `POST /ai/approvals/{id}/execute` | Empty body; revalidate and consume an `APPROVED` proposal once |

The AI envelope uses `cascadeshield.ai/1.0`; operational graph uses `cascadeshield.operational-graph/1.0`. Keep the entire returned candidate, including its source record. Altered identity, source/version/provenance, recommendation or fingerprint is rejected. Pause before request/review/execution. Changes to clock, route, resource, incident, scenario identity or recorded state stale the proposal. Approval audit does not mutate the reviewed state. The backend prepares the actual command on a separate engine, commits approval consumption plus state/events/resources together, and publishes it only after successful commit. A database/checkpoint/commit failure leaves the previous in-memory state and pending events intact. Inspect durable status after a network error before retrying; consumed actions return a conflict.

The future LLM tool set cannot include the operator approval endpoint. The current `approvedBy` value is an audit label, not authenticated identity. Authentication, actor authorization and explicit wall-clock expiry remain future deployment work. Existing `/decisions` remains the dashboard's direct manual operator path. No autonomous LLM tool client runs in this milestone.

## Database and replay

Flyway V2 adds tables only in `cascadeshield_sim`:

| Table | Actual columns |
| --- | --- |
| `operational_resources` | `run_id`, `resource_type`, `resource_id`, `definition`, `provenance`, `updated_at` |
| `operational_assignments` | `run_id`, `truck_id`, `assignment`, `provenance` |
| `graph_snapshots` | `id`, `schema_version`, `network_id`, `run_id`, `scenario_id`, `clock_sec`, `snapshot`, `operations_provenance`, `created_at` |
| `operator_approvals` | `id`, `run_id`, `clock_sec`, `status`, `state_fingerprint`, `candidate`, `evaluation`, `approved_by`, `requested_at`, `approved_at`, `executed_at`, `provenance` |

The existing `current_state` JSON remains authoritative. Resource/assignment tables are transactional projections; old runs retain separate IDs. Snapshot rows record schema, source network, clock and scenario, with simulated provenance checks. Original road geometry, historical import schemas and earlier Flyway migration are preserved.

Scenario configuration version 2 records initial resources/assignments, original trucks, clock origin, seed, immutable network identity and the actual command schedule, including availability changes. Legacy configurations without operations load an empty resource configuration. Reset restores initial definitions and clears outcomes; replay restores definitions and commands, with new administrative run ID. Completed assignment projections are canonicalized from actual service times so polling frequency cannot change final replay results. Seed 0 is recorded metadata; the current runtime is deterministic and has no stochastic operational generator.
