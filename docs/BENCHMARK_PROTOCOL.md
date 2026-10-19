# Milestone 3 reproducible benchmark protocol

All generated cases and outcomes have provenance **SIMULATED_RESEARCH_EXPERIMENT**. Routes use the unchanged, bounded real Chennai OSM graph. Warehouses, docks, drivers, loads, deadlines, incidents and rain effects are manually parameterized simulation inputs. None is an observed freight record, historical rain observation, field experiment or ML training result. Existing historical geographic cohorts remain separate.

## Scenario construction and pairing

`BenchmarkScenarioGenerator.generate(profile, seed, parameters)` validates bounded parameters and builds an actual `SimulationEngine` configuration. It uses the prepared `demoPairs` metadata, verifies connected routes, and places a warehouse exactly at the selected route destination. Each truck receives one delivery, a distinct driver and a consistent warehouse/dock assignment. Docks have opening/service windows; reservations serialize nominal arrivals on each selected dock. A resource can be shared only through these explicit assignments.

The seed controls truck speed (30–42 km/h), simulated load (300–500 kg), small departure jitter, assignment dispersion and initial driver availability. These are declared assumptions, not sampled historical freight distributions. The actual road speed/turn/access restrictions remain those of the prepared network. Vehicle capacity is 1000 kg. Driver and dock windows extend to at least 14,400 simulated seconds to avoid silently introducing a closing-window stressor.

Presets are `closure-contention`, `rain-multiple`, `driver-availability`, and `low-contention`. Every preset can be overridden with the following parameters:

| Parameter | Valid range | General default |
| --- | --- | --- |
| `truckCount` | 2–12 integer | 4 |
| `warehouseCount` | 1–3 integer, bounded by distinct prepared destination pairs | 1 |
| `docksPerWarehouse` | 1–3 integer | 1 |
| `serviceSec` | 1–600 | 180 |
| `deadlineSlackSec` | −300–1800 | 30 |
| `departureGapSec` | 0–600 | 90 |
| `driverUnavailableFraction` | 0–1 | 0 |
| `driverRestoreSec` | 0–3600, within outcome horizon | 300 |
| `closureCount`, `rainSlowdownCount` | 0–3 integer each | 1, 0 |
| `severity` | 0–1 | 1 |
| `incidentDurationSec` | 1–1800 | 240 |
| `incidentStartSec` | 0–1800, before outcome horizon | 10 |
| `simultaneousIncidents` | Boolean | true |
| `horizonSec` | 300–14,400 | 2400 |
| `contention` | 0–1, chance of choosing the first shared dock | 1 |
| `decisionIntervalSec` | 1–300 | 30 |
| `rolloutHorizonSec` | 300–3600 | 1800 |
| `maxDecisions` | 1–64 integer | 12 |

Preset defaults override the general defaults before user overrides. Time parameters must lie on the 0.1-second simulator grid. The outcome horizon must include every configured delivery deadline; a shorter horizon is rejected rather than counting a not-yet-due delivery as an observed missed deadline. Negative deadline slack intentionally creates an initially demanding SLA; it is reported rather than treated as a feasible guarantee. Severity affects simulated slowdown/risk; a closure remains inaccessible during its duration at every severity. Rain means a `SLOWDOWN` assumption on a real selected road segment. No weather API observation is asserted.

The canonical input SHA-256 includes the initial configuration, network identifier, complete private exogenous schedule, horizon, seed and effective parameters. All policies in a paired case get that same input fingerprint. Initial run/scenario UUIDs derive deterministically from those inputs. Each result additionally records an initial physical-state fingerprint. Repeated runs must reproduce realized metrics, decisions and physical state; wall-clock computation measurements can vary.

## Knowledge boundary

Future incident announcements and driver-restoration commands are held in `ScenarioSpec.exogenousSchedule`, outside the policy-visible engine. The runner injects each command at its exact announcement clock. A future command never enters `State.replaySchedule`, initial incidents or policy command history. Current driver availability is visible; an unavailable driver's restoration time is unknown until its restoration command occurs. A currently announced incident's duration is uniformly disclosed to every policy.

Counterfactuals also remove scheduled incidents after the current clock, future commands and replay schedules. They execute the actual deterministic simulator under current knowledge. They do not receive the benchmark's private future incidents or availability restoration. The decision trace stores the observed incident IDs and the observed-state fingerprint. An explicit regression changes an unseen future incident while preserving an earlier decision and its alternative outcomes.

The benchmark outcome engine still receives the full identical schedule for every policy. This distinction permits unexpected future disruptions without hindsight policy selection. No result is selected using the future outcome. No train/test partition or predictive model is developed here. Future ML work must separate scenario families and seeds before training or tuning; these benchmark seeds cannot be reused as an independent held-out efficacy test after tuning on them.

