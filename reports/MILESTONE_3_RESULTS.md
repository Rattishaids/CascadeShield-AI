# Milestone 3: executed counterfactual cascade benchmarks

Completed on 2026-10-14. **REAL GEOGRAPHIC DATA + SIMULATED RESEARCH EXPERIMENTS**. The isolated rollout engine, B0-B4 policies, controlled action comparison, ablations, persistent Benchmark Lab and reproducible exports are implemented. No GNN or autonomous LLM was trained or run.

The declared batch executed **260 policy runs across 20 paired scenarios**, four profiles and five seeds (11, 22, 33, 44, 55). Eight persistent jobs completed: 160 full-comparison outcomes and 100 equal-action outcomes. Every policy and mode retained identical initial configuration and exogenous schedule fingerprints. Raw cases, adverse outcomes, ties and decision traces are preserved.

**The executed matrix does not establish an incremental SLA/lateness benefit from counterfactual evaluation.** Full B4 mean SLA failures were 25.00% versus B3's 41.25%, with higher modeled cost and decision time. With equal actions, B3/B4 both had 41.25% mean SLA failures and 158.96 seconds mean lateness; B4 cost 1.08 more units. The no-counterfactual variant's mean SLA/lateness/cost (23.75%, 118.41 seconds, 93.19 units) were lower than full B4's. The full SLA improvement includes the wider action pipeline, including dock changes and indirect graph eligibility. It cannot be attributed specifically to executed counterfactual evaluation.

## Measured outcomes

Values below are scenario-weighted means over 20 cases per method. SLA mean differs from the separate delivery-weighted pooled rate in JSON. Lateness is total per scenario; cost uses declared illustrative units. Outcome completion and censor counts are reported below.

| Mode | Policy | SLA violations (%) | Lateness (s) | Downstream footprint | Cost (units) | Reroutes | Positive extra distance (m) | Recovery (s) | Decision time (ms/run) |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| FULL | B0 | 72.92 | 676.79 | 2.30 | 98.63 | 0.00 | 0.00 | 1,385.22 | 0.00 |
| FULL | B1 | 41.25 | 158.96 | 4.40 | 93.05 | 2.45 | 442.85 | 1,277.83 | 952.27 |
| FULL | B2 | 73.75 | 605.20 | 3.05 | 98.80 | 0.75 | 615.67 | 1,367.78 | 852.11 |
| FULL | B3 | 41.25 | 158.96 | 4.40 | 93.05 | 2.45 | 442.85 | 1,277.83 | 1,069.06 |
| FULL | B4 | 25.00 | 135.80 | 2.30 | 94.09 | 1.65 | 309.60 | 1,236.02 | 13,119.14 |
| EQUAL_ACTIONS | B0 | 72.92 | 676.79 | 2.30 | 98.63 | 0.00 | 0.00 | 1,385.22 | 0.00 |
| EQUAL_ACTIONS | B1 | 41.25 | 158.96 | 4.40 | 93.05 | 2.45 | 442.85 | 1,277.83 | 1,510.17 |
| EQUAL_ACTIONS | B2 | 73.75 | 605.20 | 3.05 | 98.80 | 0.75 | 615.67 | 1,367.78 | 1,188.81 |
| EQUAL_ACTIONS | B3 | 41.25 | 158.96 | 4.40 | 93.05 | 2.45 | 442.85 | 1,277.83 | 1,396.01 |
| EQUAL_ACTIONS | B4 | 41.25 | 158.96 | 3.75 | 94.13 | 1.95 | 428.28 | 1,279.38 | 9,249.40 |

Across all 260 rows: **0 unfinished deliveries, 0 censored recovery outcomes and 0 measured hard constraint violations**. Rejected proposals are reported separately; they are not counted as executed physical failures.

## Paired differences and uncertainty

