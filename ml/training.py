"""Executed simulation-only model fitting. Final outcomes are a separate, frozen phase."""
from __future__ import annotations

import copy
import csv
import hashlib
import importlib.metadata
import json
import os
import random
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import psutil
import torch
from torch import nn
import xgboost as xgb

from .data import load_corpus, examples, dataset_manifest, reconstruct_labels, future_impact
from .features import (FEATURES, GRAPH_FEATURES, FEATURE_HASH, FEATURE_VERSION, MODEL_VERSION,
                       PROVENANCE, canonical_hash, feature_vector, strip_labels)
from .gnn import NODE_TYPES, OperationalGNN, raw_graph, fit_normalizers, tensor_graph
from .metrics import regression, classification, fit_calibration, calibrated, interval_radius

SEED = 4001
XGB_GRID = ({"max_depth": 3, "n_estimators": 80, "learning_rate": .08},
            {"max_depth": 4, "n_estimators": 160, "learning_rate": .05})
GNN_CONFIG = {"hidden": 24, "maximumEpochs": 24, "patience": 5, "learningRate": .003,
              "historyFrames": 3, "gradientClip": 2., "etaScaleSec": 600.,
              "framesPerBackward": 4, "gradientAccumulation": "ALL_FRAMES_IN_ONE_SCENARIO",
              "mixedPrecision": False,
              "lossWeights": {"eta": 1., "sla": 1., "nodeImpact": .5}}
TARGETS = ("remainingArrivalSec", "deliveryLate", "futureImpact")
ROOT = Path(__file__).resolve().parents[1]
AUDITED_SOURCES = (
    "simulator/backend/src/main/java/io/cascadeshield/sim/MlFeatureExtractor.java",
    "simulator/backend/src/main/java/io/cascadeshield/sim/MlCorpusCli.java",
    "simulator/backend/src/main/java/io/cascadeshield/sim/MlExperimentProtocol.java",
    "ml/data.py", "ml/features.py",
)


def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".pending")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def save_checkpoint(value, path: Path):
    """A process interruption must not replace the last valid development checkpoint."""
    temporary = path.with_name(path.name + ".pending")
    torch.save(value, temporary)
    temporary.replace(path)


