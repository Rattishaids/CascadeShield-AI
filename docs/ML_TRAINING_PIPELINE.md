# Milestone 4 learning pipeline

This pipeline learns **simulated logistics outcomes on real Chennai geography**. It does not turn the 18 unrelated historical research tables into Chennai freight labels. Historical GB safety, England/Wales sites, Brazilian commerce and Birmingham geography/weather remain separate. The source road graph and ODbL attribution remain unchanged.

## Data and prediction cutoff

`MlCorpusCli` executes the existing authoritative Java simulation in an isolated process. `MlFeatureExtractor` is shared by corpus export, live inference and B5 candidates. The frozen specification is `config/milestone4_protocol_v2.json`; source inputs and hashes are in `data/processed/milestone4/corpus_v2/generation_manifest.json`. The original unused declaration is preserved: an input-only audit rejected near-duplicate split configurations before labels or fitting. Completed scenario JSONL files carry `SIMULATED_RESEARCH_EXPERIMENT` provenance. Future schedules remain in reproduction metadata and are never submitted as model inputs.

Each scenario belongs to one split. The prescribed seeds are disjoint between training, validation, calibration and final assessment; all related families, trucks, targets and adjacent snapshots of a seed stay together. Scenario counts do not equal the number of independently randomized seed groups. Published Milestone 3 seeds 11/22/33/44/55 are rejected by the learning loader. Final outcomes are generated only after `models/milestone4/v1/manifest.json` says `frozen: true`. Fitting refuses a corpus directory that already contains `final.jsonl`, and it refuses to replace a published model manifest.

The input-only audit partitions actual constructed fleet sizes: training 4/8 trucks, validation 5/9, calibration 6/10 and final 7/11/12. Related physical resource groups and continuously near duplicate inputs cannot cross splits. Common scenario templates and three bounded Chennai OD pairs remain shared. This evaluates fleet-size transfer, including extrapolation above the training maximum of eight trucks; it does not establish IID, geographic or independent-operator generalization. Every final-case input was declared before model selection, while its outcomes remained unavailable.

An as-of frame contains the existing `cascadeshield.graph-snapshot/1.0`, its exact clock/fingerprint and the ordered 32-field `cascadeshield.ml-features/1.0` contract. The SHA-256 of its compact ordered JSON name array is `bfb419c7a4fde46112e53aa83a8131e2f1e33526d4d85dda51374de1a828c4d4`. Feature identities, seed, scenario family and private incident schedules are excluded from `x`.

The features cover distance, speed, departure, deadline slack, cargo/capacity, current driver availability/duty/shift, configured dock service/opening/reservation, current occupancy/queue/capacity, already known road exposure, waiting and neighborhood summaries. `rule_road_remaining_sec`, `rule_dock_remaining_sec`, `rule_eta_known`, `graph_in_degree`, `graph_out_degree` and `graph_risk_score` are explicitly **derived rule inputs**, rather than observations. Rule forecasts never become target truth. Missing tabular values remain NaN for XGBoost's learned missing branches. GNN imputation/normalization is fit on training graphs only, with an explicit missing mask.

The supervised corpus follows untreated isolated simulation trajectories. Scores for rerouted or waiting candidate states can therefore encounter a changed action distribution. Their probabilities are predictive associations, without an identified causal treatment-effect interpretation. Downstream policy value must be measured by actually executing the predeclared isolated policy comparisons, including adverse outcomes and deterministic fallback.

`ml/data.py` reuses the existing converter for schema, masks, node/edge endpoint, provenance and future-realization checks. It separately joins later authoritative outcomes to each earlier frame. It does not consume an already realized arrival or completed delivery as a new prediction example.

| Target | Legitimate label | Missing/censored case |
| --- | --- | --- |
| Remaining road arrival seconds | Terminal actual `arrivalSec - predictionClock`, only while not arrived | Unfinished arrival has no regression label |
| Delivery SLA failure | Any carried delivery's actual dock completion after its configured deadline, only while a delivery remains incomplete | A terminal unfinished delivery has no fabricated completion/class label |
| New adverse resource event within 300 seconds | First recorded authoritative DOCK_QUEUE, DOCK_CLOSED, DELIVERY_LATE, DRIVER_BUSY, DRIVER_UNAVAILABLE or SHIFT_EXHAUSTED event strictly after cutoff and within the horizon, linked by resource/truck IDs | This predicts a recorded event onset; continuing effects and causal incident attribution are outside the target |

