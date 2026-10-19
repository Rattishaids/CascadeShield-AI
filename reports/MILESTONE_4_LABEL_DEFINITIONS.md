# Milestone 4 label definitions

Definition date: **2026-10-16**, Asia/Calcutta. These definitions concern **SIMULATED logistics outcomes on real Chennai geography**. No observed Chennai freight target exists. Model-ready field names, eligibility, masks and horizon are versioned in the corpus/schema manifest; this document does not relabel rule forecasts or rolled-out alternatives as truth.

## Prediction cutoff and independent unit

Each example has scenario identity, seed, network fingerprint and a prediction clock `t` in simulated seconds. Inputs are copied from the state available at `t`; the authoritative simulation continues separately to obtain later labels. No future completion, unannounced incident, private exogenous schedule, unknown driver restoration or counterfactual result enters input features. Any rule ETA/risk or forecast-derived dependency edge is explicitly a derived predictor, not an outcome.

The independent split unit is the **scenario/seed/incident-sequence group**, encompassing every policy, counterfactual branch, node and adjacent snapshot from that group. Seeds 11/22/33/44/55 from Milestone 3 are exposed development/history and cannot be fresh final assessment. Final assessment uses frozen new identities; preprocessing and model selection must finish without inspecting its outcomes.

## Remaining road-arrival time

For an active truck not yet arrived at `t`, `remainingArrivalSec = actualRoadArrivalSec - t` when an authoritative future road-arrival event is observed. It measures road arrival, including modeled driver/wait/incident delays, and **excludes later dock queue and service**. It is nonnegative and is measured in seconds at 0.1-second simulator resolution. The associated wall-clock time is an engineered scenario clock, not a measured field timestamp.

If the truck has already arrived, this target is ineligible rather than a trivial zero training example. If no arrival is observed before the generation horizon, `remainingArrivalSec` is null and `arrivalCensored` is true. Do not impute the horizon as a completed arrival or train ordinary squared-error regression on an unresolved lower bound. Such rows remain in censoring/coverage reports and may support a future survival model. Evaluate remaining-time MAE, RMSE and signed prediction-minus-target bias on identical eligible test rows for every predictor; report excluded/censored counts by profile/severity.

`estimated_arrival_sec`, baseline arrival and conditional road ETA are predictions/configuration. They must not serve as the arrival ground truth. Distance/speed and the existing rule ETA are legitimate deterministic baselines with their limitations recorded.

## Delivery deadline violation

For a delivery still undelivered at `t`, the final label is `1` if its authoritative `deliveredAtSec > deadlineSec` and `0` otherwise, using the same numerical tolerance as the existing SLA metric. Delivery completion includes modeled queue and dock service. A truck-level `deliveryLate` means at least one of its actually assigned carried deliveries violates its own deadline. It is not automatically identical to road-arrival lateness.

Already delivered outcomes are ineligible as prospective examples. If final completion is not observed, `deliveryCensored` is true and the ordinary supervised label stays null; incompletion is never a negative example. The benchmark may conservatively count unfinished work as an SLA failure, but that **benchmark penalty is separate from a fully observed binary training label**. Report censoring and operational unfinished counts alongside classification metrics.

SLA risk is a probability estimated by a learned/calibrated classifier. Rule slack thresholds and graph risk scores remain named baselines. Evaluate class counts, precision/recall/F1, confusion matrix, Brier score, PR-AUC and ROC-AUC when both classes exist. A one-class subset produces undefined AUC rather than an invented score. Calibration is fitted on development/validation examples only.

## Future operational impact on a resource

The horizon is **300 simulated seconds**. `futureImpact` indicates a newly recorded authoritative adverse operational impact with occurrence start `s` satisfying `t < s <= min(t + 300, generationHorizon)`. The exact permitted codes are:

- `DOCK_QUEUE`
- `DOCK_CLOSED`
- `DELIVERY_LATE`
- `DRIVER_BUSY`
- `DRIVER_UNAVAILABLE`
- `SHIFT_EXHAUSTED`

`DELIVERY_COMPLETED` is not an adverse impact. Map only the event's actual typed `resourceIds` and referenced `truckIds`; supported output nodes are `TRUCK`, `DRIVER`, `DOCK`, `WAREHOUSE` and `DELIVERY`. Do not add an invented road relationship, warehouse assignment or neighboring impact. `frame.trucks[].labels.futureImpact` and `frame.nodeLabels` derive from these same event occurrences. A node label carries an explicit eligibility mask.

An impact already present at the cutoff is not a future-onset positive. The current implementation records/deduplicates some continuing conflicts, so this target predicts **new recorded event occurrence**, not all occupancy, persistence, physical affectedness or every second of a continuing blockage. Shared-resource references may identify parties linked to the same conflict. A current modeled deadline or queue can cause a later impact without any road incident.

This is an **association target**. It does not prove causal propagation from the injected disruption or that every labeled resource is downstream of it. It differs from Milestone 3's run-level count of non-road-direct resources affected over the entire run, which uses a narrower code filter and direct-exposure exclusion. Keep those names separate.

Negative labels require adequate follow-up: either the whole 300-second window is observed or the operation ends in an absorbing all-work-completed state. At an unfinished generation horizon, an incompletely observed future window must be masked rather than silently declared negative. Corpus validation checks the chosen coverage rule. Lack of an event in a fully observed supported interval is a measured simulator negative; lack of an observed fleet record is not.

Evaluate node class distribution by type/profile, rare positives, calibrated probability metrics and the rule graph-risk baseline on the same eligible nodes. Time-aware graph variants can use known dependency validity/slack at `t`; neither later events nor the future schedule may define their input graph. Existing rule-derived graph weights/validity intervals are explicitly derived features and require an ablation when attributing benefit to learned graph structure.

## Separate observed Brazil label, not used for Chennai training

The existing `delivery_outcomes.csv` has a defensible independent definition: for eligible status-`delivered` orders with both source dates, `late_by_calendar_date = 1[date(actual customer delivery) > date(estimated delivery)]`; `delivery_delay_days` is the calendar-date difference. Missing/ineligible labels remain blank. There are 96,470 eligible rows, 6,534 positive and 89,936 negative. This is **calendar-date order lateness**, not minute-level truck SLA, route travel time, dock duration or cascade.

Training a future separate Brazil model requires a declared purchase/approval/carrier cutoff and excludes customer delivery/status-after-cutoff, reviews and derived outcome fields from features. No such separate model is counted as implemented or trained in this milestone merely because the historical table exists.

## Provenance and failure cases

Target source is `AUTHORITATIVE_SIMULATION_ENGINE` and target category is `SIMULATED_OUTCOME` for the new simulator corpus. The original map remains `REAL_GEOGRAPHIC_DATA`. Model predictions carry their algorithm/artifact/schema/calibration identity and are never called observed real-world outcomes. Missing labels stay null with a mask; numerical zero is meaningful only with availability true. No fabricated records or outcomes fill scarce classes.

Keep final assessment failure cases, severe/rare subsets, masked examples, invalid model inputs and deterministic fallback counts. An accurate offline model can still produce equal or worse decisions; independent paired B3/B4/B5 realized operational outcomes are required to establish any decision benefit.
