# Release runtime and research scope

This release packages portable startup, the simulator, its required Chennai graph, optional frozen models and a curated research record. The original workspace, datasets, database and omitted large artifacts remain preserved locally. Packaging does not alter historical benchmark numbers or convert a negative scientific result into a success.

## Included and excluded files

Included: React/TypeScript source/lockfile/tests; Java API/routing/simulation/operational graph/approvals/benchmark source/tests; PostGIS initialization and Flyway V1–V3 migrations; ordinary tracked Chennai OSM-derived `road_graph.json` and `roads.geojson` with provenance; a clearly simulated two-truck shared-dock fixture/loader; optional CPU-compatible model bundle and inference source; useful research tools, metadata, protocols and selected reports.

Excluded: large raw GB safety/Cambridge/Brazil/taxi/weather collections, archives, original research database/dumps, most processed cohorts and training corpora, extensive per-run benchmark/snapshot exports, cached builds, environments, local state, secrets, prompts/conversations/private scratch files. Historical links may refer to artifacts preserved in the original workspace rather than distributed in this ZIP.

No restricted collection is silently replaced by synthetic observations. Independent countries/time periods remain separate cohorts. The historical 18-table/2,414,128-row import statement describes the original workspace; the app release does not create or distribute those rows. Default startup does not require the optional model service or any historical cohort.

## Supported implementation claims

| Milestone | Recorded scope | Interpretation |
| --- | --- | --- |
| 1 | Routing, movement, road incidents, intervention, persistence/replay | Completed engineering vertical slice with simulated operations |
| 2 | Drivers, shared docks/queues, deliveries, dependencies, frozen approvals | Completed integration; constructed cascade examples are not field efficacy |
| 3 | Counterfactual engine, B0–B4, Lab and 260 policy runs | Completed bounded simulator study with action/trigger/compute limitations |
| 4 | Actual trained models, held-out predictions, 440 policy runs/11 methods, guarded inference | Completed assessment; **primary prevention-success criterion not met** |

Historical counts describe their original executions. [Current release verification](../reports/RELEASE_VERIFICATION.md) separately records the staged clean-export test, failures and unverified conditions. An app pass does not show that all historical studies were regenerated, or that a different computer/OS was tested.

M4 supervision is later authoritative simulator outcomes on real OSM geography, not observed freight. Its training/validation/calibration/final sets contain 64/24/24/40 scenarios, with four independent final seed groups. Fleet sizes transfer across splits while the bounded map and small OD/template library remain shared. Final seeds are exposed and cannot be reused as fresh holdout data after tuning.

XGBoost ETA MAE was 59.189 seconds; static GNN had better offline SLA Brier score, without demonstrated prevention benefit. B5-XGBoost mean SLA failures were 49.034% versus B3 47.389%. It tied B4 and the same-algorithm rule control on SLA. Counterfactual XGBoost had no isolated SLA gain and cost more compute. Failed inference/fallback outcomes, correlated observations, under-covering intervals and other qualifications remain in the original report.

## Reproduction levels

**Application:** Follow the root README. Compose creates an isolated database, applies migrations, imports the included graph and launches the UI/API. A clearly simulated demo is loaded only into an empty draft. No old host environment or historical archive is required.

**New experiments:** Benchmark Lab runs new B0–B4 comparisons from included source. Declare parameters, action controls and seeds; preserve failed/censored results. New runs are not regenerated copies of published outcomes. Avoid restarting active jobs.

**Optional inference:** Build/start with `-WithML`. The included CPU-compatible bundle supports all four trained providers. Runtime packaging may differ from the original training launch infrastructure. Its manifest records the historical model/source/artifact freeze, not a promise that all old raw data are in this ZIP. Runtime integrity checks must not pretend omitted training artifacts exist.

**Historical research regeneration:** Acquisition/preprocessing/training documentation remains methodology. Exact old commands may require original environment names, ports/container names, full source datasets, raw exports and historical frozen source state. Do not treat archived absolute-path commands as the release quick start. Reacquire permitted data under applicable licenses, restore the exact required artifacts/source, and use explicit new output locations/protocols when doing new work. Kaggle authentication and restrictions still apply.

**Full artifact audits:** Historical completion validators intentionally expect their full corpus, model/source freeze and raw policy outcomes. Report omitted artifacts as missing. Do not bypass gates or fabricate files to make a curated release pass a full historical audit. These validators answer a different question from whether the app ZIP can start.

## Geography, rights and assumptions

Included graph: source timestamp `2026-10-09T05:33:21Z`, bounds `[13.04, 80.24, 13.095, 80.29]`, SHA-256 `c943bac278192042b22342d8e1be898cc68512fb936e314633645bc3e0304e60`; 12,386 nodes, 23,907 directed edges, 14,147 physical segments, 10 supported restrictions. Preserve [OpenStreetMap attribution](https://www.openstreetmap.org/copyright) and comply with [ODbL 1.0](https://opendatacommons.org/licenses/odbl/1-0/) when adapting/redistributing the database. [Chennai provenance](../reports/CHENNAI_NETWORK.md) records original extraction/filtering and assumptions.

Most speeds, operational timings, workloads, weather effects, costs and driver windows are model inputs. Unsupported access/turn situations are conservatively excluded; this is not commercial navigation certification. No production authentication, field-calibrated freight risk, global fleet optimum, causal learned action effects, autonomous LLM control, blockchain or Milestone 5 is provided.
