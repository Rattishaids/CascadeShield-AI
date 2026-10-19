# Typed inference and decision architecture

Milestone 2 implements local, deterministic fallback inference. It prepares replacement boundaries for future Python inference without introducing a learned model, autonomous agent or paid AI service. Spring Boot remains the owner of simulation state, physical movement, operational resource enforcement and action execution. Existing Milestone 1 prediction/prevention services remain usable.

## Public interfaces and stable records

The seven public interfaces are nested in `AiArchitecture`. DTOs are public records in `AiModels`, with schema version `cascadeshield.ai/1.0`. `AiFallbackPipeline` implements every interface and takes `(RoadGraph, ObjectMapper)`. Inference methods accept a state snapshot; they deep-copy it before changing any calculations. No interface can execute an operator action.

| Interface | Contract | Current implementation |
| --- | --- | --- |
| `PredictionProvider` | `PredictionBatch predict(State)` | Piecewise road ETA with known incident schedules, configured driver constraints and operational forecasts |
| `GraphRiskProvider` | `CascadeView graphRisk(State)` | Recomputed operational graph and bounded deterministic graph baseline |
| `CandidateActionGenerator` | `CandidateBatch candidates(State, truckId)` | Currently feasible Continue, Wait and Reroute actions from the existing turn-aware road planner |
| `CounterfactualEvaluator` | `Evaluation evaluate(State, CandidateAction)` | Direct travel estimates and operational projections recomputed on a copied state |
| `ConstraintValidator` | `ValidationResult validate(State, CandidateAction)` | Frozen candidate identity/state checks, capacity, replay lock and disclosed operational warnings |
| `ActionOptimizer` | `CandidateAction optimize(evaluations, clockSec)` | Deterministic normalized objective, with action-name tie breaking |
| `DecisionExplainer` | `Explanation explain(Evaluation)` | Statements and structured facts from calculated before/after estimates |

`Source` records provider, version, provenance, calibration status and limitations. Every fallback source explicitly sets `calibrated: false` and `provenance: SIMULATED_PREDICTION`. `Context` records network, run/scenario IDs, random seed, simulated time and state fingerprint. Run IDs identify administrative executions; equal physical replay results need not have equal run UUIDs.

`TruckPrediction.estimatedArrivalSec` is nullable. An unavailable driver or an exhausted shift can make operational arrival unknown. `conditionalRoadArrivalSec` remains a conditional travel estimate, including applicable configured shift-start or shared-driver timing adjustments; it does not promise dispatch or restore driver availability. Evaluation reports `beforeEtaKnown` and `afterEtaKnown`; an unknown ETA must not be rendered as a confirmed deadline forecast. Direct risk remains an uncalibrated rule score computed from the conditional estimate.

## Read-only counterfactuals and selection

Candidate IDs are deterministic UUIDs derived from the frozen state fingerprint, truck and action. A candidate carries its actual road recommendation ID. Evaluation rejects an unknown action, altered recommendation, unavailable detour or stale fingerprint. Driver swaps, dock swaps, fabricated schedules and unconstrained autonomous actions are not candidates.

For Wait, the copied truck finishes an occupied edge and holds at a safe node according to its incident schedule. For Reroute, the occupied-edge prefix and offset are retained, and the existing planner enforces incoming-way restrictions and ordered stops. Continue clears a prior approved hold, while closures still prevent illegal edge entry. Evaluation never moves the real truck, advances the clock or writes a realized label.

The operational runtime refreshes predicted dock schedules and constraints on each copy. The copied operational graph and graph baseline are then recomputed. Evaluation returns direct before/after ETA and risk, ETA certainty, before/after graph scores, before/after operational impacts and constraint warnings. These are deterministic projections under the known schedule, not measured counterfactual effectiveness or a full alternative future replay.