def sha(path: Path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def learning_source_hashes():
    paths = list((ROOT / "ml").glob("*.py")) + [ROOT / "scripts/train_milestone4.py"]
    return {p.relative_to(ROOT).as_posix(): sha(p) for p in sorted(paths)}


def policy_source_hashes():
    directory = ROOT / "simulator/backend/src/main/java/io/cascadeshield/sim"
    paths = list(directory.glob("Ml*.java"))
    paths += [ROOT / name for name in ("scripts/run_milestone4_experiments.py", "scripts/run_milestone4_java.sh")]
    return {p.relative_to(ROOT).as_posix(): sha(p) for p in sorted(paths)}


def require_training_audit(corpus_dir: Path, protocol: Path, audit: Path):
    """Fail closed before any model fitting if independent input audit is stale."""
    checked = json.loads(audit.read_text(encoding="utf-8-sig"))
    if checked.get("trainingAuthorizedAfterAudit") is not True:
        raise ValueError("Independent leakage audit has not authorized training")
    for name, path in (("protocolSha256", protocol),
                       ("generationManifestSha256", corpus_dir / "generation_manifest.json"),
                       ("featureSchemaFileSha256", corpus_dir / "feature_schema.json"),
                       ("graphSha256", ROOT / "data/processed/chennai_osm/road_graph.json"),
                       ("auditImplementationSha256", ROOT / "scripts/audit_milestone4_leakage.py")):
        if checked.get(name) != sha(path):
            raise ValueError("Independent pretraining audit is stale: " + name)
    declaration = json.loads((corpus_dir / "generation_manifest.json").read_text(encoding="utf-8-sig"))
    if checked.get("featureSchemaHash") != FEATURE_HASH or declaration.get("graphSha256") != checked["graphSha256"]:
        raise ValueError("Independent audit does not bind the current feature/network contract")
    sources = checked.get("reviewedSourceSha256", {})
    if any(sources.get(name) != sha(ROOT / name) for name in AUDITED_SOURCES):
        raise ValueError("Reviewed corpus/feature source changed after independent audit")
    development = checked.get("developmentAudit") or {}
    if (development.get("passed") is not True or development.get("strictAuthoritativeTargetParity") is not True
            or development.get("asOfInferenceProjectionValidated") is not True
            or development.get("finalOutcomesOpened") is not False):
        raise ValueError("A passing independent development target/as-of audit is required before fitting")
    if any(development.get("sourceCorpusSha256", {}).get(split) != sha(corpus_dir / f"{split}.jsonl")
           for split in ("train", "validation", "calibration")):
        raise ValueError("Development corpus changed after independent target/as-of audit")
    return {"path": str(audit).replace("\\", "/"), "sha256": sha(audit),
            "protocolSha256": checked["protocolSha256"],
            "generationManifestSha256": checked["generationManifestSha256"],
            "graphSha256": checked["graphSha256"], "featureSchemaHash": FEATURE_HASH,
            "developmentCorpusSha256": development["sourceCorpusSha256"],
            "reviewedSourceSha256": sources}


def versions():
    return {name: importlib.metadata.version(name) for name in
            ("numpy", "scikit-learn", "torch", "torch-geometric", "psutil")} | {"xgboost": xgb.__version__}


def freeze_random():
    random.seed(SEED); np.random.seed(SEED); torch.manual_seed(SEED)
    torch.set_num_threads(2)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(SEED)
    torch.use_deterministic_algorithms(True, warn_only=True)


def validate_split_isolation(scenarios):
    groups = {}
    identities = set()
    for s in scenarios:
        if s["seed"] in groups and groups[s["seed"]] != s["split"]:
            raise ValueError("The same seed occurs in separate dataset splits")
        groups[s["seed"]] = s["split"]
        identity = s.get("inputFingerprint", s.get("scenarioFingerprint"))
        if identity in identities:
            raise ValueError("A scenario input fingerprint is duplicated across files")
        identities.add(identity)


def _matrix(rows, names, target):
    eligible = [r for r in rows if r["labels"][target] is not None]
    return (np.asarray([feature_vector(r["features"], names) for r in eligible], dtype=np.float32),
            np.asarray([r["labels"][target] for r in eligible], dtype=np.float32), eligible)


def fit_xgb(train, validation, calibration, output, names, device):
    fitted, selection, calibration_config = {}, {}, {}
    for target in TARGETS:
        xt, yt, _ = _matrix(train, names, target)
        xv, yv, _ = _matrix(validation, names, target)
        xc, yc, _ = _matrix(calibration, names, target)
        if not len(yt) or not len(yv) or not len(yc):
            raise ValueError(f"Target {target} has no legitimate train/validation/calibration labels")
        trials = []
        for index, parameters in enumerate(XGB_GRID):
            start = time.perf_counter()
            common = dict(**parameters, tree_method="hist", device=device, n_jobs=2,
                          random_state=SEED, subsample=1., colsample_bytree=1.)
            if target == "remainingArrivalSec":
                model = xgb.XGBRegressor(**common, objective="reg:squarederror")
                model.fit(xt, yt); pred = np.maximum(0, model.predict(xv))
                score = regression(yv, pred)["mae"]
            else:
                if len(np.unique(yt)) != 2:
                    raise ValueError(f"Cannot train {target}: training data has one class")
                model = xgb.XGBClassifier(**common, objective="binary:logistic", eval_metric="logloss")
                model.fit(xt, yt); pred = model.predict_proba(xv)[:, 1]
                score = classification(yv, pred)["brier"]
            configuration = json.loads(model.get_booster().save_config())
            actual_device = configuration["learner"]["generic_param"]["device"]
            elapsed = (time.perf_counter()-start)*1000
            trials.append({"index": index, "parameters": parameters, "validationScore": score,
                           "fitAndValidationMs": elapsed, "requestedDevice": device,
                           "actualLearnerDevice": actual_device, "model": model})
        best = min(trials, key=lambda t: (t["validationScore"], t["index"]))
        model = best["model"]
        filename = {"remainingArrivalSec": "eta.json", "deliveryLate": "sla.json", "futureImpact": "impact.json"}[target]
        model.save_model(output / filename)
        loaded = xgb.XGBRegressor() if target == "remainingArrivalSec" else xgb.XGBClassifier()
        loaded.load_model(output / filename)
        # CPU deployment is intentional even when fitting used CUDA.
        model.set_params(device="cpu"); loaded.set_params(device="cpu")
        predict = lambda m, x: np.maximum(0, m.predict(x)) if target == "remainingArrivalSec" else m.predict_proba(x)[:, 1]
        if not np.allclose(predict(model, xc), predict(loaded, xc), rtol=1e-6, atol=1e-6):
            raise AssertionError("Serialized XGBoost predictions changed after CPU reload")
        predc = predict(loaded, xc)
        calibration_config[target] = interval_radius(yc, predc) if target == "remainingArrivalSec" else fit_calibration(yc, predc)
        fitted[target] = loaded
        selection[target] = {"selectedIndex": best["index"], "criterion": "MAE" if target == "remainingArrivalSec" else "Brier",
                             "trials": [{k: v for k, v in trial.items() if k != "model"} for trial in trials],
                             "trainExamples": len(yt), "validationExamples": len(yv), "calibrationExamples": len(yc),
                             "featureImportance": dict(sorted(zip(names, map(float, loaded.feature_importances_)), key=lambda x: -x[1])),
                             "reloadEquivalent": True}
    return {"featureNames": names, "calibration": calibration_config, "selection": selection}


def _schema(scenarios):
    sample = scenarios[0]["frames"][0]["graphSnapshot"]["featureSchemas"]
    return {kind: list(FEATURES) if kind == "TRUCK" else [f["name"] for f in sample[kind]] for kind in NODE_TYPES}


def prepare_graphs(scenarios, schema, normalizers=None, device="cpu"):
    raw = [[raw_graph(frame, schema) for frame in s["frames"]] for s in scenarios]
    if normalizers is None:
        normalizers = fit_normalizers([g for gs in raw for g in gs], schema)
    tensors = [[tensor_graph(g, normalizers, device) for g in gs] for gs in raw]
    return tensors, normalizers


def _labels(scenario, frame, graph, device):
    trucks = {t["truckId"]: t for t in frame["trucks"]}
    labels = [reconstruct_labels(scenario, frame, trucks[node.split(":", 1)[1]]) for node in graph["ids"]["TRUCK"]]
    eta = torch.tensor([l["remainingArrivalSec"] if l["remainingArrivalSec"] is not None else float("nan") for l in labels], dtype=torch.float32, device=device)
    sla = torch.tensor([l["deliveryLate"] if l["deliveryLate"] is not None else float("nan") for l in labels], dtype=torch.float32, device=device)
    impacts = {kind: torch.tensor([future_impact(scenario, frame, node) if future_impact(scenario, frame, node) is not None else float("nan") for node in ids], dtype=torch.float32, device=device)
               for kind, ids in graph["ids"].items()}
    return eta, sla, impacts


def graph_loss(output, labels):
    truck, impacts = output
    eta, sla, impact_labels = labels
    terms = []
    mask = torch.isfinite(eta)
    if mask.any():
        terms.append(nn.functional.smooth_l1_loss(truck[mask, 0]/600., eta[mask]/600.))
    mask = torch.isfinite(sla)
    if mask.any():
        terms.append(nn.functional.binary_cross_entropy_with_logits(truck[mask, 1], sla[mask]))
    logits, ys = [], []
    for kind, values in impacts.items():
        mask = torch.isfinite(impact_labels[kind])
        if mask.any():
            logits.append(values[mask]); ys.append(impact_labels[kind][mask])
    if logits:
        terms.append(.5*nn.functional.binary_cross_entropy_with_logits(torch.cat(logits), torch.cat(ys)))
    return sum(terms, truck.sum()*0.)


def graph_predictions(model, scenarios, graphs):
    model.eval(); outputs = {}
    with torch.no_grad():
        for scenario, gs in zip(scenarios, graphs):
            for index, graph in enumerate(gs):
                truck, impacts = model(gs[max(0, index-2):index+1])
                for n, node in enumerate(graph["ids"]["TRUCK"]):
                    outputs[(scenario["scenarioId"], index, node.split(":", 1)[1])] = {
                        "remainingArrivalSec": float(truck[n, 0].cpu()),
                        "deliveryLate": float(torch.sigmoid(truck[n, 1]).cpu()),
                        "futureImpact": float(torch.sigmoid(truck[n, 2]).cpu())}
    return outputs


def fit_gnn(train_scenarios, validation_scenarios, calibration_scenarios, output, temporal, device, resume=False,
            selection_hash=None):
    schema = _schema(train_scenarios)
    train_graphs, normalizers = prepare_graphs(train_scenarios, schema, device=device)
    validation_graphs, _ = prepare_graphs(validation_scenarios, schema, normalizers, device)
    calibration_graphs, _ = prepare_graphs(calibration_scenarios, schema, normalizers, device)
    freeze_random()
    model = OperationalGNN(schema, hidden=GNN_CONFIG["hidden"], temporal=temporal).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=GNN_CONFIG["learningRate"])
    prepared_labels = [[_labels(s, f, g, device) for f, g in zip(s["frames"], gs)] for s, gs in zip(train_scenarios, train_graphs)]
    validation_rows = examples(validation_scenarios)
    best, best_epoch, stale, history = float("inf"), -1, 0, []
    first_epoch = 0
    if resume and (output / "checkpoint.pt").exists():
        saved = torch.load(output / "checkpoint.pt", map_location=device, weights_only=False)
        if (saved["featureSchemaHash"] != FEATURE_HASH or saved["temporal"] != temporal or saved["config"] != GNN_CONFIG
                or saved.get("selectionInputHash") != selection_hash):
            raise ValueError("Checkpoint schema/architecture differs from declared training")
        model.load_state_dict(saved["model"]); optimizer.load_state_dict(saved["optimizer"])
        best, best_epoch, first_epoch = saved["validationCriterion"], saved["epoch"], saved["epoch"]
        history = saved.get("history", [])
        print(f"Resuming {'temporal' if temporal else 'static'} GNN from saved best epoch {first_epoch}", flush=True)
    started = time.perf_counter()
    if device == "cuda": torch.cuda.reset_peak_memory_stats()
    for epoch in range(first_epoch, GNN_CONFIG["maximumEpochs"]):
        model.train(); total_loss = 0.
        for case_index, (scenario, gs) in enumerate(zip(train_scenarios, train_graphs)):
            optimizer.zero_grad(); batch_losses = []; scenario_loss = 0.
            for index, graph in enumerate(gs):
                prediction = model(gs[max(0, index-2):index+1])
                batch_losses.append(graph_loss(prediction, prepared_labels[case_index][index]))
                if len(batch_losses) == GNN_CONFIG["framesPerBackward"] or index == len(gs)-1:
                    # Accumulate the same scenario-average gradient without retaining
                    # every frame's autograd graph in VRAM simultaneously.
                    loss = sum(batch_losses)/len(gs)
                    loss.backward(); scenario_loss += float(loss.detach().cpu()); batch_losses = []
            torch.nn.utils.clip_grad_norm_(model.parameters(), GNN_CONFIG["gradientClip"])
            optimizer.step(); total_loss += scenario_loss
        predictions = graph_predictions(model, validation_scenarios, validation_graphs)
        sla_y, sla_p, eta_y, eta_p = [], [], [], []
        for row in validation_rows:
            pred = predictions[(row["scenarioId"], row["frameIndex"], row["truckId"])]
            if row["labels"]["deliveryLate"] is not None:
                sla_y.append(row["labels"]["deliveryLate"]); sla_p.append(pred["deliveryLate"])
            if row["labels"]["remainingArrivalSec"] is not None:
                eta_y.append(row["labels"]["remainingArrivalSec"]); eta_p.append(pred["remainingArrivalSec"])
        criterion = classification(sla_y, sla_p)["brier"] + regression(eta_y, eta_p)["mae"]/600.
        record = {"epoch": epoch+1, "meanScenarioTrainLoss": total_loss/len(train_scenarios),
                  "validationCriterion": criterion, "elapsedSec": time.perf_counter()-started}
        history.append(record); print(json.dumps({"model": "gnn-temporal" if temporal else "gnn-static", **record}), flush=True)
        if criterion < best-1e-6:
            best, best_epoch, stale = criterion, epoch+1, 0
            save_checkpoint({"model": {k: v.cpu() for k, v in model.state_dict().items()}, "epoch": best_epoch,
                        "optimizer": optimizer.state_dict(), "config": GNN_CONFIG, "temporal": temporal,
                        "featureSchemaHash": FEATURE_HASH, "validationCriterion": criterion,
                        "selectionInputHash": selection_hash,
                        "history": history}, output / "checkpoint.pt")
        else:
            stale += 1
        if stale >= GNN_CONFIG["patience"]:
            break
    checkpoint = torch.load(output / "checkpoint.pt", map_location="cpu", weights_only=False)
    model.load_state_dict(checkpoint["model"]); model.to(device)
    calibration_predictions = graph_predictions(model, calibration_scenarios, calibration_graphs)
    calibration_rows = examples(calibration_scenarios)
    calibration_config = {}
    for target in TARGETS:
        eligible = [r for r in calibration_rows if r["labels"][target] is not None]
        y = [r["labels"][target] for r in eligible]
        p = [calibration_predictions[(r["scenarioId"], r["frameIndex"], r["truckId"])][target] for r in eligible]
        calibration_config[target] = interval_radius(y, p) if target == "remainingArrivalSec" else fit_calibration(y, p)
    # Export only tensor weights; inference never loads an arbitrary pickle-backed optimizer.
    save_checkpoint(checkpoint["model"], output / "weights.pt")
    cpu_model = OperationalGNN(schema, hidden=GNN_CONFIG["hidden"], temporal=temporal)
    cpu_model.load_state_dict(torch.load(output / "weights.pt", map_location="cpu", weights_only=True)); cpu_model.eval()
    cpu_graphs, _ = prepare_graphs(calibration_scenarios[:1], schema, normalizers, "cpu")
    cpu_preds = graph_predictions(cpu_model, calibration_scenarios[:1], cpu_graphs)
    max_error = max(abs(cpu_preds[k][target]-calibration_predictions[k][target]) for k in cpu_preds for target in TARGETS)
    if max_error > .02:
        raise AssertionError(f"CPU/GPU reload mismatch {max_error}")
    return {"nodeSchema": schema, "normalizers": normalizers, "hidden": GNN_CONFIG["hidden"],
            "temporal": temporal, "historyFrames": 3 if temporal else 1,
            "calibration": calibration_config, "selectedEpoch": best_epoch,
            "selectionCriterion": "validation Brier(SLA) + validation ETA MAE/600", "trainingHistory": history,
            "trainingDevice": device, "trainingSec": time.perf_counter()-started,
            "peakCudaAllocatedBytes": torch.cuda.max_memory_allocated() if device == "cuda" else None,
            "peakCudaReservedBytes": torch.cuda.max_memory_reserved() if device == "cuda" else None,
            "framesPerBackward": GNN_CONFIG["framesPerBackward"],
            "gradientAccumulation": GNN_CONFIG["gradientAccumulation"],
            "mixedPrecision": False,
            "mixedPrecisionReason": "Small bounded graphs; full precision preserves probability and ETA stability",
            "cpuReloadMaximumAbsoluteDifference": max_error,
            "processRssAtCompletionBytes": psutil.Process().memory_info().rss,
            "peakProcessRssBytes": getattr(psutil.Process().memory_info(), "peak_wset", None)}


