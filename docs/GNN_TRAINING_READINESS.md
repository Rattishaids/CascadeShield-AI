# Graph snapshot and GNN training readiness

The export is `cascadeshield.graph-snapshot/1.0`, produced by `GraphSnapshotExporter` and exposed at `GET /api/ai/graph-snapshot`. This GET reads the current simulation snapshot without writing state or the database. `POST /api/ai/graph-snapshots` explicitly persists a copy in `cascadeshield_sim.graph_snapshots` and returns the snapshot ID, schema version, clock and content. It does not move trucks or add an operational outcome. This is an engineering artifact for future heterogeneous graph ingestion. No GNN was trained, no historical logistics labels were manufactured, and no model effectiveness is claimed.

## Snapshot fields

| Field | Meaning |
| --- | --- |
| `schemaVersion` | Exact format version; incompatible versions fail conversion |
| `simulationTime` | Simulated seconds, initial offset-aware clock and computed simulation timestamp |
| `networkId`, `runId`, `scenarioId`, `randomSeed` | Physical graph reference and administrative/scenario replay identity; scenario is null before saving |
| `featureSchemas` | Ordered names, numeric dtypes, units and feature provenance for each node type |
| `nodes` | Typed stable `TYPE:ID` entities, source resource ID, available numeric values and `availableMask` |
| `edges` | Directed type, weight, finite half-open time validity, allowed numeric edge inputs and provenance |
| `predictions` | Separate rule-derived arrival, direct risk, graph risk and dock-time projections; unavailable projections have no record |
| `realizedLabels` | Outcomes measured by the authoritative simulation, emitted only after the associated event occurs |
| `provenance` | Real geography, simulated operations/predictions/outcomes, no trained model, immutable network-source metadata |

The simulation timestamp is derived from the scenario's `initialClockIso` and simulated elapsed seconds; it is not the export's wall-clock date or a claim that the simulated operation occurred then. Network metadata separately records the immutable OSM acquisition timestamp. `randomSeed` is recorded for scenario identity even though the present simulator is deterministic and has no stochastic generator.

The physical OSM network is referenced by network identity and provenance; it is not silently relabeled as an operational graph. Operational nodes are trucks, drivers, docks, deliveries and warehouses configured by the operator. Warehouse coordinates are simulated placements on real geographic coordinates, not observed warehouse records. Driver/resource relationships come only from configured assignments.

Inputs use explicit allowlists. Truck inputs include current speed, traveled/remaining distance, current edge offset, capacity/load, departure/deadline and approved wait schedule. Driver inputs include availability, shift windows and accumulated simulated duty. Dock inputs include service and opening windows. Delivery inputs include load, deadline and configured priority. Warehouse inputs include dock capacity and simulated placement. Current realized arrival, dock completion, delivery lateness, ETA estimates and risk outputs are excluded from `x`. Planned deadlines and known incident schedules are configuration, not future outcomes.

Input values can be null, with `availableMask: false`. A known numerical zero has `availableMask: true`. Outcome labels include `arrival_sec`, `arrival_delay_sec`, `actual_dock_start_sec`, `actual_dock_end_sec`, `delivered_at_sec` and `delivery_lateness_sec` only when measurable. Their provenance is always `SIMULATED_OUTCOME`, with source `AUTHORITATIVE_SIMULATION_ENGINE`. Risk and ETA predictions remain `SIMULATED_PREDICTION`; they are not ground truth for learning a better predictor. Unknown driver-constrained arrival does not produce an operational-arrival target. The conditional road estimate is named separately.

## Conversion

From the project root, choose unused file names, save a fresh snapshot and convert it with the existing Python environment:

```powershell
$snapshotPath = '.runtime/graph-snapshot.json'
$tensorPath = '.runtime/graph-tensor-pack.json'
if ((Test-Path -LiteralPath $snapshotPath) -or (Test-Path -LiteralPath $tensorPath)) {
  throw 'Choose unused snapshot and tensor-pack paths to preserve prior evidence.'
}
New-Item -ItemType Directory -Path .runtime -Force | Out-Null
Invoke-WebRequest http://127.0.0.1:8080/api/ai/graph-snapshot `
  -UseBasicParsing -OutFile $snapshotPath
