"""Validate independent simulator scenarios and prepare supervised examples as of time t."""
from __future__ import annotations

import json
import math
from collections import Counter
from pathlib import Path
from typing import Any

from scripts.convert_graph_snapshot import convert_snapshot
from .features import FEATURES, FEATURE_VERSION, FEATURE_HASH, PROVENANCE, ADVERSE_CODES, feature_vector, canonical_hash, FORBIDDEN

CORPUS_VERSION = "cascadeshield.ml-corpus/1.0"
SPLITS = frozenset({"train", "validation", "calibration", "final"})


def _finite(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"Invalid {name}")
    return float(value)


def validate_frame(frame: dict[str, Any], *, inference: bool = False) -> dict[str, Any]:
    if not isinstance(frame, dict) or frame.get("schemaVersion") != "cascadeshield.ml-frame/1.0" or frame.get("featureSchemaVersion") != FEATURE_VERSION or frame.get("featureSchemaHash") != FEATURE_HASH:
        raise ValueError("Incompatible prediction frame/feature schema")
    if inference:
        def reject_future(value):
            if isinstance(value, dict):
                for key, item in value.items():
                    if key in FORBIDDEN:
                        raise ValueError("Outcome/private schedule is forbidden in prediction input: " + key)
                    reject_future(item)
            elif isinstance(value, list):
                for item in value: reject_future(item)
        reject_future(frame)
    clock = _finite(frame.get("clockSec"), "frame clock")
    if clock < 0:
        raise ValueError("Negative prediction clock")
    graph = frame.get("graphSnapshot")
    if not isinstance(graph, dict):
        raise ValueError("graphSnapshot is required")
    pack = convert_snapshot(graph)
    if abs(graph["simulationTime"]["clockSec"] - clock) > 1e-7:
        raise ValueError("Graph clock differs from prediction cutoff")
    trucks = frame.get("trucks")
    if not isinstance(trucks, list):
        raise ValueError("trucks must be a list")
    truck_ids = set()
    graph_trucks = set(pack["node_stores"].get("TRUCK", {}).get("resource_ids", []))
    if inference and ("nodeLabels" in frame or "labels" in frame or graph.get("realizedLabels")):
        raise ValueError("Inference cannot receive outcome labels")
    for truck in trucks:
        truck_id = truck.get("truckId")
        if not isinstance(truck_id, str) or truck_id in truck_ids or truck_id not in graph_trucks:
            raise ValueError("Duplicate or missing graph truck")
        truck_ids.add(truck_id)
        feature_vector(truck.get("features"))
        if abs(truck["features"]["clock_sec"] - clock) > 1e-7:
            raise ValueError("Feature clock differs from prediction cutoff")
        if inference and "labels" in truck:
            raise ValueError("Inference cannot receive later truck outcomes")
    return pack


def load_corpus(path: Path, allowed_splits: set[str] | frozenset[str] = SPLITS) -> list[dict[str, Any]]:
    scenarios = []
    ids, fingerprints = set(), set()
    seeds: dict[int, str] = {}
    # Iterate lines so large exports do not require a second whole-file string copy.
    with path.open(encoding="utf-8-sig") as handle:
        for line_no, line in enumerate(handle, 1):
            if not line.strip():
                continue
            scenario = json.loads(line)
            if scenario.get("schemaVersion") != CORPUS_VERSION or scenario.get("provenance") != PROVENANCE:
                raise ValueError(f"Line {line_no}: unsupported corpus schema/provenance")
            split = scenario.get("split")
            if split not in allowed_splits:
                raise ValueError(f"Split {split!r} is forbidden in this phase; final assessment stays unopened")
            sid = scenario.get("scenarioId")
            fingerprint = scenario.get("inputFingerprint", scenario.get("scenarioFingerprint"))
            seed = scenario.get("seed")
            if not isinstance(seed, int) or isinstance(seed, bool) or seed in {11, 22, 33, 44, 55}:
                raise ValueError("A fresh integer seed is required; published Milestone 3 seeds are forbidden")
            if not sid or sid in ids or not fingerprint or fingerprint in fingerprints:
                raise ValueError("Duplicate scenario or scenario input fingerprint")
            if seed in seeds and seeds[seed] != split:
                raise ValueError("Related seeds cross training/assessment boundaries")
            ids.add(sid); fingerprints.add(fingerprint); seeds[seed] = split
            horizon = _finite(scenario.get("horizonSec"), "horizon")
            if not scenario.get("frames") or not isinstance(scenario.get("outcomes"), dict):
                raise ValueError("Timestamped frames and separately joined authoritative outcomes are required")
            previous = -1.0
            for frame in scenario["frames"]:
                clock = frame.get("clockSec")
                if clock <= previous or clock > horizon:
                    raise ValueError("Frames must have strictly increasing cutoffs within the outcome horizon")
                previous = clock
                validate_frame(frame)
            scenarios.append(scenario)
    if not scenarios:
        raise ValueError("Empty supervised corpus")
    return scenarios


def _outcome_map(scenario: dict[str, Any], kind: str) -> dict[str, dict[str, Any]]:
    return {row["id"]: row for row in scenario["outcomes"].get(kind, [])}


