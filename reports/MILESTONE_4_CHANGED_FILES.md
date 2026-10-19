# Milestone 4 reviewed file inventory

Reviewed M4 implementation paths and point-in-time evidence hashes. There is no full pre-M4 file tree or Git index; addition/modification labels describe reviewed work, not an independently reconstructed exhaustive Git diff. Only the 86 recorded pre-M4 paths support byte-level preservation claims.

All 86 recorded original assets remained unchanged. This inventory describes reviewed implementation work, not a reconstructed Git diff. Generated raw policy records and corpus files have complete hashes in their own manifests. Dependency environments, node_modules, caches and compiled output are excluded here.

Reviewed implementation files: **73**. Machine-readable bytes and SHA-256: [inventory](MILESTONE_4_CHANGED_FILES.json).

## Data/target metadata

- [data/metadata/milestone_4_data_audit.json](../data/metadata/milestone_4_data_audit.json) - M4_ADDITION.
- [data/metadata/milestone_4_label_definitions.json](../data/metadata/milestone_4_label_definitions.json) - M4_ADDITION.

## Existing documentation/launch/frontend integration

- [.gitignore](../.gitignore) - M4_MODIFICATION.
- [README.md](../README.md) - M4_MODIFICATION.
- [scripts/start_simulator.ps1](../scripts/start_simulator.ps1) - M4_MODIFICATION.
- [simulator/README.md](../simulator/README.md) - M4_MODIFICATION.
- [simulator/frontend/src/App.tsx](../simulator/frontend/src/App.tsx) - M4_MODIFICATION.
- [simulator/frontend/src/types.ts](../simulator/frontend/src/types.ts) - M4_MODIFICATION.

## Experiment declarations

- [config/milestone4_protocol.json](../config/milestone4_protocol.json) - M4_ADDITION.
- [config/milestone4_protocol_v2.json](../config/milestone4_protocol_v2.json) - M4_ADDITION.

## Final evidence and reproducibility

- [scripts/VerifyMilestone4Replay.java](../scripts/VerifyMilestone4Replay.java) - M4_ADDITION.
- [scripts/audit_milestone4_results.py](../scripts/audit_milestone4_results.py) - M4_ADDITION.
- [scripts/check_milestone4_ml_tests.py](../scripts/check_milestone4_ml_tests.py) - M4_ADDITION.
- [scripts/diagnose_milestone4_predictions.py](../scripts/diagnose_milestone4_predictions.py) - M4_ADDITION.
- [scripts/finish_milestone4.py](../scripts/finish_milestone4.py) - M4_ADDITION.
- [scripts/plot_milestone4_results.py](../scripts/plot_milestone4_results.py) - M4_ADDITION.
- [scripts/report_milestone4.py](../scripts/report_milestone4.py) - M4_ADDITION.
- [scripts/validate_milestone4_completion.py](../scripts/validate_milestone4_completion.py) - M4_ADDITION.

## Isolated dependency specifications

- [requirements-ml-cpu.txt](../requirements-ml-cpu.txt) - M4_ADDITION.
- [requirements-ml-gpu.txt](../requirements-ml-gpu.txt) - M4_ADDITION.

## Java M4 contract tests

- [simulator/backend/src/test/java/io/cascadeshield/sim/MlCorpusTest.java](../simulator/backend/src/test/java/io/cascadeshield/sim/MlCorpusTest.java) - M4_ADDITION.
- [simulator/backend/src/test/java/io/cascadeshield/sim/MlInferenceClientTest.java](../simulator/backend/src/test/java/io/cascadeshield/sim/MlInferenceClientTest.java) - M4_ADDITION.
- [simulator/backend/src/test/java/io/cascadeshield/sim/MlOperatorAdvisorTest.java](../simulator/backend/src/test/java/io/cascadeshield/sim/MlOperatorAdvisorTest.java) - M4_ADDITION.
- [simulator/backend/src/test/java/io/cascadeshield/sim/MlPolicyRunnerTest.java](../simulator/backend/src/test/java/io/cascadeshield/sim/MlPolicyRunnerTest.java) - M4_ADDITION.

## Java corpus/inference/advice/B5 extensions

- [simulator/backend/src/main/java/io/cascadeshield/sim/MlController.java](../simulator/backend/src/main/java/io/cascadeshield/sim/MlController.java) - M4_ADDITION.
- [simulator/backend/src/main/java/io/cascadeshield/sim/MlCorpusCli.java](../simulator/backend/src/main/java/io/cascadeshield/sim/MlCorpusCli.java) - M4_ADDITION.
- [simulator/backend/src/main/java/io/cascadeshield/sim/MlExperimentProtocol.java](../simulator/backend/src/main/java/io/cascadeshield/sim/MlExperimentProtocol.java) - M4_ADDITION.
- [simulator/backend/src/main/java/io/cascadeshield/sim/MlFeatureExtractor.java](../simulator/backend/src/main/java/io/cascadeshield/sim/MlFeatureExtractor.java) - M4_ADDITION.
- [simulator/backend/src/main/java/io/cascadeshield/sim/MlInferenceClient.java](../simulator/backend/src/main/java/io/cascadeshield/sim/MlInferenceClient.java) - M4_ADDITION.
- [simulator/backend/src/main/java/io/cascadeshield/sim/MlModels.java](../simulator/backend/src/main/java/io/cascadeshield/sim/MlModels.java) - M4_ADDITION.
- [simulator/backend/src/main/java/io/cascadeshield/sim/MlOperatorAdvisor.java](../simulator/backend/src/main/java/io/cascadeshield/sim/MlOperatorAdvisor.java) - M4_ADDITION.
- [simulator/backend/src/main/java/io/cascadeshield/sim/MlPolicyCli.java](../simulator/backend/src/main/java/io/cascadeshield/sim/MlPolicyCli.java) - M4_ADDITION.
- [simulator/backend/src/main/java/io/cascadeshield/sim/MlPolicyRunner.java](../simulator/backend/src/main/java/io/cascadeshield/sim/MlPolicyRunner.java) - M4_ADDITION.

