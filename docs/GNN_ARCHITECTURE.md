# Operational heterogeneous graph learning

`ml/gnn.py` implements a small PyTorch/PyTorch Geometric graph model over the existing JGraphT export. The model is intended for controlled simulator studies. It has no observed freight training history and supplies no deployment or commercial-navigation claim.

The graph has the five types actually built by `OperationalDependencyGraph`: TRUCK, DRIVER, DOCK, DELIVERY and WAREHOUSE. The OSM road graph remains separate geographic provenance. No invented road, incident, warehouse or driver node is added. Current road/incident exposure is an explicit truck context feature, rather than a fabricated new graph relation.

The converter preserves stable `TYPE:ID` mappings, directed edges, available-value masks and forecast validity windows. Supported relations are ASSIGNED_DRIVER, RESERVED_DOCK, CARRIES_DELIVERY, DOCK_AT_WAREHOUSE, DELIVERY_TO_WAREHOUSE, SHARED_DOCK_CONFLICT, SHARED_DRIVER_CONFLICT, DRIVER_UNAVAILABLE, SHIFT_EXCEEDED, DOCK_OVERLAP, DOCK_WINDOW, DELIVERY_DEADLINE and DRIVER_OVERLAP. Some relation kinds may be absent from a training corpus; their presence in the implemented schema does not imply a trained parameter received examples. Unsupported relations fail inference and cause Java fallback.

Assignment relations come from configured simulated operations. Conflict relations, dependency weights and validity end estimates are explicit deterministic rule-derived inputs, not measured road/warehouse observations. The comparison therefore tests learned use of the current forecast graph as well as its topology.

## Static model

Each type has its own input encoder into 24 hidden units. TRUCK uses the same ordered 32-field context as tabular models. Other types use their actual exporter feature schema, training-median imputation, training mean/scale, clipped standardized values and an appended availability mask. No target, future completion timestamp or rule output is inserted into an ordinary raw node feature by the converter.

Two directed message-passing layers use relation-specific linear transforms and edge gates. A gate receives current edge weight, positive forecast lead time and remaining validity, each bounded/scaled at the prediction clock. Incoming messages have mean aggregation within the relation. A type-specific self transform is added, averaged with incoming relation outputs, followed by ReLU. There are no undocumented reverse operational edges. The implementation uses actual [PyG MessagePassing](https://pytorch-geometric.readthedocs.io/en/latest/_modules/torch_geometric/nn/conv/message_passing.html), not a renamed multilayer perceptron.

The truck output has three separately trained heads: nonnegative remaining-arrival seconds (`softplus * 600`), SLA logit and adverse-event logit. Other resource types have adverse-event logit heads. ETA labels are masked after road arrival; SLA labels are masked after delivery or when terminal completion is censored. Resource labels indicate a **new first recorded adverse event** in the next 300 simulated seconds, using only later authoritative outcomes as `y`.

## Temporal variant

`gnn-temporal-v1` retains the same encoders, graph layers, targets and compute configuration. Per-type GRU cells consume graph embeddings plus elapsed time across at most three preceding/current frames. Memory is aligned by stable node identity, begins at zero for each example history and never crosses scenario/run boundaries. The last frame's heads produce the prediction. At a live cold start, a single graph is accepted with an explicit missing-history warning.

This is a causal short-history graph recurrent model. It is not an event-stream TGN, an attention transformer, or a learned counterfactual simulator. The static model also receives clock, duty and planned validity features; “static” here means no recurrent history, rather than removal of every time value.

## Fitting, uncertainty and evaluation

The fixed architecture uses Adam at .003, at most 24 epochs, gradient norm clipping at 2 and early stopping after five validation epochs without improvement. ETA uses smooth L1 after division by 600; SLA uses binary cross entropy; all-node adverse-event BCE has weight .5. Selection minimizes validation SLA Brier plus ETA MAE/600. Node onset classes are often sparse, so precision/recall, PR-AUC, Brier and class counts are required alongside all-node metrics; an all-negative head is not deemed successful because of accuracy.

Static and temporal models are fit independently. Probability calibration uses separate simulated calibration scenarios. All ETA/SLA/event outputs of a GNN provider come from that GNN's trained heads; the provider never silently returns XGBoost under a GNN label. The all-type node event metrics additionally report raw sigmoid heads explicitly, without claiming truck calibration transfers to other node types.

XGBoost sees the current truck attributes and neighborhood summaries. The GNN additionally receives all typed resource-node attributes and their directed relationships. Both use the same prediction-time source state, but this is **not a pure architecture-only comparison with identical information representations**. No-graph XGBoost removes only three graph summary fields; temporal-versus-static holds the graph encoder and current graph fields fixed while adding past history.

Seed 4001 initializes Python, NumPy, Torch and CUDA generators. The runner sets `CUBLAS_WORKSPACE_CONFIG=:4096:8` and requests deterministic algorithms where available. Some device-specific operations or software versions can still differ; [PyTorch documents these limits](https://docs.pytorch.org/docs/main/generated/torch.use_deterministic_algorithms.html). Saved CPU weights and fixed CPU inference provide the reproducible replay boundary. CPU/GPU reload differences are actually checked and reported, rather than a claim of cross-device bitwise training equality.

Checkpoints include optimizer state, epoch, configuration, feature hash and development validation history. Published inference loads only tensor weights with `weights_only=True`; optimizer pickles are confined to trusted local training checkpoints. Model checksums and graph/schema versions are verified before serving.

Training and held-out metrics are recorded only after execution in the model manifest and `reports/MILESTONE_4_PREDICTION_METRICS.*`. If labels, class variation, device execution or serialization fails, the model is not listed as validated and B5 must use explicit deterministic fallback. Negative graph-learning results remain part of the report.
