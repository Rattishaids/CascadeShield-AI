"""Held-out prediction comparison from frozen models; no fitting or threshold selection."""
from __future__ import annotations

import csv
import json
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
import torch

from .data import load_corpus, examples, dataset_manifest, future_impact
from .features import REQUEST_VERSION, FEATURE_VERSION, FEATURE_HASH, PROVENANCE, strip_labels
from .inference import ModelBundle
from .gnn import raw_graph, tensor_graph
from .metrics import regression, classification, clustered_loss_difference
from .training import write_json, sha, TARGETS


def evaluate(corpus: Path, models: Path, output: Path, expected_split="final"):
    bundle = ModelBundle(models)
    if not bundle.manifest.get("frozen"):
        raise ValueError("Model selection has not been frozen")
    scenarios = load_corpus(corpus, {expected_split})
    if expected_split == "final":
        unlock = json.loads((corpus.parent / "final_unlock.json").read_text(encoding="utf-8-sig"))
        if unlock.get("selectionManifestSha256") != sha(models / "manifest.json"):
            raise ValueError("Final corpus was not generated under this exact frozen model selection")
        if sha(corpus.parent / "generation_manifest.json") != bundle.manifest["generationManifestSha256"]:
            raise ValueError("Final scenario declaration changed after model selection")
        if sha(Path(bundle.manifest["protocolSourcePath"])) != bundle.manifest["protocolSha256"]:
            raise ValueError("Declared protocol changed after model selection")
        for split, expected in bundle.manifest["sourceCorpusSha256"].items():
            if sha(corpus.parent / f"{split}.jsonl") != expected:
                raise ValueError("Development corpus changed after selection freeze")
    development_seeds = {seed for values in bundle.manifest["dataset"]["seedsBySplit"].values() for seed in values}
    if expected_split == "final" and any(s["seed"] in development_seeds for s in scenarios):
        raise ValueError("Final assessment reused an exposed development/calibration seed")
    rows = examples(scenarios)
    prediction_map, latency, node_results = {}, defaultdict(list), defaultdict(lambda: [[], []])
    inference_started = time.perf_counter()
    for model_id in bundle.models:
        for scenario in scenarios:
            history = []
            for index, original in enumerate(scenario["frames"]):
                frame = strip_labels(original)
                request = {"schemaVersion": REQUEST_VERSION, "featureSchemaVersion": FEATURE_VERSION,
                           "featureSchemaHash": FEATURE_HASH, "networkId": bundle.manifest["networkId"],
                           "graphSha256": bundle.manifest["graphSha256"], "modelId": model_id,
                           "stateFingerprint": frame["stateFingerprint"], "frame": frame, "history": history[-2:]}
                started = time.perf_counter(); response = bundle.predict(request)
                latency[model_id].append((time.perf_counter()-started)*1000.)
                for p in response["predictions"]:
                    prediction_map[(model_id, scenario["scenarioId"], index, p["truckId"])] = p
                if model_id.startswith("gnn"):
                    config = bundle.manifest["models"][model_id]
                    gs = [tensor_graph(raw_graph(f, config["nodeSchema"]), config["normalizers"]) for f in history[-2:] + [frame]]
                    with torch.no_grad():
                        _, logits = bundle.models[model_id](gs)
                    for kind, values in logits.items():
                        for node, prob in zip(gs[-1]["ids"][kind], torch.sigmoid(values).numpy()):
                            key = (model_id, kind)
                            label = future_impact(scenario, original, node)
                            if label is not None:
                                node_results[key][0].append(label); node_results[key][1].append(float(prob))
                history.append(frame)
    results, raw_rows = [], []
    for model_id in bundle.models:
        for target in TARGETS:
            eligible = [r for r in rows if r["labels"][target] is not None]
            field = {"remainingArrivalSec": "remainingArrivalSec", "deliveryLate": "slaProbability", "futureImpact": "futureImpactProbability"}[target]
            y = [r["labels"][target] for r in eligible]
            p = [prediction_map[(model_id, r["scenarioId"], r["frameIndex"], r["truckId"])][field] for r in eligible]
            if any(value is None for value in p):
                raise ValueError("A trained provider omitted an eligible prediction")
            metrics = regression(y, p) if target == "remainingArrivalSec" else classification(y, p)
            results.append({"modelId": model_id, "target": target, "group": "ALL", **metrics})
            for family in sorted({r["family"] for r in eligible}):
                indices = [i for i, r in enumerate(eligible) if r["family"] == family]
                metrics = regression([y[i] for i in indices], [p[i] for i in indices]) if target == "remainingArrivalSec" else classification([y[i] for i in indices], [p[i] for i in indices])
                results.append({"modelId": model_id, "target": target, "group": "family:"+family, **metrics})
            for severity_group, predicate in (("no_current_route_exposure", lambda value: value <= 0),
                                              ("moderate", lambda value: 0 < value < .8),
                                              ("severe", lambda value: value >= .8)):
                indices = [i for i, r in enumerate(eligible) if predicate(r["severity"])]
                if indices:
                    metrics = regression([y[i] for i in indices], [p[i] for i in indices]) if target == "remainingArrivalSec" else classification([y[i] for i in indices], [p[i] for i in indices])
                    results.append({"modelId": model_id, "target": target, "group": "severity:"+severity_group, **metrics})
            for row, truth, pred in zip(eligible, y, p):
                raw_rows.append({"modelId": model_id, "target": target, "scenarioId": row["scenarioId"], "seed": row["seed"],
                                 "family": row["family"], "truckId": row["truckId"], "clockSec": row["clockSec"],
                                 "truth": truth, "prediction": pred, "absoluteError": abs(pred-truth),
                                 "provenance": "SIMULATED_OUTCOME_VS_SIMULATED_PREDICTION"})
    baseline_specs = (
        ("distance_speed", "remainingArrivalSec", lambda r: r["features"]["distance_speed_remaining_sec"] + r["features"]["departure_remaining_sec"]),
        ("rule_conditional_road_eta", "remainingArrivalSec", lambda r: r["features"]["rule_road_remaining_sec"]),
        ("rule_known_operational_eta_only", "remainingArrivalSec", lambda r: r["baseline"].get("remainingArrivalSec")),
        ("training_mean_remaining_time", "remainingArrivalSec", lambda r: bundle.manifest["baselineStatistics"]["remainingArrivalSec"]),
        ("sla_slack_threshold", "deliveryLate", lambda r: float(r["features"]["distance_speed_remaining_sec"] + (r["features"]["dock_service_sec"] or 0) > r["features"]["deadline_slack_sec"])),
        ("rule_dock_slack_known_only", "deliveryLate", lambda r: r["baseline"].get("slackRisk")),
        ("training_sla_prevalence", "deliveryLate", lambda r: bundle.manifest["baselineStatistics"]["deliveryLate"]),
        ("graph_rule_score", "futureImpact", lambda r: r["features"]["graph_risk_score"]),
        ("training_impact_prevalence", "futureImpact", lambda r: bundle.manifest["baselineStatistics"]["futureImpact"]),
    )
    for model_id, target, predict in baseline_specs:
        eligible = [r for r in rows if r["labels"][target] is not None and predict(r) is not None]
        y, p = [r["labels"][target] for r in eligible], [predict(r) for r in eligible]
        metrics = regression(y, p) if target == "remainingArrivalSec" else classification(y, p)
        results.append({"modelId": model_id, "target": target, "group": "ALL", "coverageNote": "Known-only baselines use a smaller explicit n; do not treat missing ETA as a fabricated zero", **metrics})
        # Give every learned provider the identical rows as each deterministic
        # comparator, so a known-only baseline's smaller denominator stays fair.
        field = {"remainingArrivalSec": "remainingArrivalSec", "deliveryLate": "slaProbability", "futureImpact": "futureImpactProbability"}[target]
        for trained_id in bundle.models:
            matched = [prediction_map[(trained_id, r["scenarioId"], r["frameIndex"], r["truckId"])][field] for r in eligible]
            paired_metrics = regression(y, matched) if target == "remainingArrivalSec" else classification(y, matched)
            baseline_loss = np.abs(np.asarray(y)-np.asarray(p)) if target == "remainingArrivalSec" else np.square(np.asarray(y)-np.asarray(p))
            trained_loss = np.abs(np.asarray(y)-np.asarray(matched)) if target == "remainingArrivalSec" else np.square(np.asarray(y)-np.asarray(matched))
            results.append({"modelId": trained_id, "target": target, "group": "MATCHED_BASELINE:"+model_id,
                            "pairedLossDifference": float(np.mean(trained_loss-baseline_loss)),
                            "pairedLossUncertainty": clustered_loss_difference([r["seed"] for r in eligible], trained_loss-baseline_loss),
                            "pairedLossDifferenceDirection": "NEGATIVE_MEANS_LOWER_LEARNED_MAE_OR_BRIER_ON_IDENTICAL_ROWS",
                            "pairedScenarioCount": len({r["scenarioId"] for r in eligible}), **paired_metrics})
        for row, truth, pred in zip(eligible, y, p):
            raw_rows.append({"modelId": model_id, "target": target, "scenarioId": row["scenarioId"], "seed": row["seed"],
                             "family": row["family"], "truckId": row["truckId"], "clockSec": row["clockSec"],
                             "truth": truth, "prediction": pred, "absoluteError": abs(pred-truth),
                             "provenance": "SIMULATED_OUTCOME_VS_RULE_OR_STATISTICAL_PREDICTION"})
    uncertainty = {}
    for model_id in bundle.models:
        eligible = [r for r in rows if r["labels"]["remainingArrivalSec"] is not None]
        covered = []
        for row in eligible:
            p = prediction_map[(model_id, row["scenarioId"], row["frameIndex"], row["truckId"])]
            y = row["labels"]["remainingArrivalSec"]
            if p["etaLowerSec"] is not None:
                covered.append(p["etaLowerSec"] <= y <= p["etaUpperSec"])
        uncertainty[model_id] = {"n": len(covered), "empiricalCoverage": float(np.mean(covered)) if covered else None,
                                "calibration": bundle.manifest["models"][model_id]["calibration"]["remainingArrivalSec"]}
    node_metrics = [{"modelId": key[0], "nodeType": key[1], "target": "new_adverse_resource_impact_300sec",
                     "calibration": "RAW_SIGMOID_NODE_HEAD", **classification(*values)} for key, values in node_results.items()]
    report = {"schemaVersion": "cascadeshield.prediction-evaluation/1.0", "split": expected_split,
              "provenance": PROVENANCE, "modelsFrozenBeforeFinal": bundle.manifest["frozen"],
              "modelManifestSha256": sha(models / "manifest.json"), "assessmentCorpusSha256": sha(corpus),
              "dataset": dataset_manifest(scenarios, rows), "metrics": results, "nodeMetrics": node_metrics,
              "etaIntervals": uncertainty,
              "inferenceLatencyMs": {key: {"n": len(v), "mean": float(np.mean(v)), "median": float(np.median(v)),
                                            "p95": float(np.quantile(v, .95)), "max": float(np.max(v))} for key, v in latency.items()},
              "totalEvaluationSec": time.perf_counter()-inference_started,
              "limitations": ["No observed freight outcomes were used", "Repeated snapshots are correlated within scenario and seed",
                              "GNN observes all typed resource-node features; XGB uses current-truck features and neighborhood summaries, so this is not a pure architecture-only comparison",
                              "Future-impact is a new recorded adverse-event association, not incident causality or ongoing-state exposure",
                              "Final families include distribution shifts; calibration has no field guarantee"]}
    output.mkdir(parents=True, exist_ok=True)
    stem = "MILESTONE_4_PREDICTION_METRICS" if expected_split == "final" else "milestone4_validation_prediction_metrics"
    target = output / f"{stem}.json"
    if target.exists():
        raise ValueError("Assessment report already exists; preserve its evidence and choose a new output directory")
    write_json(target, report)
    columns = ["modelId", "target", "group", "n", "mae", "rmse", "bias", "positive", "negative", "precision", "recall", "f1", "prAuc", "rocAuc", "brier", "confusionMatrix"]
    with (output / f"{stem}.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore"); writer.writeheader(); writer.writerows(results)
    with (output / f"{stem}_rows.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(raw_rows[0])); writer.writeheader(); writer.writerows(raw_rows)
    failure_cases = {target: sorted([r for r in raw_rows if r["target"] == target], key=lambda r: r["absoluteError"], reverse=True)[:20]
                     for target in TARGETS}
    write_json(output / ("milestone4_final_prediction_failure_cases.json" if expected_split == "final" else "milestone4_validation_failure_cases.json"), failure_cases)
    return report