## M4 documentation

- [docs/GNN_ARCHITECTURE.md](../docs/GNN_ARCHITECTURE.md) - M4_ADDITION.
- [docs/MILESTONE_4_BENCHMARK_PROTOCOL.md](../docs/MILESTONE_4_BENCHMARK_PROTOCOL.md) - M4_ADDITION.
- [docs/MILESTONE_4_REPRODUCE.md](../docs/MILESTONE_4_REPRODUCE.md) - M4_ADDITION.
- [docs/ML_INFERENCE_API.md](../docs/ML_INFERENCE_API.md) - M4_ADDITION.
- [docs/ML_TRAINING_PIPELINE.md](../docs/ML_TRAINING_PIPELINE.md) - M4_ADDITION.

## M4 experiment/operation/evidence scripts

- [scripts/audit_milestone4_leakage.py](../scripts/audit_milestone4_leakage.py) - M4_ADDITION.
- [scripts/audit_ml_environment.py](../scripts/audit_ml_environment.py) - M4_ADDITION.
- [scripts/benchmark_ml_compute.py](../scripts/benchmark_ml_compute.py) - M4_ADDITION.
- [scripts/check_milestone4_legacy.py](../scripts/check_milestone4_legacy.py) - M4_ADDITION.
- [scripts/diagnose_milestone3.py](../scripts/diagnose_milestone3.py) - M4_ADDITION.
- [scripts/run_frozen_milestone4_policies.py](../scripts/run_frozen_milestone4_policies.py) - M4_ADDITION.
- [scripts/run_milestone4_experiments.py](../scripts/run_milestone4_experiments.py) - M4_ADDITION.
- [scripts/run_milestone4_java.sh](../scripts/run_milestone4_java.sh) - M4_ADDITION.
- [scripts/serve_ml.py](../scripts/serve_ml.py) - M4_ADDITION.
- [scripts/start_ml.ps1](../scripts/start_ml.ps1) - M4_ADDITION.
- [scripts/stop_ml.ps1](../scripts/stop_ml.ps1) - M4_ADDITION.
- [scripts/summarize_milestone4_policies.py](../scripts/summarize_milestone4_policies.py) - M4_ADDITION.
- [scripts/test_milestone4_browser.py](../scripts/test_milestone4_browser.py) - M4_ADDITION.
- [scripts/train_milestone4.py](../scripts/train_milestone4.py) - M4_ADDITION.
- [scripts/verify_milestone4_inference.py](../scripts/verify_milestone4_inference.py) - M4_ADDITION.
- [scripts/verify_milestone4_preservation.py](../scripts/verify_milestone4_preservation.py) - M4_ADDITION.

## M4 frontend prediction/operator panels

- [simulator/frontend/src/MlAdvicePanel.tsx](../simulator/frontend/src/MlAdvicePanel.tsx) - M4_ADDITION.
- [simulator/frontend/src/MlPredictionPanel.tsx](../simulator/frontend/src/MlPredictionPanel.tsx) - M4_ADDITION.
- [simulator/frontend/src/ml.css](../simulator/frontend/src/ml.css) - M4_ADDITION.
- [simulator/frontend/src/ml.test.ts](../simulator/frontend/src/ml.test.ts) - M4_ADDITION.
- [simulator/frontend/src/ml.ts](../simulator/frontend/src/ml.ts) - M4_ADDITION.

## Python audit/policy tests

- [tests/test_milestone4_leakage_audit.py](../tests/test_milestone4_leakage_audit.py) - M4_ADDITION.
- [tests/test_milestone4_policy_freeze.py](../tests/test_milestone4_policy_freeze.py) - M4_ADDITION.
- [tests/test_milestone4_policy_summary.py](../tests/test_milestone4_policy_summary.py) - M4_ADDITION.

## Python learning tests

- [tests/test_ml_graph_metrics.py](../tests/test_ml_graph_metrics.py) - M4_ADDITION.
- [tests/test_ml_pipeline.py](../tests/test_ml_pipeline.py) - M4_ADDITION.

## Python model/data/service package

- [ml/__init__.py](../ml/__init__.py) - M4_ADDITION.
- [ml/data.py](../ml/data.py) - M4_ADDITION.
- [ml/evaluation.py](../ml/evaluation.py) - M4_ADDITION.
- [ml/features.py](../ml/features.py) - M4_ADDITION.
- [ml/gnn.py](../ml/gnn.py) - M4_ADDITION.
- [ml/inference.py](../ml/inference.py) - M4_ADDITION.
- [ml/metrics.py](../ml/metrics.py) - M4_ADDITION.
- [ml/service.py](../ml/service.py) - M4_ADDITION.
- [ml/training.py](../ml/training.py) - M4_ADDITION.

## Executed artifacts

80 summary/model/figure artifacts are listed with exact hashes in the JSON inventory. See [final results](MILESTONE_4_RESULTS.md), [prediction evidence](MILESTONE_4_PREDICTION_METRICS.json), [all 440 policy outcome hashes](MILESTONE_4_POLICY_BENCHMARK.json), and [reproduction commands](../docs/MILESTONE_4_REPRODUCE.md).