Because runtime impact IDs are deduplicated, the adverse-event target is explicitly the onset of a **new recorded** event, not every repeated physical queue tick. Successful DELIVERY_COMPLETED events are excluded. Final experiment SLA/unfinished policy metrics retain their existing conservative definition; supervised classification censors unknown completion rather than inventing it. These are different reporting purposes.

## Baselines and algorithms

Identical held-out example IDs are used for distance/speed, conditional rule road ETA, training-mean ETA, slack threshold, known rule dock slack, training SLA prevalence, mathematical graph-risk score and training adverse-event prevalence. Unknown operational ETA is reported with a smaller explicit known-only denominator; it is never silently replaced by zero.

`xgb-v1` fits independent XGBoost histogram models for ETA (`reg:squarederror`), SLA and new adverse-event probability (`binary:logistic`). Development-only alternatives are depth 3/80 trees/learning rate .08 and depth 4/160 trees/learning rate .05. ETA selection minimizes validation MAE; classification selection minimizes validation Brier score. Seed 4001, no row or column sampling, two CPU threads and explicit CPU/CUDA device selection are recorded. `xgb-no-graph-v1` removes exactly the three `graph_*` fields; it retains rule ETA features so the graph ablation does not also remove deterministic travel estimates.

Separate calibration scenarios fit regularized Platt scaling for binary probabilities. A one-class or too-small calibration sample is explicitly uncalibrated. ETA residual intervals use a finite-sample absolute-error order statistic on calibration scenarios. Correlated snapshots mean these intervals are descriptive simulated-domain uncertainty, without an IID or field coverage guarantee. No probability or threshold is fitted on final outcomes.

