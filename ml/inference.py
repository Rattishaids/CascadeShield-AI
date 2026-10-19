"""Read-only CPU inference with exact model, schema, graph and as-of validation."""
from __future__ import annotations

import hashlib
import json
import math
import threading
import time
from pathlib import Path

import numpy as np
import torch
import xgboost as xgb

from .features import (FEATURES, FEATURE_VERSION, FEATURE_HASH, REQUEST_VERSION, RESPONSE_VERSION,
                       MODEL_VERSION, feature_vector)
from .data import validate_frame
from .gnn import OperationalGNN, raw_graph, tensor_graph
from .metrics import calibrated


def domain_warnings(frame, manifest):
    """Declare detectable departures from the actual training input domain."""
    warnings = []
    trained_sizes = manifest.get("dataset", {}).get("scenarioFleetSizesBySplit", {}).get("train", [])
    count = len(frame["trucks"])
    if trained_sizes and count not in trained_sizes:
        warnings.append(f"Fleet size {count} is outside fitted training fleet sizes {trained_sizes}; this is a domain-shift prediction.")
    if any(len(t.get("deliveryIds", [])) > 1 for t in frame["trucks"]):
        warnings.append("Multiple deliveries per truck are outside the one-delivery-per-truck training design; no empirical validation is claimed for this arrangement.")
    shared = {}
    for edge in frame["graphSnapshot"].get("edges", []):
        if edge.get("type") == "ASSIGNED_DRIVER":
            shared.setdefault(edge["target"], set()).add(edge["source"])
    if any(len(trucks) > 1 for trucks in shared.values()):
        warnings.append("A shared driver assignment is outside the one-driver-per-truck training design; no empirical validation is claimed for this arrangement.")
    delivery_nodes = [n for n in frame["graphSnapshot"].get("nodes", []) if n["type"] == "DELIVERY"]
    if not delivery_nodes and count:
        warnings.append("No delivery resources are assigned; SLA outputs are unavailable and this resource graph differs from the supervised operational scenarios.")
    return warnings