Enhanced-minus-reference deltas use identical profile/seed cases; negative means lower. SLA deltas and intervals below are percentage points. Sample variation is available for every metric in JSON. Intervals use 2000 deterministic seed-cluster bootstrap replicates, keeping four profiles together per seed. There are only five independent seed clusters and no multiplicity correction: these are descriptive intervals for this simulated matrix.

| Mode | Reference | SLA delta (pp), 95% interval | Lateness delta (s), 95% interval | Cost delta (units), 95% interval |
| --- | --- | ---: | ---: | ---: |
| FULL | B0 | -47.92 [-56.67, -39.17] | -540.99 [-588.04, -493.94] | -4.54 [-5.28, -3.95] |
| FULL | B1 | -16.25 [-21.25, -12.50] | -23.16 [-51.85, 5.53] | 1.04 [0.50, 1.52] |
| FULL | B2 | -48.75 [-57.50, -40.00] | -469.40 [-521.71, -417.09] | -4.71 [-5.44, -4.10] |
| FULL | B3 | -16.25 [-21.25, -12.50] | -23.16 [-51.85, 5.53] | 1.04 [0.50, 1.52] |
| EQUAL_ACTIONS | B0 | -31.67 [-41.25, -25.42] | -517.83 [-563.15, -481.20] | -4.51 [-5.22, -4.01] |
| EQUAL_ACTIONS | B1 | 0.00 [0.00, 0.00] | 0.00 [0.00, 0.00] | 1.08 [0.50, 1.52] |
| EQUAL_ACTIONS | B2 | -32.50 [-41.25, -26.25] | -446.24 [-483.17, -409.31] | -4.67 [-5.40, -4.16] |
| EQUAL_ACTIONS | B3 | 0.00 [0.00, 0.00] | 0.00 [0.00, 0.00] | 1.08 [0.50, 1.52] |

Sample variation for the main graph/rule and enhanced comparison:

| Mode | Policy | SLA mean +/- sample SD (%) | Lateness mean +/- sample SD (s) | Cost mean +/- sample SD |
| --- | --- | ---: | ---: | ---: |
| FULL | B3 | 41.25 +/- 48.17 | 158.96 +/- 297.29 | 93.05 +/- 35.94 |
| FULL | B4 | 25.00 +/- 33.44 | 135.80 +/- 287.16 | 94.09 +/- 37.55 |
| EQUAL_ACTIONS | B3 | 41.25 +/- 48.17 | 158.96 +/- 297.29 | 93.05 +/- 35.94 |
| EQUAL_ACTIONS | B4 | 41.25 +/- 48.17 | 158.96 +/- 297.29 | 94.13 +/- 37.71 |

## Profile outcomes and adverse cases

The full-comparison B3/B4 profile means expose case dependence; they are not observed freight results.

| Profile | B3 SLA (%) | B4 SLA (%) | B3 lateness (s) | B4 lateness (s) | B3 cost | B4 cost |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| closure-contention | 100.00 | 50.00 | 100.64 | 108.32 | 93.05 | 93.28 |
| rain-multiple | 0.00 | 0.00 | 0.00 | 0.00 | 143.76 | 147.99 |
| driver-availability | 65.00 | 50.00 | 535.20 | 434.88 | 90.55 | 90.25 |
| low-contention | 0.00 | 0.00 | 0.00 | 0.00 | 44.84 | 44.84 |

The independent validator retained **68 B4/reference case comparisons with at least one adverse SLA/lateness/cost/footprint difference** (a case may occur against multiple references). Detailed deltas are in [result validation](milestone3_result_validation.json). This milestone does not establish uniform superiority.

## Ablations

All ablations retain the full-comparison physical constraints and action set. Planning exposure/threshold or executed evaluation alone changes, as documented in the protocol.