.venv\Scripts\python.exe scripts/convert_graph_snapshot.py `
  $snapshotPath $tensorPath
```

Choose new output names for later exports. The converter refuses to overwrite its input or an existing output. Its standard-library path writes `cascadeshield.tensor-pack/1.0` and requires neither Torch nor PyG. It validates node/edge identities, declared schemas, directed endpoints, finite numbers, masks, bounded weights, nonempty time intervals and provenance. It rejects future observation timestamps, realized arrival/delivery/dock event timestamps after their observation, duplicate targets and outcome fields inserted into input features. Lateness/delay durations are validated as durations rather than mistaken for event timestamps; a future ETA prediction remains valid in the separate predictions list.

The neutral pack contains per-type `x` and boolean `x_mask`, stable node ID/index mappings, and per-relation `edge_index` of shape `[2, E]`. Edge attributes include weight and valid-from/valid-until seconds; additional permitted numeric features and provenance remain available. Predictions and realized labels are separate lists, with type-specific node indices and source metadata. Missing inputs use an explicit zero fill with a false mask; this is a numerical encoding, not an invented data record. A SHA-256 of canonical source JSON links the pack to its exact source content.

If an environment already has compatible `torch` and `torch-geometric`, the optional path creates and validates a `HeteroData` artifact:

```powershell
python scripts/convert_graph_snapshot.py graph-snapshot.json graph-snapshot.pt --heterodata
```

It maps each node type to `x`, `x_mask`, IDs and feature names; each directed `(source type, relation, destination type)` to its own edge store; and realized outcomes to `y` plus boolean `y_mask`. Within one snapshot, target columns use the sorted realized target names for that node type. A node with no value for an existing target has a false mask; a type with no realized targets has zero target columns. Rule predictions are kept in a separate graph-level field. This follows the [official PyG HeteroData API](https://pytorch-geometric.readthedocs.io/en/stable/generated/torch_geometric.data.HeteroData.html). The optional dependencies are absent on the current host; no dependency is installed automatically and the actual PyG serialization path has not been executed here. Standard-library conversion is covered by automated tests and can run now.

Before combining optional PyG artifacts for training, establish one versioned target vocabulary and align every snapshot's `target_names` and masks to it. The converter does not infer a universal target head, scale heterogeneous units, batch temporal snapshots or fill unavailable labels with observations.

## What remains before training

The current operational graph has no linked observed freight history. Simulated labels are useful for software tests and explicitly synthetic simulator studies, but cannot establish real-world prevention effectiveness. Existing historical GB safety, England/Wales sites, Brazilian e-commerce and Birmingham geography/weather cohorts do not supply a single observed Chennai operation. They remain separate cohorts and are not joined to create training truth.

Real-data training requires a lawful linked regional/temporal corpus: timestamped trips, actual incident exposure, driver assignments/duty, dock reservations/occupancy, warehouse service capacity, deliveries and observed deadlines/outcomes. It also needs missingness/measurement-quality assessment and operator intervention logs. Incident-to-operational causal links must be supported by records rather than inferred from these manually created scenarios.

Future preprocessing must build prediction-time snapshots and later labels separately, record the forecast horizon, and enforce an as-of timestamp for every input. Features known after the prediction cutoff must be excluded. Terminal snapshots can carry outcomes for audit, but must not become examples for predicting an outcome already realized. Rule forecasts and edge types derived from rule forecasts need a documented policy: either exclude them from primary learned evaluation or treat them as explicit baseline-derived inputs and report that design.

Split by time and scenario/operation group before fitting normalization or imputation. Do not put adjacent snapshots from the same run into both train and test sets. Persist feature encodings, units and ordering; record OSM snapshot/graph versions; define observed targets and appropriate baselines; report calibration and coverage separately from errors. An operational model needs an out-of-sample real-data evaluation before any deployment claim.

Replay is deterministic for physical features, dependency records, predictions and outcomes when configuration, command schedule and clock match. Administrative run IDs can differ and are retained for provenance. The schema does not imply that changing random seed creates independent field observations; this implementation has no stochastic operational generator. Conversion does not train, normalize, create a dataset split or claim statistical validity.