class ModelBundle:
    def __init__(self, directory: Path):
        self.directory = directory
        manifest_bytes = (directory / "manifest.json").read_bytes()
        self.selection_manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
        self.manifest = json.loads(manifest_bytes.decode("utf-8"))
        m = self.manifest
        if not m.get("frozen") or m.get("modelVersion") != MODEL_VERSION or m.get("featureSchemaHash") != FEATURE_HASH:
            raise ValueError("Incompatible or unfrozen model bundle")
        if m.get("featureSchemaVersion") != FEATURE_VERSION or m.get("featureNames") != list(FEATURES):
            raise ValueError("Model feature schema does not match this inference implementation")
        for name, expected in m["artifactSha256"].items():
            path = (directory / name).resolve()
            if not path.is_relative_to(directory.resolve()) or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                raise ValueError("Model artifact checksum failed: " + name)
        self.models = {}
        torch.set_num_threads(2)
        for model_id, config in m["models"].items():
            if model_id.startswith("xgb"):
                models = {}
                for target, name in (("remainingArrivalSec", "eta"), ("deliveryLate", "sla"), ("futureImpact", "impact")):
                    model = xgb.XGBRegressor() if name == "eta" else xgb.XGBClassifier()
                    model.load_model(directory / model_id / f"{name}.json"); model.set_params(device="cpu", n_jobs=2)
                    models[target] = model
                self.models[model_id] = models
            elif model_id.startswith("gnn"):
                model = OperationalGNN(config["nodeSchema"], config["hidden"], config["temporal"])
                model.load_state_dict(torch.load(directory / model_id / "weights.pt", map_location="cpu", weights_only=True))
                model.eval(); self.models[model_id] = model
            else:
                raise ValueError("Unsupported serialized model: " + model_id)
        self.lock = threading.Lock()

    def catalog(self):
        return {"modelVersion": MODEL_VERSION, "featureSchemaVersion": FEATURE_VERSION,
                "selectionManifestSha256": self.selection_manifest_sha256,
                "featureSchemaHash": FEATURE_HASH, "networkId": self.manifest["networkId"],
                "graphSha256": self.manifest["graphSha256"], "inferenceDevice": "cpu",
                "models": [{"id": key, "calibration": value["calibration"],
                            "temporal": value.get("temporal", False)} for key, value in self.manifest["models"].items()],
                "provenance": "TRAINED_ON_SIMULATED_LOGISTICS_ONLY", "trainedOnObservedFreight": False}

    def validate_request(self, request):
        if not isinstance(request, dict) or request.get("schemaVersion") != REQUEST_VERSION:
            raise ValueError("Unsupported inference request schema")
        if request.get("featureSchemaVersion") != FEATURE_VERSION or request.get("featureSchemaHash") != FEATURE_HASH:
            raise ValueError("Incompatible feature schema or feature order")
        for key in ("networkId", "graphSha256"):
            if request.get(key) != self.manifest[key]:
                raise ValueError("Model is incompatible with request " + key)
        if request.get("modelId") not in self.models:
            raise ValueError("Requested trained model does not exist")
        if not isinstance(request.get("stateFingerprint"), str) or not request["stateFingerprint"]:
            raise ValueError("Frozen prediction state fingerprint is required")
        frame = request.get("frame")
        validate_frame(frame, inference=True)
        if frame.get("stateFingerprint") != request["stateFingerprint"]:
            raise ValueError("Frame fingerprint differs from frozen request")
        if frame["graphSnapshot"]["networkId"] != request["networkId"]:
            raise ValueError("Snapshot network differs from trained model network")
        history = request.get("history", [])
        if not isinstance(history, list) or len(history) > 3:
            raise ValueError("At most three preceding as-of graph frames are allowed")
        previous = -1.
        for old in history:
            validate_frame(old, inference=True)
            if old["clockSec"] <= previous or old["clockSec"] > frame["clockSec"] + 1e-7:
                raise ValueError("History is not causal and strictly chronological")
            previous = old["clockSec"]
            for field in ("networkId", "runId", "scenarioId"):
                if old["graphSnapshot"].get(field) != frame["graphSnapshot"].get(field):
                    raise ValueError("Temporal history crossed a scenario or run boundary")
        return frame, [old for old in history if old["clockSec"] < frame["clockSec"]-1e-7][-2:]

    def predict(self, request):
        start = time.perf_counter()
        frame, history = self.validate_request(request)
        model_id = request["modelId"]
        config = self.manifest["models"][model_id]
        model = self.models[model_id]
        trucks = frame["trucks"]
        predictions = []
        with self.lock:
            if model_id.startswith("xgb"):
                x = np.asarray([feature_vector(t["features"], tuple(config["featureNames"])) for t in trucks], dtype=np.float32)
                if len(x):
                    raw = {"remainingArrivalSec": np.maximum(0., model["remainingArrivalSec"].predict(x)),
                           "deliveryLate": model["deliveryLate"].predict_proba(x)[:, 1],
                           "futureImpact": model["futureImpact"].predict_proba(x)[:, 1]}
                else:
                    raw = {target: np.array([]) for target in ("remainingArrivalSec", "deliveryLate", "futureImpact")}
            else:
                graphs = [tensor_graph(raw_graph(f, config["nodeSchema"]), config["normalizers"])
                          for f in history + [frame]]
                with torch.no_grad():
                    result, _ = model(graphs)
                by_id = {node.split(":", 1)[1]: index for index, node in enumerate(graphs[-1]["ids"]["TRUCK"])}
                indices = [by_id[t["truckId"]] for t in trucks]
                raw = {"remainingArrivalSec": result[indices, 0].numpy(),
                       "deliveryLate": torch.sigmoid(result[indices, 1]).numpy(),
                       "futureImpact": torch.sigmoid(result[indices, 2]).numpy()}
            sla = calibrated(raw["deliveryLate"], config["calibration"]["deliveryLate"])
            impact = calibrated(raw["futureImpact"], config["calibration"]["futureImpact"])
            radius = config["calibration"]["remainingArrivalSec"]["radiusSec"]
            for index, truck in enumerate(trucks):
                eta = float(raw["remainingArrivalSec"][index]) if truck.get("etaEligible", True) else None
                predictions.append({"truckId": truck["truckId"], "remainingArrivalSec": eta,
                                    "etaLowerSec": max(0., eta-radius) if eta is not None and radius is not None else None,
                                    "etaUpperSec": eta+radius if eta is not None and radius is not None else None,
                                    "slaProbability": float(sla[index]) if truck.get("deliveryEligible", True) else None,
                                    "futureImpactProbability": float(impact[index])})
        warnings = ["Predictions and uncertainty were trained/calibrated on simulated operations; no observed freight validation."]
        warnings.extend(domain_warnings(frame, self.manifest))
        if model_id == "gnn-temporal-v1" and not history:
            warnings.append("No preceding graph is available; the temporal model uses one current graph with zero recurrent history.")
        return {"schemaVersion": RESPONSE_VERSION, "featureSchemaVersion": FEATURE_VERSION,
                "featureSchemaHash": FEATURE_HASH, "modelId": model_id, "modelVersion": MODEL_VERSION,
                "networkId": self.manifest["networkId"], "graphSha256": self.manifest["graphSha256"],
                "source": "TRAINED_SIMULATION_MODEL", "stateFingerprint": request["stateFingerprint"],
                "clockSec": frame["clockSec"], "predictions": predictions, "calibration": config["calibration"],
                "latencyMs": (time.perf_counter()-start)*1000., "warnings": warnings,
                "provenance": "SIMULATED_PREDICTION"}
