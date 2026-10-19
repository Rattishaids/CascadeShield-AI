# Executed counterfactual cascade experiments

Milestone 3 adds separate experiment engines around the existing authoritative Chennai road and operational simulator. A trial uses the same immutable road network and a deep copy of the observed simulation state. Its road movement, legal turns, safe occupied-edge completion, driver holds, dock queues, unloading, deadline checks and delivery completion execute through `SimulationEngine` at the existing fixed 0.1-second tick. These experiments never publish their state to the live service or research database cohorts.

Every generated case is a **SIMULATED RESEARCH EXPERIMENT**. Real geographic topology is reused; truck loads, deadlines, resources and interventions are configured simulation inputs. Executed hypothetical trial outcomes are labelled `MODEL_ROLLOUT_FORECAST`. Final benchmark policy outcomes use `SIMULATED_RESEARCH_EXPERIMENT`. Neither constitutes observed logistics evidence or a calibrated effectiveness claim.

## Current knowledge and isolation

`CounterfactualExperimentEngine.observedClone` copies the state and removes replay commands, command history, unannounced future incidents, original operational configuration, and old recommendation/audit projections. It keeps incidents already announced at the observed clock, including their declared duration, current driver availability, actual positions, traveled distance, completed outcomes and actual resource ownership. A fresh engine recomputes road ETA, operational forecasts, graph edges and risk from this sanitized state. This recomputation prevents future knowledge leaking through a previously calculated ETA or dependency edge.

The benchmark runner alone owns the private exogenous event schedule. It injects events into each policy run at the same actual clock. A trial cannot read that schedule. In particular, an unavailable driver has no hypothetical restoration time unless availability changes have already occurred. An unavailable driver can therefore produce a censored trial, rather than an invented completion.

The observed-state SHA-256 excludes audit history, run/scenario UUIDs and hidden schedules. It includes actual operational/road state and recomputed current knowledge. Policy input fingerprints separately cover the full initial configuration and private exogenous schedule for reproducibility; that fingerprint is an identifier, not a policy input feature.

## Supported alternatives

| Action | Actual modeled behavior |
| --- | --- |
| `NONE` | Keep the existing road and resource plan. The runtime still enforces closures, availability, duty windows and dock service. |
| `CONTINUE` | Clear an approved wait and continue the existing connected route. |
| `WAIT` | Wait until the known incident duration ends. An occupied edge finishes first; holding occurs at a safe node. |
| `LOCAL_REROUTE` | Replace the first observed affected segment with a legal detour to its original endpoint. Preserve the remaining prefix and suffix. Reject a repair whose reconnecting turn or ordered stops are invalid. |
| `GLOBAL_REROUTE` | Recalculate the entire remaining route through required ordered stops using current known incidents and turn restrictions. |
| `ADJUST_DOCK_RESERVATION` | Move an unfinished reservation to a feasible interval on the same warehouse's configured dock, including an eligible spare dock. Actual arrival, queue ordering and service continue to determine completion. |

Both reroute types retain an occupied edge as their first edge, preserve its offset and exact position, and keep previous incoming-way history at a road node. They increment the realized reroute count only when applied. A connected detour can be longer or shorter; distances are measured after execution.

Delivery reprioritization is omitted because the existing queue uses ready time and truck ID, rather than configured delivery priority. Driver and vehicle/delivery reassignment are omitted because no modeled driver transfer or cargo transfer establishes spatial eligibility. Offering these actions would imply unsupported operational behavior. The action enum therefore contains only executable actions.

## Feasibility and deadlines

Validation checks truck references, positive cargo capacity, assigned cargo totals, delivery ownership, warehouse endpoint consistency, connected directed roads, legal turns, required stops and occupied-edge continuity. Dock changes must remain at the same warehouse, fit current time/opening/service duration, avoid another configured reservation or actual occupied service, and preserve existing delivery/driver assignments. Active unloading or completed service cannot be moved.

`audit(State)` separately measures physical state invariants: actual cargo, connected legal route/progress and map position, driver/delivery/warehouse ownership, service start after physical arrival, actual dock interval within opening hours and required duration, occupied dock consistency, and nonoverlapping actual service intervals. The benchmark runner and executed trial collect these audits initially, after changes, at bounded 10-second observations and finally. Violations are unique by code plus resource IDs; `Metrics.constraintViolations` counts measured failures. Rejected candidate attempts appear separately in `finalSummary.constraintRejections`. Candidate rejection therefore does not claim an invalid action physically executed. A trial with a measured hard invariant failure is excluded from feasible selection.

The audit is a state inspection, not a reconstruction of every road-entry instant. Within each observation interval, the original engine's 0.1-second movement gates enforce current closure and driver entry constraints; audits do not infer unobserved illegal entries from a later macro snapshot. Finishing an occupied edge remains the documented safety rule.

Interventions cannot promise a road trip while a driver's restoration time is unknown or after the duty window has ended. Executed alternative road ETA must fit the current known driver window. The existing engine independently prevents any actual edge entry that would overrun a shift, so forecast feasibility does not bypass runtime constraints.