| Variant | SLA mean +/- sample SD (%) | Lateness mean +/- sample SD (s) | Cost mean +/- sample SD | Cases with different physical metrics from B4 |
| --- | ---: | ---: | ---: | ---: |
| B4 | 25.00 +/- 33.44 | 135.80 +/- 287.16 | 94.09 +/- 37.55 | 0 |
| B4_NO_TEMPORAL | 27.50 +/- 35.26 | 150.26 +/- 290.84 | 94.08 +/- 37.55 | 2 |
| B4_NO_ADAPTIVE | 25.00 +/- 33.44 | 135.80 +/- 287.16 | 94.09 +/- 37.55 | 0 |
| B4_NO_COUNTERFACTUAL | 23.75 +/- 32.92 | 118.41 +/- 290.52 | 93.19 +/- 35.94 | 13 |

These executed differences justify only the corresponding case-specific simulated outcomes. A variant with no changed physical outcomes provides no measured benefit for that component in this matrix, even though functional tests establish that its implementation changes planning behavior. Full-versus-controlled differences also include the dock action repertoire; they cannot all be credited to counterfactual intelligence.

The batch recorded 822 decisions and 1508 executed hypothetical alternatives, whose forecast metrics remain separate from the 260 realized policy outcomes. The six-decision limit was reached in 83 policy runs; selecting NONE/CONTINUE consumes a decision slot too. Per-policy/mode frequencies and actual selected action counts are recorded in the machine-readable milestone report. The finite budget remains unchanged from the declared protocol.

## Interrupted execution and recovery

1 interrupted attempt(s) are retained separately in the execution journal and failed raw archives. The service shutdown interrupted rain-multiple FULL at recorded progress 30/40; its partial outcome JSON did not survive, so that progress counter is not treated as 30 available measured rows. The runner archived the actual error and retried the full request with identical declared inputs. Completed jobs were reused. The final 260-row corpus contains only complete successful jobs, with no reconstructed or substituted outcomes. Decision timing spans the original and restored JVM sessions and should not be treated as a controlled hardware performance study.

## Implementation and constraints

Each alternative deep-copies identical observed state and executes the existing 0.1-second authoritative simulator. No future incident or unannounced driver restoration enters the planning copy. Supported actions are no intervention, continue, wait, local/global rerouting and feasible same-warehouse dock/reservation changes. Capacity, ownership, connected turn-aware roads, driver windows and dock calendars are validated. Delivery deadlines are soft SLA penalties. Physical audits inspect actual state every 10 seconds and after interventions; original per-tick entry guards remain active.

Full B3 delegates to the existing graph/rule fallback; controlled B3 extends its copied heuristic to the common actions. B4 scores executed current-knowledge alternatives with fixed normalized SLA/lateness/downstream/cost/distance/recovery weights and an explicit unfinished-delivery penalty. Driver/vehicle transfers and priority changes are absent because their physical execution is not modeled. OR-Tools is omitted: bounded candidate enumeration and existing routing provide the implemented search, without a modeled fleet-wide assignment problem or global optimality claim.

The Benchmark Lab provides scenario/seed/policy controls, full/equal-action modes, ablations, asynchronous progress, actual outcome tables, before/after dependency graphs, decision traces and CSV/JSON download. Flyway V3 persists isolated benchmark jobs. Live approval and scenario modules are reused without rewriting them.

## Executed engineering checks

| Check | Passed |
| --- | ---: |
| Java (85 preserved + 39 new; real Chennai included) | 124 |
| Frontend (36 preserved + 14 new) | 50 |
| Python acquisition/geography/conversion/statistics | 33 |
| Isolated API + PostgreSQL (includes 15 malformed-input cases) | 12 |
| Actual browser workflow + exports | 8 |
| Actual backend-container restart + persistence | 5 |

**232 current checks passed**, plus the frontend production build and independent raw/combined 260-row validation. Java had zero failures/errors/skips. Browser had no console/page errors or live mutation requests. Old destructive API/browser harnesses were not rerun against the operator checkpoint; their Milestone 2 evidence remains historical, while all existing unit tests were rerun.

