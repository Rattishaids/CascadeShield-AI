"""Validate Milestone 2 snapshots and create a neutral tensor pack or optional PyG HeteroData.

The standard-library path never imports Torch. Zero fill encodes missing input values and
must be read together with x_mask; it is not an invented observation. Outcomes are kept
outside x. This module does not split data, train a model, or compute research metrics.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any

SNAPSHOT_VERSION = "cascadeshield.graph-snapshot/1.0"
PACK_VERSION = "cascadeshield.tensor-pack/1.0"
REALIZED_TIMESTAMP_TARGETS = {
    "arrival_sec", "delivered_at_sec", "actual_dock_start_sec", "actual_dock_end_sec",
}
FORBIDDEN_INPUTS = {
    "arrival_sec", "arrival_delay_sec", "delivered_at_sec", "delivery_lateness_sec",
    "actual_dock_start_sec", "actual_dock_end_sec", "estimated_arrival_sec",
    "direct_risk_score", "cascade_risk_score", "conditional_road_arrival_sec",
    "estimated_dock_start_sec", "estimated_dock_end_sec",
}


def _finite(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{label} must be a finite number")
    return float(value)


def convert_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Return validated deterministic node and edge arrays without changing source records."""
    if snapshot.get("schemaVersion") != SNAPSHOT_VERSION:
        raise ValueError("Unsupported graph snapshot schemaVersion")
    provenance = snapshot.get("provenance", {})
    if provenance.get("operations") != "SIMULATED" or provenance.get("outcomeLabels") != "SIMULATED_OUTCOME":
        raise ValueError("This converter requires explicitly simulated operations and outcomes")
    if provenance.get("geography") != "REAL_GEOGRAPHIC":
        raise ValueError("Real geographic provenance must be explicit")
    clock = _finite(snapshot.get("simulationTime", {}).get("clockSec"), "clockSec")
    if clock < 0:
        raise ValueError("clockSec cannot be negative")
    schemas = snapshot.get("featureSchemas")
    if not isinstance(schemas, dict):
        raise ValueError("featureSchemas must be a type-to-feature-schema map")
    node_stores: dict[str, dict[str, Any]] = {}
    features_by_type: dict[str, list[str]] = {}
    for node_type, schema in sorted(schemas.items()):
        if not isinstance(node_type, str) or not isinstance(schema, list):
            raise ValueError("Invalid node type/schema")
        names = [entry.get("name") for entry in schema]
        if any(not isinstance(name, str) or not name for name in names) or len(names) != len(set(names)):
            raise ValueError(f"Duplicate or invalid feature names for {node_type}")
        if any(name in FORBIDDEN_INPUTS or name.startswith("actual_") for name in names):
            raise ValueError("Outcome/prediction fields are not allowed in input x")
        if any(entry.get("dtype") not in {"float64", "float32"} for entry in schema):
            raise ValueError("Only declared floating-point input schemas are supported")
        features_by_type[node_type] = names
        node_stores[node_type] = {"node_ids": [], "resource_ids": [], "feature_names": names,
                                  "feature_schema": schema, "x": [], "x_mask": [], "provenance": []}
    node_lookup: dict[str, tuple[str, int]] = {}
    nodes = snapshot.get("nodes", [])
    if not isinstance(nodes, list):
        raise ValueError("nodes must be a list")
    for node in sorted(nodes, key=lambda item: item.get("id", "")):
        node_id, node_type = node.get("id"), node.get("type")
        if not isinstance(node_id, str) or not node_id or node_id in node_lookup:
            raise ValueError("Node IDs must be unique non-empty strings")
        if node_type not in node_stores:
            raise ValueError(f"Missing feature schema for node type {node_type}")
        if node.get("provenance") not in {"SIMULATED", "REAL_GEOGRAPHIC"}:
            raise ValueError(f"Unexpected node provenance for {node_id}")
        values, masks = node.get("features"), node.get("availableMask")
        if not isinstance(values, dict) or not isinstance(masks, dict):
            raise ValueError(f"Feature values and availableMask required for {node_id}")
        names = features_by_type[node_type]
        if set(values) != set(names) or set(masks) != set(names):
            raise ValueError(f"Feature values/mask do not match declared schema for {node_id}")
        x, mask = [], []
        for name in names:
            available = masks[name]
            if type(available) is not bool or available != (values[name] is not None):
                raise ValueError(f"Availability mask contradicts value for {node_id}.{name}")
            x.append(_finite(values[name], f"{node_id}.{name}") if available else 0.0)
            mask.append(available)
        store = node_stores[node_type]
        node_lookup[node_id] = (node_type, len(store["node_ids"]))
        store["node_ids"].append(node_id)
        store["resource_ids"].append(node.get("resourceId"))
        store["provenance"].append(node["provenance"])
        store["x"].append(x)
        store["x_mask"].append(mask)
    relation_stores: dict[tuple[str, str, str], dict[str, Any]] = {}
    edge_ids: set[str] = set()
    edges = snapshot.get("edges", [])
    if not isinstance(edges, list):
        raise ValueError("edges must be a list")
    for edge in sorted(edges, key=lambda item: item.get("id", "")):
        edge_id = edge.get("id")
        if not isinstance(edge_id, str) or not edge_id or edge_id in edge_ids:
            raise ValueError("Edge IDs must be unique non-empty strings")
        edge_ids.add(edge_id)
        if edge.get("source") not in node_lookup or edge.get("target") not in node_lookup:
            raise ValueError(f"Unknown directed edge endpoint for {edge_id}")
        source_type, source_index = node_lookup[edge["source"]]
        target_type, target_index = node_lookup[edge["target"]]
        relation = edge.get("type")
        if not isinstance(relation, str) or not relation:
            raise ValueError("Directed edge type is required")
        weight = _finite(edge.get("weight"), f"{edge_id}.weight")
        start = _finite(edge.get("validFromSec"), f"{edge_id}.validFromSec")
        end = _finite(edge.get("validUntilSec"), f"{edge_id}.validUntilSec")
        if not 0 <= weight <= 1 or start < 0 or end <= start:
            raise ValueError(f"Invalid dependency weight/time validity for {edge_id}")
        if edge.get("provenance") not in {"SIMULATED", "SIMULATED_PREDICTION", "REAL_GEOGRAPHIC"}:
            raise ValueError(f"Unexpected edge provenance for {edge_id}")
        features = edge.get("features", {})
        if not isinstance(features, dict) or any(name in FORBIDDEN_INPUTS or name.startswith("actual_") for name in features):
            raise ValueError(f"Invalid input edge features for {edge_id}")
        for name, value in features.items():
            _finite(value, f"{edge_id}.{name}")
        key = (source_type, relation, target_type)
        store = relation_stores.setdefault(key, {"edge_type": list(key), "edge_ids": [],
                                                "edge_index": [[], []], "edge_attr": [],
                                                "edge_attr_names": ["weight", "valid_from_sec", "valid_until_sec"],
                                                "additional_features": [], "provenance": []})
        store["edge_ids"].append(edge_id)
        store["edge_index"][0].append(source_index)
        store["edge_index"][1].append(target_index)
        store["edge_attr"].append([weight, start, end])
        store["additional_features"].append(features)
        store["provenance"].append(edge["provenance"])
    target_groups: dict[str, list[dict[str, Any]]] = {}
    for key, required_provenance in (("predictions", "SIMULATED_PREDICTION"), ("realizedLabels", "SIMULATED_OUTCOME")):
        targets = snapshot.get(key, [])
        if not isinstance(targets, list):
            raise ValueError(f"{key} must be a list")
        seen: set[tuple[str, str]] = set()
        converted = []
        for target in sorted(targets, key=lambda item: (item.get("nodeId", ""), item.get("target", ""))):
            node_id, name = target.get("nodeId"), target.get("target")
            if node_id not in node_lookup or not isinstance(name, str) or not name:
                raise ValueError(f"Unknown target node or missing target name in {key}")
            signature = (node_id, name)
            if signature in seen:
                raise ValueError(f"Duplicate target {signature}")
            seen.add(signature)
            if target.get("provenance") != required_provenance:
                raise ValueError(f"{key} provenance must be {required_provenance}")
            value = _finite(target.get("value"), f"{key}.{name}")
            at_clock = _finite(target.get("atClockSec"), f"{key}.{name}.atClockSec")
            if at_clock > clock + 1e-7 or at_clock < 0 or value < 0:
                raise ValueError("Target is from a future observation or has an invalid value")
            if key == "realizedLabels" and name in REALIZED_TIMESTAMP_TARGETS and value > at_clock + 1e-7:
                raise ValueError("A realized event timestamp cannot follow its observation timestamp or snapshot clock")
            node_type, index = node_lookup[node_id]
            converted.append({**target, "node_type": node_type, "node_index": index})
        target_groups[key] = converted
    canonical = json.dumps(snapshot, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return {"schemaVersion": PACK_VERSION, "sourceSchemaVersion": SNAPSHOT_VERSION,
            "sourceSha256": hashlib.sha256(canonical).hexdigest(),
            "metadata": {key: snapshot.get(key) for key in ("simulationTime", "networkId", "runId", "scenarioId", "randomSeed", "provenance")},
            "node_stores": node_stores, "edge_stores": [relation_stores[key] for key in sorted(relation_stores)],
            "predictions": target_groups["predictions"], "realized_labels": target_groups["realizedLabels"],
            "encoding": {"missing_inputs": "zero-fill with false x_mask; zero is not an observation",
                         "labels": "SIMULATED_OUTCOME only; unavailable outcomes have no record",
                         "predictions": "separate rule-based outputs; never training ground truth"}}


def to_heterodata(pack: dict[str, Any]) -> Any:
    """Optional dependency boundary; prediction outputs remain separate from x and y."""
    try:
        import torch
        from torch_geometric.data import HeteroData
    except ImportError as exc:
        raise RuntimeError("--heterodata requires installed torch and torch-geometric; no dependencies were installed") from exc
    data = HeteroData()
    for node_type, store in pack["node_stores"].items():
        count, width = len(store["node_ids"]), len(store["feature_names"])
        data[node_type].num_nodes = count
        data[node_type].x = torch.tensor(store["x"], dtype=torch.float64).reshape(count, width)
        data[node_type].x_mask = torch.tensor(store["x_mask"], dtype=torch.bool).reshape(count, width)
        data[node_type].node_ids = store["node_ids"]
        data[node_type].resource_ids = store["resource_ids"]
        data[node_type].feature_names = store["feature_names"]
        data[node_type].feature_schema = store["feature_schema"]
        data[node_type].provenance = store["provenance"]
        outcomes = [row for row in pack["realized_labels"] if row["node_type"] == node_type]
        target_names = sorted({row["target"] for row in outcomes})
        y = torch.zeros((count, len(target_names)), dtype=torch.float64)
        y_mask = torch.zeros((count, len(target_names)), dtype=torch.bool)
        target_index = {name: index for index, name in enumerate(target_names)}
        for row in outcomes:
            y[row["node_index"], target_index[row["target"]]] = row["value"]
            y_mask[row["node_index"], target_index[row["target"]]] = True
        data[node_type].y, data[node_type].y_mask = y, y_mask
        data[node_type].target_names = target_names
        data[node_type].target_provenance = "SIMULATED_OUTCOME"
    for store in pack["edge_stores"]:
        key = tuple(store["edge_type"])
        data[key].edge_index = torch.tensor(store["edge_index"], dtype=torch.long).reshape(2, len(store["edge_ids"]))
        data[key].edge_attr = torch.tensor(store["edge_attr"], dtype=torch.float64).reshape(len(store["edge_ids"]), 3)
        data[key].edge_ids, data[key].edge_attr_names = store["edge_ids"], store["edge_attr_names"]
        data[key].provenance = store["provenance"]
        data[key].additional_features = store["additional_features"]
    data.snapshot_metadata = pack["metadata"]
    data.rule_based_predictions = pack["predictions"]
    data.source_sha256 = pack["sourceSha256"]
    data.encoding = pack["encoding"]
    data.validate(raise_on_error=True)
    return data


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--heterodata", action="store_true", help="Save a PyG object (.pt); Torch/PyG must already be installed")
    args = parser.parse_args()
    source = args.snapshot.resolve()
    target = args.output.resolve()
    if source == target:
        parser.error("Output must differ from the immutable source snapshot")
    if target.exists():
        parser.error("Output already exists; choose a new path to preserve previous evidence")
    try:
        pack = convert_snapshot(json.loads(source.read_text(encoding="utf-8-sig")))
        target.parent.mkdir(parents=True, exist_ok=True)
        if args.heterodata:
            data = to_heterodata(pack)
            import torch
            torch.save(data, target)
        else:
            target.write_text(json.dumps(pack, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    except (ValueError, RuntimeError, ImportError, OSError) as exc:
        parser.exit(1, f"Snapshot conversion failed: {exc}\n")
    print(f"Validated {sum(len(store['node_ids']) for store in pack['node_stores'].values())} nodes, "
          f"{sum(len(store['edge_ids']) for store in pack['edge_stores'])} directed edges; "
          f"{len(pack['realized_labels'])} simulated outcome labels. Saved {target}")


if __name__ == "__main__":
    main()