Capacity violations and recorded-replay interventions are blocking. Predicted resource conflicts remain explicit planning warnings: a safe road mitigation may improve a schedule without resolving every conflict. Actual movement and unloading still obey backend driver availability, edge-entry, ownership and dock-window rules. Assignment creation separately rejects invalid references, load, destination, shift windows and baseline driver overlap. A warning cannot authorize an unsafe entry or restore a failed driver.

Selection minimizes `0.65 × normalized remaining time + 0.20 × normalized remaining distance + 0.15 × normalized summed operational delay`. Normalizers come from feasible alternatives, with a floor of one. Weights are rule assumptions, not learned preferences. All forecast impacts are retained in the objective, so an action can be rejected as inferior when its earlier arrival creates a larger resource queue. This is a bounded demonstration heuristic, not a global joint routing/scheduling optimum.

## REST boundary and approval

The controller exposes these implemented routes. A `POST` inference call still reads a copied state and has no simulation write effect.

| HTTP route | Body | Response/effect |
| --- | --- | --- |
| `POST /api/ai/predict` | None | `PredictionBatch`, including graph risk and operational forecasts |
| `POST /api/ai/candidates/{truckId}` | None | `CandidateBatch` |
| `POST /api/ai/counterfactual` | Exact `CandidateAction` | `Evaluation` |
| `POST /api/ai/validate` | Exact `CandidateAction` | `ValidationResult` |
| `GET /api/ai/recommendations/{truckId}` | None | `RecommendationResult` with evaluations, selection and explanation |
| `POST /api/ai/explain` | Exact `CandidateAction` | Revalidated `Explanation` |
| `GET /api/ai/graph-snapshot` | None | Current versioned snapshot; no persistence/write |
| `POST /api/ai/graph-snapshots` | None | Persists the current snapshot in PostgreSQL and returns its ID and content |
| `GET /api/incidents/{id}` | None | Incident, directly affected truck IDs and attributed resource risks |
| `GET /api/operations/affected?incidentId={id}` | None | Thresholded affected nodes, risks and edges; omit the query to inspect all current causes |

Current state, operational graph and baseline cascade are also available through `GET /api/state`, `GET /api/operations/graph` and `GET /api/operations/cascade`. Incident inspection can include attributed risks below the affected-subgraph threshold; the affected-resource endpoint applies the current severity-sensitive threshold. See [AGENTIC_WORKFLOW_DESIGN.md](AGENTIC_WORKFLOW_DESIGN.md) for the distinct request, operator approval and single-use execution routes. The current fallback API rejects altered candidate source/version records as well as altered action identity.

Approved execution applies the real engine decision to a prepared engine copy. PostgreSQL approval consumption and the prepared state/events are committed in one transaction; only after a successful commit is that engine published as authoritative. A failed checkpoint or failed transaction commit preserves the prior in-memory position, route, clock, commands and pending events. `SimulationApprovalTransactionTest` exercises both failures and successful single-use publication with explicit test-only fixtures and transactional doubles. This is additional engineering evidence, separate from any real logistics outcome.

A future Python model adapter should implement the same input/output contract, preserve provenance and return its exact model version, feature schema and uncertainty/calibration status. Backend validation must reject incompatible network/scenario versions, missing or nonfinite required outputs, stale state, unsupported actions and schema mismatches. Model failure should select the documented fallback and report its source; it must not silently convert an absent prediction into a fabricated value. No Python inference service is installed or called in this milestone.

## Data and future implementation limits

Graph snapshots use a separate training-readiness schema; see [GNN_TRAINING_READINESS.md](GNN_TRAINING_READINESS.md). Historical research cohorts remain geographically and temporally separate. Simulated assignments, cascade estimates and realized simulation labels are never described as observed historical Chennai freight operations.

Before a learned adapter is enabled, the project still needs consented/appropriately licensed linked dispatch, telemetry, warehouse, driver, dock and delivery records; time-based evaluation splits; observed outcome definitions; calibration; feature/version compatibility tests; and an explicit deployment/approval policy. This milestone supplies engineering boundaries and tests, not training evidence or research-effectiveness results.