def fit(corpus_dir: Path, output: Path, report_dir: Path, protocol: Path, device: str, resume=False,
        audit: Path = Path("reports/milestone4_leakage_audit.json"), gnn_device=None):
    audit_evidence = require_training_audit(corpus_dir, protocol, audit)
    if (output / "manifest.json").exists():
        raise ValueError("A frozen published model bundle is immutable; choose a new version")
    if output.exists() and any(output.iterdir()) and not resume:
        raise ValueError("Model directory already contains artifacts; preserve it and choose a new version")
    if (corpus_dir / "final.jsonl").exists():
        raise ValueError("Final outcomes already exist: model selection must precede generation of final assessment")
    freeze_random()
    output.mkdir(parents=True, exist_ok=True)
    scenarios = []
    source_hashes = {}
    source_schema = json.loads((corpus_dir / "feature_schema.json").read_text(encoding="utf-8-sig"))
    if source_schema.get("schemaVersion") != FEATURE_VERSION or source_schema.get("featureSchemaHash") != FEATURE_HASH or source_schema.get("featureNames") != list(FEATURES):
        raise ValueError("Java exporter schema does not match the frozen Python feature contract")
    for split in ("train", "validation", "calibration"):
        source = corpus_dir / f"{split}.jsonl"
        scenarios.extend(load_corpus(source, {split})); source_hashes[split] = sha(source)
    validate_split_isolation(scenarios)
    rows = examples(scenarios)
    groups = {split: [r for r in rows if r["split"] == split] for split in ("train", "validation", "calibration")}
    by_split = {split: [s for s in scenarios if s["split"] == split] for split in groups}
    network_ids = {f["graphSnapshot"]["networkId"] for s in scenarios for f in s["frames"]}
    graph_hashes = {f.get("graphSha256", s.get("graphSha256")) for s in scenarios for f in s["frames"]}
    if len(network_ids) != 1 or len(graph_hashes) != 1 or None in graph_hashes:
        raise ValueError("A single explicit immutable network graph version is required")
    selection_inputs = {"featureSchemaHash": FEATURE_HASH, "graphSha256": next(iter(graph_hashes)),
                        "sourceCorpusSha256": source_hashes, "protocolSha256": sha(protocol),
                        "randomSeed": SEED, "xgbGrid": XGB_GRID, "gnnConfig": GNN_CONFIG,
                        "learningSourceSha256": learning_source_hashes()}
    selection_hash = canonical_hash(selection_inputs)
    selection_path = output / "selection_inputs.json"
    if selection_path.exists() and canonical_hash(json.loads(selection_path.read_text(encoding="utf-8"))) != selection_hash:
        raise ValueError("Interrupted training inputs/configuration changed; existing checkpoints cannot be resumed")
    if not selection_path.exists(): write_json(selection_path, selection_inputs)
    # Preserve the exact passing review beside the immutable published artifacts.
    pending_audit = output / "pretraining_audit.json.pending"
    pending_audit.write_bytes(audit.read_bytes()); pending_audit.replace(output / "pretraining_audit.json")
    manifest = {"schemaVersion": "cascadeshield.model-bundle/1.0", "modelVersion": MODEL_VERSION,
                "selectionStartedAtUtc": datetime.now(timezone.utc).isoformat(),
                "featureSchemaVersion": FEATURE_VERSION, "featureNames": FEATURES, "featureSchemaHash": FEATURE_HASH,
                "networkId": next(iter(network_ids)), "graphSha256": next(iter(graph_hashes)),
                "provenance": "TRAINED_ON_SIMULATED_LOGISTICS_ONLY", "trainedOnObservedFreight": False,
                "randomSeed": SEED, "packages": versions(), "sourceCorpusSha256": source_hashes,
                "protocolSha256": sha(protocol), "dataset": dataset_manifest(scenarios, rows),
                "protocolSourcePath": str(protocol).replace("\\", "/"),
                "selectionInputHash": selection_hash,
                "generationManifestSha256": sha(corpus_dir / "generation_manifest.json"),
                "sourceFeatureSchemaSha256": sha(corpus_dir / "feature_schema.json"),
                "modelSelection": {"xgbGrid": XGB_GRID, "gnnConfig": GNN_CONFIG, "usesFinalOutcomes": False},
                "models": {}, "trainingDeviceRequested": device, "pretrainingAudit": audit_evidence,
                "trainingHardware": {"logicalCpuCount": psutil.cpu_count(),
                     "ramTotalBytes": psutil.virtual_memory().total,
                     "ramAvailableBytesAtStart": psutil.virtual_memory().available,
                     "gpuName": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
                     "gpuTotalBytes": torch.cuda.get_device_properties(0).total_memory if torch.cuda.is_available() else None}}
    manifest["baselineStatistics"] = {target: float(np.mean([r["labels"][target] for r in groups["train"] if r["labels"][target] is not None])) for target in TARGETS}
    started = time.perf_counter()
    if device == "cuda" and not torch.cuda.is_available():
        manifest["deviceFallbackReason"] = "CUDA requested but unavailable; using CPU without changing system drivers"
        device = "cpu"
        print(manifest["deviceFallbackReason"], flush=True)
    manifest["trainingDeviceSelected"] = device
    gnn_device = gnn_device or device
    if gnn_device == "cuda" and not torch.cuda.is_available():
        gnn_device = "cpu"
        manifest["gnnDeviceFallbackReason"] = "CUDA requested but unavailable; using CPU"
    manifest["gnnTrainingDeviceSelected"] = gnn_device
    for model_id, names in (("xgb-v1", FEATURES), ("xgb-no-graph-v1", tuple(n for n in FEATURES if n not in GRAPH_FEATURES))):
        directory = output / model_id; directory.mkdir(exist_ok=resume)
        print(f"Fitting {model_id} on {len(groups['train'])} truck snapshots", flush=True)
        manifest["models"][model_id] = fit_xgb(groups["train"], groups["validation"], groups["calibration"], directory, names, device)
    for model_id, temporal in (("gnn-static-v1", False), ("gnn-temporal-v1", True)):
        directory = output / model_id; directory.mkdir(exist_ok=resume)
        print(f"Fitting {model_id} on independent timestamped operational graphs", flush=True)
        try:
            manifest["models"][model_id] = fit_gnn(by_split["train"], by_split["validation"], by_split["calibration"], directory, temporal, gnn_device, resume, selection_hash)
        except torch.cuda.OutOfMemoryError as exc:
            if gnn_device != "cuda": raise
            torch.cuda.empty_cache()
            print(f"{model_id}: GPU allocation exceeded available VRAM; resuming on CPU", flush=True)
            manifest["models"][model_id] = fit_gnn(by_split["train"], by_split["validation"], by_split["calibration"], directory, temporal, "cpu", True, selection_hash)
            manifest["models"][model_id]["deviceFallbackReason"] = "GPU out of memory: " + str(exc)
    manifest["totalTrainingSec"] = time.perf_counter()-started
    if learning_source_hashes() != selection_inputs["learningSourceSha256"]:
        raise ValueError("Learning/inference implementation changed during fitting; model selection cannot be frozen")
    manifest["implementationSha256"] = {**selection_inputs["learningSourceSha256"], **policy_source_hashes()}
    compute_path = report_dir / "milestone4_compute_comparison.json"
    if compute_path.exists():
        manifest["computeComparison"] = {"path": str(compute_path).replace("\\", "/"), "sha256": sha(compute_path)}
    execution_path = report_dir / "milestone4_pretraining_execution_events.json"
    if execution_path.exists():
        manifest["pretrainingExecutionEvents"] = {"path": str(execution_path).replace("\\", "/"), "sha256": sha(execution_path)}
    manifest["selectionFrozenAtUtc"] = datetime.now(timezone.utc).isoformat()
    manifest["artifactSha256"] = {str(p.relative_to(output)).replace("\\", "/"): sha(p) for p in output.rglob("*") if p.is_file()}
    for model_id in manifest["models"]:
        manifest["models"][model_id]["artifactSha256"] = {key: value for key, value in manifest["artifactSha256"].items() if key.startswith(model_id+"/")}
    manifest["frozen"] = True
    manifest["validatedModelIds"] = list(manifest["models"])
    manifest["assessmentRule"] = "Final outcomes were absent during model/feature/hyperparameter/calibration selection. No refitting after final assessment."
    write_json(output / "manifest.json", manifest)
    write_json(report_dir / "milestone4_model_selection.json", manifest)
    write_json(output / "feature_schema.json", {"schemaVersion": FEATURE_VERSION, "featureNames": FEATURES,
                                               "featureSchemaHash": FEATURE_HASH})
    print("MODEL SELECTION FROZEN: " + str(output / "manifest.json"), flush=True)
    return manifest
