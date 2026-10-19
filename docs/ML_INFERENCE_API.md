# Milestone 4 inference boundary

The Java engine owns all simulation transitions. Python prediction reads a copied, timestamped feature frame and has no simulator or database write access. Model outputs concern simulated operations on the real bounded Chennai OSM graph. They are not observed freight outcomes.

The Python service exposes `GET /health`, `GET /models` and `POST /predict`. Run `python scripts/serve_ml.py --models models/milestone4/v1 --host 0.0.0.0 --port 8090` from the project root after training. The default Python host is loopback; the explicit host above lets the Docker backend reach the host through `host.docker.internal:8090`. Use this trusted local development service on the local machine; it is not an authenticated public deployment.

Requests use `cascadeshield.ml-request/1.0`, the exact ordered feature schema/hash, model ID, OSM graph SHA, network ID and prediction-state fingerprint. `frame` contains current features and a graph snapshot with empty realized labels. Optional chronological `history` contains at most three preceding frames from the same run/scenario. Labels, private incident/restoration schedules and future outcomes are rejected. Python and Java independently validate schemas and numerical ranges.

Available trained IDs, once their artifacts exist, are `xgb-v1`, `xgb-no-graph-v1`, `gnn-static-v1` and `gnn-temporal-v1`. Model version is `milestone4-v1`. Each response contains current truck IDs, remaining road-arrival seconds, a calibration-residual interval, delivery-lateness probability, future new operational-impact probability over 300 seconds, source, calibration details, model/version, input fingerprint and elapsed inference time. Arrived ETA and inapplicable SLA outputs remain null. A missing or unsupported label is never an invented observation. Inspect the manifest and final results for actual trained/validated status, training domain, interval coverage and calibration limits.

The Spring Boot routes are:

| Route | Behavior |
| --- | --- |
| `GET /api/ml/status` | Read-only feature/network/model registry, including explicit service-unavailable status. |
| `POST /api/ml/predict` with `{"modelId":"xgb-v1"}` | Captures the exact backend state; returns a validated prediction or deterministic fallback envelope. |
| `POST /api/ml/recommendations/{truckId}` with the same selection | Ranks existing operator candidates on separate state copies; never executes or approves an action. |

Java rejects incompatible model/schema/network/hash/fingerprint/clock, missing or duplicate trucks, invalid probability or time ranges and inconsistent intervals. HTTP calls have bounded timeouts. The fallback is the existing rule estimate, explicitly labelled `RULE_BASED`, with null probabilities/intervals and an uncalibrated warning. A model failure during any operator candidate comparison makes the entire comparison use deterministic scores; it does not mix incomparable providers. Live history is bounded and ephemeral; a backend restart clears recurrent context and preserves the Java state. Temporal inference without history is explicitly disclosed.

The dashboard separates the prediction panel from realized simulator outcomes. Its operator review panel uses the existing `CONTINUE`, `WAIT`, `REROUTE` candidates and the fixed Milestone 4 score. It does not implement the research runner's five-action policy or claim policy equivalence. Candidate scoring is an association-based estimate on action-conditioned features, not causal evidence of action benefit. The training corpus follows unmodified scenario trajectories; off-policy candidate states can be outside that training distribution. Temporal operator comparisons use only the current graph, while isolated temporal policy experiments maintain causal history.

The operator must separately request review, enter an identifier and explicitly approve, then execute through the existing transactional `/api/ai/approvals` endpoints. Backend guards require a paused/draft non-replay state, the exact full-state fingerprint, current constraints and a single unconsumed approval. Model code cannot bypass these guards. Any state change requires a fresh comparison/approval. The existing approval record persists the authoritative candidate and deterministic constraint evaluation; the read-only ML advice itself is not silently stored as a trained-model audit record.

CPU model loading/inference is required even after GPU fitting. An inference service outage cannot move a truck or change a saved simulation. Unit fixtures and transport checks are engineering evidence only; trained performance and policy benefit must come from the frozen held-out assessment described in `MILESTONE_4_BENCHMARK_PROTOCOL.md`.