Delivery deadlines are **soft constraints**. A late alternative is retained with an explicit `SLA_DEADLINE` warning and penalized by measured SLA/lateness. Rejecting every late alternative would remove the no-intervention comparison and hide disruption harm. Physical/reference/capacity/resource violations are hard rejections. `NONE` and `CONTINUE` preserve a constrained existing scenario, including safe holds, instead of pretending that an intervention can restore an unavailable resource.

No OR-Tools dependency is added. The implemented comparison enumerates the bounded executable alternatives and runs them through the actual simulator; it does not solve a combinatorial fleet-wide assignment problem. A solver would offer no demonstrated advantage for this local finite action set. Selection is sequential and does not claim a global joint optimum.

## Actual metrics and censoring

`ExperimentMetrics.measure` reads completed simulated delivery records. Road arrival alone is not delivery completion. When no operational deliveries exist, it reports the explicit road-trip outcomes instead; it does not create delivery records.

- SLA violation rate counts late completed deliveries **and every unfinished delivery**. An unfinished delivery is never counted as timely because a short horizon ended before its deadline.
- Total delivery lateness sums exact completed lateness and the observable lower bound `max(0, finalClock - deadline)` for unfinished deliveries. Unfinished count and recovery censoring remain separate fields.
- Downstream affected resources are deduplicated typed IDs from actual dock queues/closures, dependent late deliveries, and shared-driver holds. Trucks that physically encountered a road incident are direct exposures; impacts confined to those trucks are excluded from this downstream count. The metric describes realized resource consequences under configured contention, not proof of causality relative to an unobserved field baseline.
- Reroutes count applied route changes. Traveled distance is actual simulator movement. Signed additional distance compares each run's traveled distance with its initial actual distance plus initially planned remaining distance. A censored run can have negative signed distance because it did not finish; positive additional distance clips each truck's difference at zero.
- Recovery is completion clock minus the first announced incident clock. If outcomes remain unfinished, the requested horizon supplies a censored lower bound. This measure includes normal service completion and is not an incident-only queue-dissipation estimate.
- Computation time uses `System.nanoTime()` wall-clock duration. It is separate from simulated time and can vary between repeated deterministic physical outcomes.

Modeled operational cost has abstract units, not rupees or measured commercial expenditure:

| Component | Rate |
| --- | --- |
| Actual vehicle distance | 1 unit/km |
| Actual modeled driver duty | 0.02 units/second |
| Actual dock service elapsed | 0.01 units/second |
| Applied reroute | 0.5 units/change |
| Applied dock reservation/dock change | 0.25 units/change |

Driver duty is the existing runtime's recorded ownership duty; an initial road hold before acquiring a driver is not billed as duty. Vehicle queue waiting is not separately monetized. Cost rates are assumptions in `ExperimentMetrics.COST_RATES`; they are not historical calibration or economic validation.

## Selection objective

At each observed decision, feasible alternatives share one absolute outcome horizon. Each objective uses min/max values among those current alternatives only. An objective with no variation contributes zero. No aggregate test-set outcome, future scenario or policy benchmark maximum is used as a normalizer.

| Objective | Weight |
| --- | --- |
| SLA violation rate | 0.35 |
| Delivery lateness | 0.25 |
| Downstream unique affected resources | 0.15 |
| Modeled operational cost | 0.15 |
| Positive additional distance | 0.05 |
| Recovery time | 0.05 |

The final score is `2 * unfinishedDeliveries + weightedNormalizedObjectives`. The normalized portion is within `[0,1]`, so completing one more delivery always dominates a cheaper censored alternative. This explicit service-completeness penalty prevents cheap stalled trucks winning because they traveled less. Deterministic ties prefer the action enum's stable order, starting with no intervention, then candidate ID. Scores are decision objectives, not probabilities.

## Interfaces and validation

`CounterfactualExperimentEngine` exposes `observedClone`, `fingerprint`, `actions`, `validate`, `audit`, `apply`, `trial`, `runObserved`, `score`, and `choose`. `trial` takes an absolute simulation horizon, executes a copied engine, and returns action feasibility, warnings, projected executed metrics, copied final state, wall-clock computation duration and observed-state fingerprint. Compact decision traces persist candidate metrics and explanations rather than complete alternative states.

The focused `CounterfactualExperimentEngineTest` suite exercises isolation, deterministic copied outcomes, hidden replay/incident/driver-restoration exclusion, ETA recomputation, distinct local/global routes, occupied-edge continuity, disconnected routes, turn restrictions, driver windows, cargo constraints, reservations, active service protection, soft deadlines, censoring, normalization, explicit provenance and actual metric aggregation. Artificial unit-test topology is tagged `TEST_FIXTURE_ONLY` and is never used as acquired research geography.

No GNN training, autonomous LLM, observed freight fabrication or historical cohort join occurs in this engine.

