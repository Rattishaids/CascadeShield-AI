# Reproduce and operate Milestone 4

The canonical workspace is `D:\CascadeShield-AI`. This study trains on **simulated logistics operations and outcomes on real Chennai OSM geography**. The 18 historical research tables remain separate. They do not supply linked Chennai freight, incident causation or real dock/driver outcomes. ODbL attribution and the original road graph are preserved. See the [source audit](../reports/MILESTONE_4_DATA_AUDIT.md), [target definitions](../reports/MILESTONE_4_LABEL_DEFINITIONS.md), [training pipeline](ML_TRAINING_PIPELINE.md), [graph architecture](GNN_ARCHITECTURE.md) and [assessment protocol](MILESTONE_4_BENCHMARK_PROTOCOL.md).

The frozen bundle is [models/milestone4/v1/manifest.json](../models/milestone4/v1/manifest.json). Its SHA-256 is `a225deef5bfe31676129cefa595ef8fb39511486b06e9d0a1d31de40733a3a39`. It records four validated providers, development selection/calibration, actual devices, CPU reload checks, source hashes and serialized model checksums. Final outcomes have now been generated for this study. Re-evaluating these fixed artifacts is reproduction; refitting after inspecting those outcomes would require a new versioned study with a newly declared independent assessment. The existing model directory is immutable and fitting into it is refused.

## Launch the current application

Run from Windows PowerShell:

```powershell
Set-Location D:\CascadeShield-AI
powershell -ExecutionPolicy Bypass -File scripts/start_simulator.ps1 -WithML
# Rebuild after Java changes on this host, using the official-only Maven relay:
powershell -ExecutionPolicy Bypass -File scripts/start_simulator.ps1 -UseMavenRelay -WithML
```

Open **http://127.0.0.1:5173**. Spring Boot health is **http://127.0.0.1:8080/api/health**, ML health is **http://127.0.0.1:8090/health**, and the model registry is **http://127.0.0.1:8090/models**. Startup checks existing database imports and preserves saved simulations, source datasets and volumes. It does not reset, start playback, fit a model or create an experiment job. PostgreSQL/PostGIS uses the existing local port 55432 and Docker volume. Backend restart restores a saved checkpoint paused; no simulation time passes during downtime.

The dashboard and backend bind to localhost. The ML startup helper explicitly binds `0.0.0.0:8090` for Docker's `host.docker.internal` access. This is an unauthenticated local development boundary; public service deployment and production identity are outside the milestone. Python inference cannot write to the Java simulation or database. An outage/timeout/schema mismatch produces labelled deterministic fallback; it never supplies invented trained probabilities or grants action approval. Operator review, explicit approval and transactional execution remain separate.

```powershell
# Start only CPU inference:
powershell -ExecutionPolicy Bypass -File scripts/start_ml.ps1
# Stop only the recorded model service, after offline policy jobs have finished:
powershell -ExecutionPolicy Bypass -File scripts/stop_ml.ps1
# Stop the script-managed frontend/backend; retain PostgreSQL and saved state:
powershell -ExecutionPolicy Bypass -File scripts/stop_simulator.ps1
```

Runtime process identities and logs are under `.runtime/`; use `docker compose -f simulator/compose.yaml logs backend` for Java logs. A different already running model manifest is rejected by the startup helper rather than silently switched. Python's direct service CLI defaults to loopback; use the startup helper for the Docker application.

## Python environments and hardware

Invoke each environment's `Scripts\python.exe` directly. Copied activation scripts and console launchers may retain the old C path. The original `.venv` remains the acquisition/database/browser environment. `.venv-ml` is the isolated Python 3.11 CPU inference/test environment, while `.venv-ml-gpu` is the separate training environment.

The actual setup uses an RTX 4050 Laptop GPU, 6,438,780,928 bytes VRAM, driver 610.74, existing host Torch 2.7.1+cu118, NumPy 2.2.6, scikit-learn 1.7.2, XGBoost 3.1.3 and PyG 2.7.0. CPU inference uses Torch 2.7.1+cpu and XGBoost-CPU 3.1.3. The GPU environment reads the existing host Torch installation through `--system-site-packages`; its training dependencies are local to that environment. No system driver, CUDA toolkit or unrelated installation was replaced. That host Python package may remain on C even though project outputs and environments are on D.

On a fresh environment, use the installed Python 3.11 executable (resolve it with `py -0p`) and create only missing environments:

```powershell
Set-Location D:\CascadeShield-AI
$env:TEMP = Join-Path (Get-Location) '.runtime\tmp'
$env:TMP = $env:TEMP
New-Item -ItemType Directory -Force -Path $env:TEMP | Out-Null
py -3.11 -m venv .venv-ml
.venv-ml\Scripts\python.exe -m pip install --no-cache-dir torch==2.7.1+cpu --index-url https://download.pytorch.org/whl/cpu
.venv-ml\Scripts\python.exe -m pip install --no-cache-dir -r requirements-ml-cpu.txt
# This host already has compatible CUDA Torch; verify it before reusing it:
py -3.11 -m venv --system-site-packages .venv-ml-gpu
.venv-ml-gpu\Scripts\python.exe -m pip install --no-cache-dir -r requirements-ml-gpu.txt
```

