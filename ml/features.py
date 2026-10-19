"""The ordered as-of feature contract shared with Java MlFeatureExtractor."""
from __future__ import annotations

import hashlib
import json
import math
from typing import Any

FEATURE_VERSION = "cascadeshield.ml-features/1.0"
REQUEST_VERSION = "cascadeshield.ml-request/1.0"
RESPONSE_VERSION = "cascadeshield.ml-response/1.0"
MODEL_VERSION = "milestone4-v1"
PROVENANCE = "SIMULATED_RESEARCH_EXPERIMENT"
FEATURES = (
    "clock_sec", "remaining_distance_m", "max_speed_kph", "current_speed_kph",
    "departure_remaining_sec", "deadline_slack_sec", "load_kg", "capacity_kg",
    "driver_available", "driver_shift_remaining_sec", "driver_duty_sec", "dock_service_sec",
    "dock_open_remaining_sec", "reservation_start_remaining_sec", "reservation_end_remaining_sec",
    "dock_occupied", "dock_queue_count", "warehouse_dock_capacity", "known_incident_count",
    "route_closure_count", "route_slowdown_count", "route_max_severity",
    "known_incident_remaining_sec", "graph_in_degree", "graph_out_degree", "graph_risk_score",
    "rule_road_remaining_sec", "rule_dock_remaining_sec", "rule_eta_known", "priority_high",
    "wait_remaining_sec", "distance_speed_remaining_sec",
)
GRAPH_FEATURES = frozenset({"graph_in_degree", "graph_out_degree", "graph_risk_score"})
FEATURE_HASH = hashlib.sha256(json.dumps(FEATURES, separators=(",", ":")).encode()).hexdigest()
ADVERSE_CODES = frozenset({"DOCK_QUEUE", "DOCK_CLOSED", "DELIVERY_LATE", "DRIVER_BUSY",
                           "DRIVER_UNAVAILABLE", "SHIFT_EXHAUSTED"})
FORBIDDEN = frozenset({"outcomes", "labels", "nodeLabels", "exogenousSchedule", "futureSchedule",
                       "deliveredAtSec", "actualDockEndSec", "arrivalSec"})


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def feature_vector(values: dict[str, Any], names: tuple[str, ...] = FEATURES) -> list[float]:
    if not isinstance(values, dict) or set(values) != set(FEATURES):
        raise ValueError("Features must exactly match the frozen Java/Python feature vocabulary")
    vector = []
    for name in names:
        value = values[name]
        if value is None:
            vector.append(float("nan"))  # explicit missing value, handled by fitted preprocessing.
        elif isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"Nonfinite or nonnumeric feature: {name}")
        else:
            vector.append(float(value))
    return vector


def strip_labels(frame: dict[str, Any]) -> dict[str, Any]:
    """Build an inference request from a corpus frame without exposing later outcomes."""
    result = {key: value for key, value in frame.items() if key not in {"nodeLabels", "labels"}}
    result["trucks"] = [{key: value for key, value in truck.items() if key != "labels"}
                        for truck in frame["trucks"]]
    graph = dict(result["graphSnapshot"])
    graph["realizedLabels"] = []
    result["graphSnapshot"] = graph
    return result