## Policies and allowed actions

| Policy | Full-comparison actions | Decision rule |
| --- | --- | --- |
| B0 | `NONE` | Preserve the original plan; actual road/resource constraints still execute. |
| B1 | `NONE`, `GLOBAL_REROUTE` | Reactive whole-remaining-route planning; minimize projected road arrival, without a dock-outcome objective. |
| B2 | `NONE`, `LOCAL_REROUTE` | Repair the first known affected road segment, retaining connected prefix/suffix and legal turns. Keep the plan if a local repair is unavailable. |
| B3 | `NONE`, `CONTINUE`, `WAIT`, `GLOBAL_REROUTE` | Call the original `AiFallbackPipeline` candidates, copied evaluation and optimizer; normalize projected time 0.65, distance 0.20 and projected operational delay exposure 0.15. No executed rollout. |
| B4 | All modeled actions above plus `LOCAL_REROUTE`, `ADJUST_DOCK_RESERVATION` | Execute independent current-knowledge alternatives, score realized simulated outcomes and select a feasible minimum. |

Global rerouting can reconsider every remaining road edge while preserving an occupied edge, actual position, ordered stops and incoming-turn history. Local rerouting repairs one segment and validates its retained suffix. Neither changes the physical map. Dock adjustment may move a reservation or choose another configured dock at the same warehouse when the interval fits actual occupancy, reservations and opening/service windows. Actual service remains governed by the existing dock runtime.

Reprioritization, driver reassignment and vehicle/delivery transfer are absent because the current model lacks a priority-aware queue rule, physical transfer travel and eligible transfer handling. They are not offered as hypothetical feasible actions. OR-Tools is omitted: this bounded milestone enumerates supported actions and uses existing legal routing, rather than solving a modeled fleet-wide assignment optimization problem.

The **controlled equal-action comparison** gives every policy exactly `NONE`, `CONTINUE`, `WAIT`, `LOCAL_REROUTE`, `GLOBAL_REROUTE`; dock adjustments are excluded. B0 deliberately selects no intervention as the null baseline. B1 minimizes projected road arrival over the common feasible choices, B2 retains its conventional local-repair preference, B3 extends the original copied heuristic objective to the common actions, and B4 uses executed outcomes. Full B3 delegates to the existing optimizer. Its benchmark adapter adds stricter common action constraints and maps a selected unchanged reroute to `NONE`, avoiding a fake reroute count. Controlled B3 extends candidate availability and uses deterministic enum-order ties; it is an explicitly documented port rather than a claim of byte-for-byte identical legacy behavior. Equal availability does not make the policies identical: their decision objectives and choice rules are the treatment. The B3-versus-B4 controlled contrast compares complete decision pipelines with matched action availability; their trigger rules and indirect resource eligibility also differ. The full comparison additionally changes action availability and must not attribute every difference to prediction intelligence.

All action validation remains active for all policies: connected accessible routes, legal turns, capacity, consistent assignments, driver availability/shift, reservation duration/hours and occupied-edge safety. Deadlines are validated and reported as soft SLA constraints: rejecting every already late trip would eliminate the very disrupted cases being evaluated. Hard violations reject the intervention; execution never enters a closed edge, teleports a driver or overbooks physical dock service. A failed alternative is retained as infeasible, with its violations, when submitted through the counterfactual engine. Candidate generation offers currently feasible modeled actions.

## Rollouts and scoring

The authoritative engine advances in fixed 0.1-second ticks. Benchmark observations happen at most every 10 simulated seconds, and exactly at exogenous announcements and configured decision intervals. New cause/conflict signatures are deduplicated per truck; the configured decision budget bounds repeated interventions. Each trace records whether the budget was reached. Resource exposure can nominate an indirect truck for B4; conventional B1/B2 and the original B3 react to directly affected remaining road plans.

Each B4 alternative clones the same observed state and executes until completion or `min(outcomeHorizon, currentClock + rolloutHorizonSec)`. Every compared alternative uses that same absolute horizon. Trials execute actual movements, waits, driver holds, dock queues and delivery completion. Candidate metrics are **realized simulated outcomes under a current-knowledge counterfactual**; they are predictions of the benchmark future, separate from the final policy-run realized metrics. A trial that ends before a delivery deadline still assigns an unfinished-delivery failure proxy for conservative selection; this proxy is not an observed deadline violation. Final benchmark horizons include all deadlines.