Do not run environment creation over the current completed environments simply to repeat the application launch. On another host, a CUDA GPU or compatible host Torch must be verified rather than assumed; use the CPU environment when unavailable. The GPU requirements file intentionally does not install or replace host Torch. See the [D-drive hardware report](../reports/milestone4_environment_d_drive_20261018.json) and [timed compute comparison](../reports/milestone4_compute_comparison.json) for actual execution rather than inferred capability.

```powershell
nvidia-smi
# Choose a fresh output name: existing environment evidence is never overwritten.
.venv-ml-gpu\Scripts\python.exe scripts/audit_ml_environment.py --output .runtime/environment-repeat.json
```

Hardware audit records device model/free/total VRAM, driver, CUDA execution, package/module paths, logical/physical CPUs, available/total RAM and disk capacity. Its tiny matrix/XGBoost probes are engineering fixtures, not research data. Actual development workload timing found CUDA slower for both small GNN variants and XGBoost. The executed main fit used CUDA XGBoost and CPU GNNs; no efficiency gain is claimed. All providers load in the CPU deployment environment.

The graph model uses bounded graph/frame accumulation, fixed seeds, gradient clipping, validation early stopping, saved checkpoints and CUDA memory reporting/recovery. Miniature operational graphs fit as whole graphs; neighbor sampling or mixed precision is not necessary or enabled merely because a GPU exists. See the manifest for executed epoch/device/memory details. GPU permission is not evidence of a useful model or downstream benefit.

## Recheck fixed artifacts without fitting

These commands retain model weights and use current preserved data. Select fresh repeat-report filenames where supported to retain the published evidence:

```powershell
.venv-ml\Scripts\python.exe scripts/verify_milestone4_preservation.py --output .runtime/preservation-repeat.json
.venv-ml\Scripts\python.exe -m unittest discover -s tests -p 'test_ml_*.py' -v
.venv-ml\Scripts\python.exe -m unittest discover -s tests -p 'test_milestone4*.py' -v
.venv-ml\Scripts\python.exe scripts/train_milestone4.py evaluate-validation --reports .runtime/repeat-validation
.venv-ml\Scripts\python.exe scripts/train_milestone4.py evaluate-final --reports .runtime/repeat-final
.venv-ml\Scripts\python.exe scripts/verify_milestone4_inference.py --report .runtime/ml-integration-repeat.json
```

Strict inference immutability verification requires an already stationary live run; the verifier refuses a running simulation rather than pausing it. The read-only browser harness `scripts/test_milestone4_browser.py` exercises provider selection and current display on the documented completed demonstration, writes its named evidence/screenshots, and does not reset the fleet. Acquisition/operational integration harnesses can replace the simulated test fleet; see [simulator/README.md](../simulator/README.md) before using them during a demonstration.

`verify_milestone4_preservation.py` checks only the 86 paths recorded before M4; it does not claim a full Git diff or recount database rows. [Database verification](../reports/milestone4_d_drive_database_verification.json) and [historical cohort validation](../reports/milestone4_historical_database_verification.json) are separate evidence. The workspace had no `.git` repository. [The M4 file inventory](../reports/MILESTONE_4_CHANGED_FILES.md) explicitly distinguishes scoped preservation from reviewed implementation changes.

## Recreate the pre-assessment sequence in a clean study workspace

The following sequence documents the executed design. Use a separate clean, versioned workspace with the source code and preserved real graph, but without this study's generated M4 corpus/model/output directories. Do not delete or clear the current study to make commands accept a rerun. The current `final.jsonl` is already exposed and fitting here is deliberately blocked. A new scientific study also needs new independent final cases and version identifiers; replaying the same cases is not a new independent assessment.

Docker Desktop/Linux engine and the existing Maven cache/official Maven Central relay are prerequisites. The standard startup helper with `-UseMavenRelay` prepares this host's relay; an offline Java experiment does not call the live simulation API. Its default resource limits are a 2 GiB container, four CPUs and 1 GiB Java heap. Do not launch overlapping corpus or policy writers.

