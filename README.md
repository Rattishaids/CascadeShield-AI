# CascadeShield AI

This workspace acquires and validates real source data, preserves separate research cohorts, and implements explicitly simulated logistics experiments on real Chennai geography. Milestone 4 adds trained XGBoost, heterogeneous GNN and short-history temporal GNN predictors, CPU inference, deterministic fallback and isolated model-assisted policy assessment. These models were trained on simulated operations; they do not establish observed freight accuracy or field effectiveness.

The simulator under `simulator/` includes real Chennai road routing, backend-authoritative simulated trucks, operational warehouses/docks/drivers/deliveries, a separate dependency graph, bounded cascade estimates, operator-reviewed actions and PostgreSQL scenario replay. Read [launch and demonstration instructions](simulator/README.md), [Milestone 2 results](reports/MILESTONE_2_RESULTS.md), and the preserved [Milestone 1 evidence](reports/MILESTONE_1_RESULTS.md). Research data and licensing quarantine are preserved. Operational labels are simulated; no autonomous LLM is run.

Milestone 3 adds isolated executed counterfactuals, B0–B4 comparisons, equal-action controls, ablations, persistent Benchmark Lab jobs and reproducible raw exports. Read [counterfactual implementation](docs/COUNTERFACTUAL_ENGINE.md), [benchmark protocol](docs/BENCHMARK_PROTOCOL.md) and [executed Milestone 3 results](reports/MILESTONE_3_RESULTS.md). Benchmark outcomes are simulated research experiments; historical cohorts remain separate.

The canonical workspace is now `D:\CascadeShield-AI`. Launch the full current application from that directory with `powershell -ExecutionPolicy Bypass -File scripts/start_simulator.ps1 -WithML`, then open **http://127.0.0.1:5173**. The launch preserves saved simulations. Add `-UseMavenRelay` when rebuilding Java on this host. The separate CPU model service runs on port 8090; the backend remains the sole simulation authority.

Read the [Milestone 4 reproduction guide](docs/MILESTONE_4_REPRODUCE.md), [training pipeline](docs/ML_TRAINING_PIPELINE.md), [GNN architecture](docs/GNN_ARCHITECTURE.md), [inference contract](docs/ML_INFERENCE_API.md) and [frozen evaluation protocol](docs/MILESTONE_4_BENCHMARK_PROTOCOL.md). The [frozen model manifest](models/milestone4/v1/manifest.json) records actual fitting, selected configurations and artifact checksums. Predictive results are in [the held-out metrics](reports/MILESTONE_4_PREDICTION_METRICS.json); final downstream policy conclusions require complete paired execution and its separate report. Do not infer decision superiority from a trained model or GPU use.

Read [dataset inventory](reports/DATASET_INVENTORY.md), [download status](reports/DOWNLOAD_STATUS.md), [actual columns](reports/ACTUAL_COLUMNS.md), [data quality](reports/DATA_QUALITY.md), and [missing requirements](reports/MISSING_DATA_REQUIREMENTS.md). Machine-readable reports and provenance are under `reports/` and `data/metadata/`.