def reconstruct_labels(scenario: dict[str, Any], frame: dict[str, Any], truck: dict[str, Any]) -> dict[str, Any]:
    """Join future outcomes only into y. No private schedule is accepted as a feature."""
    clock = frame["clockSec"]
    terminal = _outcome_map(scenario, "trucks").get(truck["truckId"])
    if terminal is None:
        raise ValueError("Truck outcome is absent")
    arrival = terminal["arrivalSec"]
    eta_eligible = arrival < 0 or arrival > clock + 1e-7
    remaining = max(0.0, arrival - clock) if eta_eligible and arrival >= 0 else None
    deliveries = [d for d in scenario["outcomes"].get("deliveries", []) if d.get("truckId") == truck["truckId"]]
    pending = [d for d in deliveries if d["deliveredAtSec"] < 0 or d["deliveredAtSec"] > clock + 1e-7]
    complete = bool(deliveries) and all(d["deliveredAtSec"] >= 0 for d in deliveries)
    late = int(any(d["deliveredAtSec"] > d["deadlineSec"] + 1e-7 for d in deliveries)) if pending and complete else None
    future = future_impact(scenario, frame, "TRUCK:" + truck["truckId"])
    return {"remainingArrivalSec": remaining, "deliveryLate": late, "futureImpact": future,
            "etaEligible": eta_eligible, "deliveryEligible": bool(pending),
            "arrivalCensored": eta_eligible and arrival < 0, "deliveryCensored": bool(pending) and not complete}


def future_impact(scenario: dict[str, Any], frame: dict[str, Any], node_id: str) -> int | None:
    clock = frame["clockSec"]
    outcomes = scenario["outcomes"]
    if not outcomes.get("completed", False) and outcomes.get("finalClockSec", scenario["horizonSec"]) < clock + 300.0 - 1e-7:
        return None  # A partially observed negative (or positive) window is not a complete target.
    until = min(clock + 300.0, scenario["horizonSec"])
    for impact in scenario["outcomes"].get("realizedImpacts", []):
        if impact.get("predicted") or impact.get("code") not in ADVERSE_CODES:
            continue
        if clock + 1e-7 < impact["startSec"] <= until + 1e-7:
            ids = set(impact.get("resourceIds", [])) | {"TRUCK:" + t for t in impact.get("truckIds", [])}
            if node_id in ids:
                return 1
    return 0


def examples(scenarios: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for scenario in scenarios:
        for frame_index, frame in enumerate(scenario["frames"]):
            for node_label in frame.get("nodeLabels", []):
                expected = future_impact(scenario, frame, node_label["nodeId"])
                if node_label.get("futureImpact") != expected or node_label.get("eligible") != (expected is not None):
                    raise ValueError("Stored resource target/mask differs from reconstructed authoritative outcome")
            for truck in frame["trucks"]:
                labels = reconstruct_labels(scenario, frame, truck)
                provided = truck.get("labels", {})
                for name in ("remainingArrivalSec", "deliveryLate", "futureImpact"):
                    if name in provided:
                        if (provided[name] is None) != (labels[name] is None):
                            raise ValueError(f"Stored {name} missingness differs from reconstructed target")
                        if provided[name] is not None and abs(float(provided[name]) - float(labels[name])) > 1e-6:
                            raise ValueError(f"Stored {name} differs from independently reconstructed target")
                rows.append({"scenarioId": scenario["scenarioId"], "seed": scenario["seed"],
                             "split": scenario["split"], "family": scenario["family"], "clockSec": frame["clockSec"],
                             "truckId": truck["truckId"], "features": truck["features"], "labels": labels,
                             "baseline": truck.get("baseline", {}), "frameIndex": frame_index,
                             "severity": truck["features"]["route_max_severity"]})
    return rows


def dataset_manifest(scenarios: list[dict[str, Any]], rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {"provenance": PROVENANCE, "scenarioCount": len(scenarios), "truckExamples": len(rows),
            "scenariosBySplit": dict(Counter(s["split"] for s in scenarios)),
            "examplesBySplit": dict(Counter(r["split"] for r in rows)),
            "seedsBySplit": {split: sorted({s["seed"] for s in scenarios if s["split"] == split}) for split in SPLITS},
            "scenarioFleetSizesBySplit": {split: sorted({len(s["frames"][0]["trucks"]) for s in scenarios if s["split"] == split}) for split in SPLITS},
            "featureMissingValuesBySplit": {split: {name: sum(r["features"][name] is None for r in rows if r["split"] == split)
                                                    for name in FEATURES} for split in SPLITS},
            "censoredTargets": {"arrival": sum(r["labels"]["arrivalCensored"] for r in rows),
                                "delivery": sum(r["labels"]["deliveryCensored"] for r in rows)},
            "scenarioFingerprints": {s["scenarioId"]: s.get("inputFingerprint", s.get("scenarioFingerprint")) for s in scenarios},
            "frameFingerprints": [canonical_hash({"scenarioId": s["scenarioId"], "clockSec": f["clockSec"],
                                                   "graphSnapshot": f["graphSnapshot"],
                                                   "features": [t["features"] for t in f["trucks"]]})
                                  for s in scenarios for f in s["frames"]],
            "targets": {name: {"available": sum(r["labels"][name] is not None for r in rows),
                               "missingOrIneligible": sum(r["labels"][name] is None for r in rows),
                               "positive": sum(r["labels"][name] == 1 for r in rows) if name != "remainingArrivalSec" else None}
                        for name in ("remainingArrivalSec", "deliveryLate", "futureImpact")}}