Feasible alternative dimensions are min/max normalized at that decision, using only its alternatives. A dimension with no variation contributes zero. Weights are: SLA rate 0.35, total lateness 0.25, downstream resource footprint 0.15, modeled operational cost 0.15, positive additional distance 0.05 and recovery duration 0.05. Deterministic ties prefer action enum order and then action ID. Weights are fixed before execution and are not optimized using the reported benchmark outcomes. This is a bounded action search, not a global optimal dispatch claim.

## Ablations

The same case, hidden schedule, action set and physical runtime are reused for:

| Variant | Effective implementation difference |
| --- | --- |
| B4 full | Forecast temporal exposure, severity-sensitive threshold and executed counterfactual evaluation. |
| `B4_NO_TEMPORAL` | Planning graph and seed impacts use only currently active intervals; future assignment/conflict exposure is removed from risk-driven candidate eligibility. Physical reservations/queues/driver constraints remain enforced. This is an instantaneous graph planning baseline. |
| `B4_NO_ADAPTIVE` | Risk cutoff stays at 0.35 instead of the severity-sensitive 0.15–0.35 threshold, changing which indirect trucks qualify for preventive decisions. |
| `B4_NO_COUNTERFACTUAL` | Preserve B4 resource actions and eligibility, but select with the copied time/distance/operational-exposure heuristic instead of executing alternatives. |

The first two ablations modify the planning copy, leaving authoritative operational constraints intact. A unit test checks that removing forecast interval exposure changes propagated resource scores, and fixed-threshold output differs. Another checks that full B4 alternatives contain executed outcome metrics while the no-counterfactual trace contains heuristic scores without claimed realized trial metrics. A particular benchmark case may still have identical actions/outcomes across variants; such a result is retained.

## Outcome measurements and interpretation

Policy-run metrics are separate from graph risk scores and pre-action ETA. They include SLA violation count/rate, total delivery lateness, distinct downstream disruption resources, reroutes, actual travel distance, signed and positive extra distance, modeled cost, recovery duration, wall-clock decision time and actual audited hard constraint violations. Unfinished deliveries count as SLA failures. Their observed lateness is a horizon lower bound and recovery is censored; they never count as successful on-time deliveries.

The downstream footprint counts distinct resource IDs from realized queue/closed-dock/late-delivery/busy-driver outcomes involving trucks that did not physically encounter an incident. It describes non-direct disruption under configured contention. It does not prove that an incident caused every counted consequence; initially demanding deadlines can also create late outcomes. Direct driver-unavailability records themselves are excluded. Paired policy contrasts, rather than the footprint alone, are needed to assess modeled consequences.

Constraint metrics count unique actual hard invariant audit failures by code/resource reference, at initial/final state, after interventions and the bounded 10-second observations. The audit checks capacity, connected turn-aware remaining topology/current position, assignments/ownership and actual dock service windows/overlap. Rejected selected actions appear separately as `finalSummary.constraintRejections`; candidate filtering is not a physical violation. The audit is not continuous certification: every 0.1-second closure/driver edge-entry gate remains enforced by the original tested simulation engine, while the recorded macro audit provides separate observed evidence.

Additional distance compares actual traveled distance with the paired initial plan. Signed distance can be negative for a shorter reroute or a censored incomplete trip; positive additional distance is reported separately. Cost uses declared illustrative units: distance km + 0.02 × driver duty seconds + 0.01 × dock service seconds + 0.5 × reroutes + 0.25 × dock changes. It is not a financial quote or calibrated operating cost. Recovery is time from the first incident announcement to all delivery completion; unfinished work uses the outcome horizon and is marked censored. It measures completion recovery rather than a fitted road-traffic recovery process.

Repeated cases use the same seeds across policies. Raw rows and traces remain exportable in JSON/CSV, including ties, adverse cases, censored outcomes and computation cost. Summaries report sample size, mean, variation and uncertainty; paired differences must use the same profile/seed/inputs. A finite simulated benchmark can support a claim only about the implemented model, seeds, parameter ranges and actions actually executed. Results cannot establish real-world cascade prevention, calibrated risk accuracy or research efficacy on the unrelated acquired cohorts.

The final executed case list, evidence, aggregate differences, uncertainty procedure and any improvement claim belong in [MILESTONE_3_RESULTS.md](../reports/MILESTONE_3_RESULTS.md). This protocol describes the implemented procedure; it does not supply unexecuted outcomes.

## Declared batch and reproducible execution

[config/benchmark_protocol.json](../config/benchmark_protocol.json) fixes the batch before execution: four profiles, seeds 11/22/33/44/55, five base methods in both comparison modes and three additional full-comparison ablations. This requests 20 unique paired cases and 260 policy outcomes. It uses six decisions per policy run, 30-second decision intervals and 1800-second copied rollouts. The JSON specifies every effective case override; the interactive presets are not the executed batch configuration. Requested counts become executed evidence only when the runner has successfully exported all jobs.