```powershell
# 1. Compile/test and declare all 152 scenario INPUTS before producing targets.
.venv-ml\Scripts\python.exe scripts/run_milestone4_experiments.py manifest --compile
# 2. Input-only audit: authorizes development export, not fitting.
.venv-ml\Scripts\python.exe scripts/audit_milestone4_leakage.py
# 3. Export only train/validation/calibration authoritative outcomes.
.venv-ml\Scripts\python.exe scripts/run_milestone4_experiments.py development
# 4. Independently reconstruct all development targets and as-of inputs.
.venv-ml\Scripts\python.exe scripts/audit_milestone4_leakage.py --development
# 5. Measure the fixed development workload before choosing fitting devices.
.venv-ml-gpu\Scripts\python.exe scripts/benchmark_ml_compute.py
# 6. Fit/select on development, calibrate separately, check CPU reload, freeze.
.venv-ml-gpu\Scripts\python.exe scripts/train_milestone4.py fit --device cuda --gnn-device cpu
.venv-ml\Scripts\python.exe scripts/train_milestone4.py evaluate-validation
# 7. Freeze the exact policy source/classes/wrapper/model/development bytes.
.venv-ml\Scripts\python.exe scripts/run_frozen_milestone4_policies.py policies --freeze-only
# 8. Only the frozen model manifest unlocks final outcome generation.
.venv-ml\Scripts\python.exe scripts/run_milestone4_experiments.py final-corpus
# 9. Assess fixed prediction providers. Never fit on final outcomes.
.venv-ml\Scripts\python.exe scripts/train_milestone4.py evaluate-final
# 10. Serve the frozen bundle on CPU and execute all isolated paired policies.
powershell -ExecutionPolicy Bypass -File scripts/start_ml.ps1
.venv-ml\Scripts\python.exe scripts/run_frozen_milestone4_policies.py policies
# 11. Summary refuses incomplete or incompatible paired runs.
.venv-ml\Scripts\python.exe scripts/summarize_milestone4_policies.py
```

The unused initial declaration and input manifest are retained at `config/milestone4_protocol.json` and `data/processed/milestone4/corpus/`. Before fitting, input-only auditing rejected near duplicate operation templates and partial-horizon label masking was corrected. Revision 2 has 64 training, 24 validation, 24 calibration and 40 final scenarios: 112 development and 152 total. Same-seed families, trucks, resources and adjacent frames remain together. Training fleet sizes are 4/8, validation 5/9, calibration 6/10, final 7/11/12. This is a declared fleet-size transfer test on one bounded network/shared templates, with four final seed clusters, rather than IID snapshot, unseen-country or field generalization.

`fit` requires both audits to authorize fitting and binds the protocol, generation manifest, development bytes, graph, ordered feature schema and reviewed source hashes. It refuses final outcomes in the fitting corpus directory and refuses an already published model bundle. For an interrupted unpublished fit, `fit --device cuda --gnn-device cpu --resume` resumes the saved best development checkpoint/optimizer; XGBoost repeats its fixed deterministic development search. This is not an arbitrary-instruction bitwise continuation. A completed frozen bundle must never be resumed for refitting.

## Resume exact policy execution and inspect results

The frozen policy wrapper rejects protocol/model/source/class/development drift and detects a still-active labelled offline container before starting a second writer. After confirming no previous process remains active, repeat the same frozen wrapper command to reuse completed matching case rows and execute missing ones. Existing incompatible or partial evidence is not silently replaced. The service preflight requires the exact frozen manifest and validated providers. Keep the inference service and Docker running until the batch finishes. Do not recompile or edit frozen research source/classes during it.

```powershell
docker ps --filter name=cascadeshield-m4 --format '{{.Names}} {{.Status}}'
.venv-ml\Scripts\python.exe scripts/run_frozen_milestone4_policies.py policies
.venv-ml\Scripts\python.exe scripts/summarize_milestone4_policies.py
```

The predeclared final comparison is 40 cases across 11 policies, or 440 required paired rows. A policy summary is valid only when its `pairedExecutionComplete` flag is true. Individual rows or training success do not prove complete policy execution. Raw outcomes, traces, forecasts, decisions, inference failures/fallbacks and timings live in `reports/milestone4_policy_raw/`; execution command/timing records live in `reports/milestone4_execution_log/`. The completed summary filenames are `reports/MILESTONE_4_POLICY_BENCHMARK.json` and `.csv`. Never present missing or running rows as successful results.

The separate four-case development diagnostic is `scripts/run_frozen_milestone4_policies.py diagnostics`; it has its own immutable implementation freeze and cannot replace the final matched experiment. The original Milestone 3 trace diagnosis is [milestone4_b4_diagnostics.json](../reports/milestone4_b4_diagnostics.json). Original B0–B4 code and M3 outcomes remain unchanged; the new learned B5 score, graph/temporal/ML ablations and optional bounded counterfactual variant have distinct IDs. Equal maximum action/budget/horizon declarations do not guarantee equal realized decisions, eligibility or wall time.

Prediction metrics, eligible denominators, calibration, censoring and failure cases are in [MILESTONE_4_PREDICTION_METRICS.json](../reports/MILESTONE_4_PREDICTION_METRICS.json), its CSV and per-row CSV. The trained model is an associational predictor on untreated simulation trajectories. Candidate action states may shift that distribution, and actual isolated execution is required to assess decisions. No causal action effect, observed logistics prevention benefit, GNN superiority, GPU speedup, commercial navigation certification or result from an unfinished batch is implied.

Source licenses, permission quarantine and missing field requirements remain in the historical inventory. The new generated operational corpus is not a substitute for unavailable real Chennai freight and must keep its simulated provenance when exported. Do not publish private future operational records or credentials if later collected. No cloud GPU cost, system-driver replacement, autonomous LLM, reinforcement learning, blockchain or Milestone 5 work is part of this milestone.