Evidence: [Java](milestone3_java_tests.json), [frontend/build](milestone3_frontend_tests.json), [Python](milestone3_python_tests.json), [API/database](milestone3_integration_tests.json), [browser](milestone3_browser_tests.json), [restart](milestone3_restart_tests.json), [raw outcome validation](milestone3_result_validation.json), [actual lab screenshot](screenshots/milestone-3-benchmark-lab.png), [decision trace screenshot](screenshots/milestone-3-benchmark-trace.png). Engineering validation jobs are excluded from the declared benchmark corpus. Their deliberately short 300-second rollout produced adverse B4 lateness, demonstrating censoring/horizon limitations rather than being suppressed.

## Preserved state, data and provenance

The existing completed three-truck live run stayed at **1,621.0 simulated seconds**. The batch and real container restart preserved its exact API state, PostgreSQL checkpoint, assignments, commands, scenarios and audit events. Frontend: http://127.0.0.1:5173; API health: http://127.0.0.1:8080/api/health.

All 18 eligible historical research tables and **2,414,128 rows** remain unchanged, with recorded checksums/provenance intact. A fresh [artifact audit](milestone3_artifact_validation/validation_run.json) checked all 12 original raw files and all 18 processed files, including every CSV row/header, with zero errors (54 validation records). Source artifacts, processed cohorts, previous reports and licensing quarantine are preserved. GB, England/Wales, Brazil and Birmingham are not joined to simulated Chennai operations. No new observed freight data is claimed.

Real topology is the existing central Chennai OSM extract dated 2026-10-09T05:33:21Z, SHA-256 `38ab5bdea18ca7859daea5a3801f1a5d138d320e29a841aa8d67f00c1c87e80d`. Graph SHA-256 is `c943bac278192042b22342d8e1be898cc68512fb936e314633645bc3e0304e60`: 12,386 nodes, 23,907 directed edges, 14,147 physical map segments and 10 supported turn restrictions. ODbL 1.0/OpenStreetMap attribution and missing-speed assumptions remain in [CHENNAI_NETWORK.md](CHENNAI_NETWORK.md).

## Reproduce and stop boundary

```powershell
powershell -ExecutionPolicy Bypass -File scripts/start_simulator.ps1 -UseMavenRelay
.venv\Scripts\python.exe scripts/run_benchmarks.py
.venv\Scripts\python.exe scripts/validate_benchmark_results.py
.venv\Scripts\python.exe scripts/report_milestone3.py
```

The journal resumes existing jobs and refuses a changed protocol in the same output directory. Use a new output directory for a separately declared fresh execution. Do not restart while jobs are active: interrupted jobs are marked failed. Raw exports/checksums are retained in [BENCHMARK_RESULTS.json](BENCHMARK_RESULTS.json), [CSV](BENCHMARK_RESULTS.csv), `benchmark_raw/` and [execution journal](benchmark_execution_journal.json). Details: [engine](../docs/COUNTERFACTUAL_ENGINE.md), [protocol/API](../docs/BENCHMARK_PROTOCOL.md), [launch instructions](../simulator/README.md).

Limitations: bounded geography and repeated prepared OD pairs; parameterized workloads/weather, uncalibrated rule risk and abstract costs; finite six-decision sequential search rather than a fleet optimum; known active-incident duration but hidden future announcements/restoration; horizon-dependent copied outcomes; five seed clusters and unadjusted descriptive intervals. Equal action availability still permits different graph/trigger eligibility, so the no-counterfactual ablation is the closer component contrast. Downstream direct/non-direct classification is policy-dependent and is not causal cascade attribution. Fixed policy order, JVM warm-up and host load affect decision timing, and computation is excluded from modeled operational cost.

The future seed partition is prospective bookkeeping only. Both groups are published; no model was fit or evaluated, and tuning on these results would require a new held-out ML assessment. These experiments support only the measured model-specific differences above, not uniform superiority or real-world effectiveness. **Work stops after Milestone 3.**