XGBoost models use stable JSON `save_model`/`load_model`, rather than estimator pickles. This follows the [official model IO guidance](https://xgboost.readthedocs.io/en/stable/tutorials/saving_model.html). GNN details and its genuinely separate trained ETA/SLA/event heads are in [GNN_ARCHITECTURE.md](GNN_ARCHITECTURE.md).

## Environments, GPU and CPU deployment

The original `.venv` and system Python packages are preserved. `.venv-ml` is an isolated Python 3.11 CPU deployment/test environment: NumPy 2.2.6, scikit-learn 1.7.2, XGBoost-CPU 3.1.3, Torch 2.7.1+cpu and PyG 2.7.0. Torch comes from the official CPU wheel index. `.venv-ml-gpu` uses `--system-site-packages` to read the already installed host Torch 2.7.1+cu118, with its own local NumPy/scikit-learn/XGBoost 3.1.3/PyG packages. No CUDA toolkit, graphics driver or system package is replaced. Unused host multimedia packages have incompatible NumPy constraints; they are not imported by this research environment.

The canonical workspace was moved to `D:\CascadeShield-AI`. Invoke each environment's `Scripts\python.exe` directly from that directory: activation/console-script launchers copied from C may retain their original path. `reports/milestone4_environment_d_drive_20261018.json` records the actual D environment paths, GPU execution and disk/RAM availability after the move. The CUDA environment deliberately still reads the existing host CUDA Torch package from its original C installation. Set `TEMP` and `TMP` to a project directory on D for package installation and research execution; source datasets remain unchanged.

CUDA execution was probed on the actual NVIDIA GeForce RTX 4050 Laptop GPU with 6,438,780,928 bytes of device memory. Full XGBoost's actual learner configuration reported `device: cuda:0` and `grow_gpu_hist`. Those engineering probes use explicit test arrays and are not research examples or reported prediction results. Actual model fitting and CPU/GPU work measurements use only the generated development corpus. GPU fitting follows the [official histogram/device API](https://xgboost.readthedocs.io/en/stable/gpu/); package-specific execution is checked rather than inferred from the presence of a GPU.

The trained graph tensors and parameters are placed on the chosen device. Exported weights are CPU tensors. Java inference runs the CPU environment, giving a bounded local deployment dependency. GPU acceleration may be slower for these tiny graphs because kernel launch/transfer cost can dominate; `reports/milestone4_compute_comparison.json` records actual timed work once executed. GPU results are not assumed faster.

## Commands

From the project root, after the isolated Java corpus export has produced development files:

```powershell
.venv-ml-gpu\Scripts\python.exe scripts/benchmark_ml_compute.py
.venv-ml-gpu\Scripts\python.exe scripts/train_milestone4.py fit --device cuda
.venv-ml\Scripts\python.exe scripts/train_milestone4.py evaluate-validation
```

Use `--gnn-device cpu` alongside `--device cuda` when the measured small-graph CPU workload is faster. This records the separate graph-training device without changing architecture, labels or selection criteria. A CUDA request automatically falls back when CUDA is unavailable; bounded frame accumulation and CPU recovery protect GNN fitting against GPU allocation failures.

On the executed fixed development workload, CUDA was slower than CPU for both graph variants and XGBoost ETA fitting. Main GNN fitting therefore uses CPU; the full XGBoost study uses CUDA to retain the authorized GPU-trained experiment with small absolute overhead. GPU execution is not described as an efficiency gain. Work runs on the shared local workstation, and the main fit overlaps a bounded Java regression check; recorded wall times are actual execution costs, rather than controlled hardware-throughput measurements. The failed gate/probe attempts and the corrected binary-target dtype error are preserved in `reports/milestone4_pretraining_execution_events.json`.

Only after model selection/calibration is frozen, generate the final Java corpus with the frozen manifest unlock, then run:

```powershell
.venv-ml\Scripts\python.exe scripts/train_milestone4.py evaluate-final
.venv-ml\Scripts\python.exe scripts/serve_ml.py --models models/milestone4/v1
.venv-ml\Scripts\python.exe -m unittest discover -s tests -p 'test_ml_*.py' -v
```

For an interrupted **unpublished** fit, repeat `fit --device cuda --resume`. XGBoost repeats its deterministic development-only selection; GNN fitting resumes the best saved development checkpoint, optimizer and selected epoch. This is not a bitwise continuation of an arbitrary interrupted instruction. A completed published bundle is immutable. Choose a new model directory/version for a separately declared future study, with a fresh final assessment.

The bundle records feature order/hash, network graph hash, package versions, actual split sizes/seed groups, every development hyperparameter trial, selected GNN epochs, calibration, feature importance, CPU reload checks and artifact checksums. Final evaluation saves full metrics, by-family/severity errors, class distributions, calibration bins, confusion matrices, intervals, measured CPU latency and adverse examples. Empty/one-class metrics remain explicitly undefined. The actual executed counts and results belong in `reports/MILESTONE_4_RESULTS.md`; implementation alone is not training evidence.

The first executed bundle was frozen on 2026-10-18 at 06:44:34 UTC. `models/milestone4/v1/manifest.json` has SHA-256 `a225deef5bfe31676129cefa595ef8fb39511486b06e9d0a1d31de40733a3a39`. It records 412.276 seconds for fitting, calibration and reload work, excluding initial package import and corpus parsing. The 112 development scenarios provided 6,908 truck snapshots: 3,500 training, 1,584 validation and 1,824 calibration. ETA and SLA retain their smaller eligible denominators in the manifest.

| Provider | Actual fitting device | Selected development configuration | CPU reload check |
| --- | --- | --- | --- |
| `xgb-v1` | CUDA | ETA/impact grid trial 1; SLA trial 0 | All three heads equivalent within tolerance |
| `xgb-no-graph-v1` | CUDA | Grid trial 1 for all three heads | All three heads equivalent within tolerance |
| `gnn-static-v1` | CPU | Best epoch 20 of 24 executed | Maximum absolute difference 0 |
| `gnn-temporal-v1` | CPU | Best epoch 16; early stopping after epoch 21 | Maximum absolute difference 0 |

These are fitting and serialization results. Predictive accuracy and downstream prevention value require the separate frozen-model evaluations; training-loss improvement alone establishes neither.

Learned-versus-baseline loss comparisons use identical eligible rows and resample whole seed groups across all families, trucks and snapshots. The predeclared 2,000-replicate bootstrap uses seed 4016 and a descriptive 95% percentile interval. Four final seed groups support limited inference; no independent-row confidence or multiplicity-adjusted superiority claim is made. A single available seed yields an explicitly unavailable interval. Checkpoints and JSON evidence use temporary files followed by replacement, preserving the last complete file if a process stops during a write.