The runner uses existing services and preserves raw per-job exports and a resumable journal. From the project root, with the simulator running:

```powershell
.venv\Scripts\python.exe scripts/run_benchmarks.py
```

The journal refuses a changed protocol in the same output directory. A failed job is saved with its actual error and partial outcomes; the batch stops instead of filling missing rows. Raw JSON includes original scenario configurations, private incident schedules, input fingerprints, observed-state decision fingerprints, alternatives, realized policy metrics and before/after graph snapshots. CSV contains measured policy outcomes. The final report checks identical fingerprints across both modes and unchanged live assignments, commands and completed/paused state.

`scripts/benchmark_statistics.py` aggregates actual-provenance rows only. It reports sample means, sample standard deviations, pooled delivery-weighted SLA rates and paired enhanced-minus-reference differences. Uncertainty uses 2000 deterministic bootstrap replicates, seed 3013, resampling the five seed clusters while keeping all four profiles together. The interval describes this small fixed simulated matrix, has no multiplicity correction and supports no population or field claim. It is reported alongside ties, adverse differences and computational overhead. Censored recovery values remain explicit lower bounds.

The protocol records a prospective seed split (development 11/22/33, reserved assessment 44/55), with all policy runs and snapshots from a seed kept together. No model is fit, tuned or selected here. These published benchmark outcomes must not later be presented as an untouched final ML evaluation after adapting a model to them; a new independently generated held-out assessment is needed then.

Matched action availability controls the action repertoire, while trigger rules and indirect resource eligibility still differ between policies. Thus equal B3/B4 compares the complete decision pipelines; the `NO_COUNTERFACTUAL` ablation is the closer test of executed evaluation alone. The downstream metric's direct/non-direct classification can change when a policy avoids an incident, so its footprint is not a clean causal cascade count. Five seed clusters give fragile descriptive intervals. Fixed policy execution order, JVM warm-up and host contention affect wall-clock timing; the modeled operational cost excludes computation cost.

## Isolated jobs and REST contract

The Benchmark Lab submits only `/api/benchmarks` commands. `BenchmarkService` loads its own immutable graph and has no live `SimulationService` dependency. A single background worker with two queue slots bounds concurrent work; PostgreSQL Flyway V3 adds only `cascadeshield_sim.benchmark_jobs`. Each job records network ID, exact graph SHA-256, frozen request, progress, result/error, timestamps and explicit simulation provenance. Completed results survive backend restart. Interrupted queued/running jobs are marked failed on restart; there is no invented continuation or outcome. Active jobs must finish before intentionally restarting the backend.

| Endpoint | Behavior |
| --- | --- |
| `GET /api/benchmarks/catalog` | Presets, policy action sets, ablations, bounds, score weights, illustrative cost rates and graph identity. |
| `GET /api/benchmarks/runs` | Up to 50 persisted job summaries, newest first. |
| `POST /api/benchmarks/runs` | Frozen `{parameters, policies, comparisonMode, ablations}`; returns persisted job immediately. Parameters include `profile` and a distinct integer `seeds` list. |
| `GET /api/benchmarks/runs/{id}` | Poll status/progress, actual results or saved failure. |
| `GET /api/benchmarks/runs/{id}/export?format=json` | Complete job, configurations, schedules, graphs and traces. |
| `GET /api/benchmarks/runs/{id}/export?format=csv` | Realized policy metrics with paired scenario fingerprints. |

Interactive requests support 2–8 trucks, 1–8 seeds within 0–2147483647 and a 300–7200-second outcome horizon. Invalid parameters return HTTP 400; a full worker queue returns 429. Incomplete export returns 409. Other resource/time bounds above remain active. `FULL` and `EQUAL_ACTIONS` select comparison mode; ablation IDs are `FULL`, `NO_TEMPORAL`, `NO_ADAPTIVE`, `NO_COUNTERFACTUAL` and non-full ablations require B4.

The non-mutating engineering checks are `scripts/test_benchmark_integration.py` and `scripts/test_benchmark_browser.py`. Their small jobs verify infrastructure and are distinct from the declared research batch. They do not reset the existing fleet or execute live approvals.

After an interrupted job, `run_benchmarks.py --retry-failed` archives its actual failure and retries the exact frozen request once per invocation. Failed attempt IDs, progress counters, errors and raw checksums remain in the journal and final JSON; partial progress without persisted outcome rows is not reconstructed or included in the successful corpus.