## Reproduce on Windows PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-data.txt
.\.venv\Scripts\python.exe scripts/acquire_data.py
.\.venv\Scripts\python.exe scripts/prepare_data.py
.\.venv\Scripts\python.exe scripts/audit_domain_quality.py
.\.venv\Scripts\python.exe scripts/load_postgis.py
.\.venv\Scripts\python.exe scripts/render_reports.py
.\.venv\Scripts\python.exe scripts/validate_artifacts.py
.\.venv\Scripts\python.exe scripts/check_milestone4_legacy.py
```

Configuration is in `config/acquisition.json`. Raw data is never overwritten, transformed, extracted into place or committed to Git. Evidence documents are also checksummed. An existing file with a changed or missing manifest checksum is refused. Preparation rechecks raw hashes, validates full files and emits processed CSVs and manifests; rerunning preparation may replace derived outputs. API errors, HTML challenges and partial Overpass responses are rejected, recorded and never treated as datasets. No alternate sources or synthetic records are substituted.

The exact data-acquisition dependency versions used for this run are in `requirements-data.lock.txt`. Install that file instead of the ranged requirements to reproduce the Python environment. Source data can be revised independently; the raw and processed manifests identify this run's exact bytes. `scripts/validate_artifacts.py` independently scans every processed CSV and checks all original and derived hashes. ML dependencies and tests use separate Python 3.11 environments, as documented in the reproduction guide; the original data environment does not need Torch or XGBoost.

Install `requirements-validation.txt` to additionally parse generated SQL against the PostgreSQL grammar. Grammar validation does not substitute for executing an import on a configured PostgreSQL/PostGIS server. `audit_domain_quality.py` reports official DfT coded-missing labels and counts, historical OSM edit-time and tag coverage, and observed Olist outcome counts.

`acquire_data.py --only olist` (or dft, cambridge, porto, nyc, osm, weather, traccar) retries a source while preserving other provenance. Do not run two acquisition/preparation processes against this workspace at once. To intentionally acquire a changed source release, use a new workspace or explicitly versioned paths; never remove originals just to make a rerun succeed.

Kaggle credentials are read only if locally configured (`~/.kaggle/kaggle.json`, `KAGGLE_CONFIG_DIR`, `KAGGLE_USERNAME` + `KAGGLE_KEY`, or `KAGGLE_API_TOKEN`). If an authentication/terms restriction is encountered, sign in using your own account and rerun. Never commit credentials or send them in chat. Unknown licenses stay unresolved. Porto and NYC have no processed research-use derivatives or database import targets in this run.

## PostgreSQL / PostGIS

`scripts/load_postgis.py` generates schema, client-side COPY and SQL validation scripts using actual processed headers. The schemas keep GB, static England/Wales, Brazil and Birmingham datasets separate. Text staging retains source codes and identifiers; typed views expose selected numeric/timestamp fields. Coordinates use EPSG:4326, with stored point/segment geometry and GiST indexes. There are no invented foreign keys between unrelated datasets.

For an atomic, checksum-verified database load, install `requirements-db.txt`, configure `DATABASE_URL` locally, and run:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-db.txt
.\.venv\Scripts\python.exe scripts/load_postgis.py --execute
psql -f sql/004_validate.sql
```

Alternatively, from this project root run `psql -f sql/003_copy.psql` using standard local PostgreSQL connection environment variables. The psql script refuses populated tables; the Python loader verifies recorded checksums and counts on repeat imports. Neither truncates existing tables. The first execution needs permission to create the PostGIS extension, or an administrator can install it beforehand. Credentials are never written into generated SQL.

Database execution status and available local tooling are recorded in `reports/validation_run.json`. Generated SQL is not evidence of a successful database import. Validation tests use deliberately small fixtures to exercise parsers and safety checks; fixture records are never used as research data or written into `data/raw/`.

## Research boundaries

All selected DfT annual CSVs are complete. OSM is a historical Birmingham geometry subset and weather is a single Birmingham point, both explicitly configured. Cambridge's `bays` is the source authors' modelled estimate. ERA5 is provider-modelled reanalysis. Olist delivery outcomes are observed source dates with documented calendar-day calculations; they must not be used as prediction-time features.

Cambridge's publication date does not establish that a site operated in 2024. No datasets from different countries or periods are joined as one fleet. Accident presence does not establish a causal cascade, and taxi mobility does not supply freight outcomes. The remaining real operational data and permissions are listed in the missing-requirements report. The acquisition pipeline stops at ETL and database preparation. Subsequent simulator and ML milestones use separately labelled, declared simulated operations on real Chennai geography. No historical source records or experimental outcomes are fabricated. Model probabilities and intervals are calibrated within that simulated domain, with no claim of validated field coverage. Work excludes Milestone 5, autonomous LLM execution, reinforcement learning and blockchain.
