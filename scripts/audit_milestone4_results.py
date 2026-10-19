"""Audit recorded M4 results with matched denominators; no fitting or simulation."""
from __future__ import annotations

import argparse
from collections import defaultdict
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import random
from statistics import mean

ROOT = Path(__file__).resolve().parents[1]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def quantile(values: list[float], p: float) -> float:
    values = sorted(values)
    index = (len(values) - 1) * p
    lo, hi = math.floor(index), math.ceil(index)
    return values[lo] + (values[hi] - values[lo]) * (index - lo)


def matched(rows: dict, left: str, right: str, target: str, uncertainty: dict) -> dict:
    a, b = rows[left, target], rows[right, target]
    common = sorted(set(a) & set(b))
    if not common:
        raise ValueError("No matched observations")
    groups = defaultdict(list)
    losses_a, losses_b = [], []
    for key in common:
        x, y = a[key], b[key]
        if x["truth"] != y["truth"] or x["seed"] != y["seed"]:
            raise ValueError("Truth or seed differs on a matched observation")
        truth = x["truth"]
        loss_a = abs(x["prediction"] - truth) if target == "remainingArrivalSec" else (x["prediction"] - truth) ** 2
        loss_b = abs(y["prediction"] - truth) if target == "remainingArrivalSec" else (y["prediction"] - truth) ** 2
        losses_a.append(loss_a); losses_b.append(loss_b)
        groups[x["seed"]].append(loss_a - loss_b)
    seed_means = [mean(groups[seed]) for seed in sorted(groups)]
    rng = random.Random(uncertainty["bootstrapSeed"])
    boot = [mean(rng.choices(seed_means, k=len(seed_means))) for _ in range(uncertainty["pairedBootstrapReplicates"])]
    tail = (1 - uncertainty["confidenceLevel"]) / 2
    return {"left": left, "right": right, "target": target,
        "loss": "absolute error seconds" if target == "remainingArrivalSec" else "Brier squared error",
        "nMatched": len(common), "leftAvailable": len(a), "rightAvailable": len(b),
        "scenarioCount": len({key[0] for key in common}), "seedClusterCount": len(groups),
        "pooledLeftMeanLoss": mean(losses_a), "pooledRightMeanLoss": mean(losses_b),
        "pooledDifference": mean(losses_a) - mean(losses_b),
        "equalSeedMeanDifference": mean(seed_means),
        "equalSeedDifferenceInterval": [quantile(boot, tail), quantile(boot, 1 - tail)],
        "seedMeanDifferences": {str(seed): mean(values) for seed, values in sorted(groups.items())},
        "intervalInterpretation": "Left minus right, each seed weighted equally after matching example identities. Descriptive percentile bootstrap over only four whole seed clusters; correlated snapshots are never independent bootstrap units. Pooled point estimates weight examples and can differ from the equal-seed interval's estimand."}


def prediction_audit(metrics_path: Path, rows_path: Path, protocol: dict) -> dict:
    p = json.loads(metrics_path.read_text(encoding="utf-8-sig"))
    rows = defaultdict(dict)
    with rows_path.open(newline="", encoding="utf-8-sig") as stream:
        for record in csv.DictReader(stream):
            key = (record["scenarioId"], record["truckId"], float(record["clockSec"]))
            group = rows[record["modelId"], record["target"]]
            if key in group:
                raise ValueError("Duplicate model/target/example identity")
            converted = {name: float(record[name]) for name in ("truth", "prediction")}
            if not all(math.isfinite(v) for v in converted.values()):
                raise ValueError("Nonfinite recorded outcome/prediction")
            converted["seed"] = int(record["seed"])
            if converted["seed"] not in protocol["splits"]["final"]:
                raise ValueError("Non-final prediction row")
            group[key] = converted
    all_metrics = [{k: v for k, v in r.items() if k != "calibrationBins"}
        for r in p["metrics"] if r["group"] == "ALL"]
    for record in all_metrics:
        if record["n"] != len(rows[record["modelId"], record["target"]]):
            raise ValueError("Primary metric n disagrees with recorded prediction rows")
    requested = [("xgb-v1", "rule_conditional_road_eta", "remainingArrivalSec"),
        ("xgb-v1", "rule_known_operational_eta_only", "remainingArrivalSec"),
        ("xgb-v1", "xgb-no-graph-v1", "remainingArrivalSec"),
        ("gnn-temporal-v1", "gnn-static-v1", "remainingArrivalSec"),
        ("gnn-temporal-v1", "xgb-v1", "remainingArrivalSec"),
        ("xgb-v1", "rule_dock_slack_known_only", "deliveryLate"),
        ("xgb-v1", "xgb-no-graph-v1", "deliveryLate"),
        ("gnn-static-v1", "xgb-v1", "deliveryLate"),
        ("gnn-temporal-v1", "gnn-static-v1", "deliveryLate"),
        ("xgb-v1", "graph_rule_score", "futureImpact"),
        ("xgb-v1", "xgb-no-graph-v1", "futureImpact"),
        ("gnn-temporal-v1", "gnn-static-v1", "futureImpact")]
    return {"sourceSha256": {metrics_path.name: digest(metrics_path), rows_path.name: digest(rows_path)},
        "scenarioCount": p["dataset"]["scenarioCount"], "truckExamples": p["dataset"]["truckExamples"],
        "targets": p["dataset"]["targets"], "allMetrics": all_metrics,
        "matchedComparisons": [matched(rows, a, b, target, protocol["uncertainty"]) for a, b, target in requested],
        "etaIntervals": p["etaIntervals"], "inferenceLatencyMs": p["inferenceLatencyMs"],
        "nodeMetrics": [{k: v for k, v in r.items() if k != "calibrationBins"} for r in p["nodeMetrics"]],
        "limitations": p["limitations"]}


def diagnostic_audit(path: Path, protocol: dict) -> dict:
    p = json.loads(path.read_text(encoding="utf-8-sig"))
    rows = p["runs"]
    declared = protocol["developmentDiagnostics"]
    expected = {(seed, family, v["id"]) for seed in declared["seeds"] for family in declared["families"] for v in declared["variants"]}
    actual = {(r["seed"], r["family"], r["policyId"]) for r in rows}
    if actual != expected or len(actual) != len(rows):
        raise ValueError("Development diagnostic declaration incomplete/duplicated")
    metrics = ("slaViolations", "totalDeliveryLatenessSec", "unfinishedDeliveries", "constraintViolations", "decisionComputationMs", "recoveryCensored")
    by_variant = {}
    for v in declared["variants"]:
        group = [r for r in rows if r["policyId"] == v["id"]]
        by_variant[v["id"]] = {"caseCount": len(group), "totals": {k: sum(r["run"]["metrics"][k] for r in group) for k in metrics},
            "meanDecisionCount": mean(len(r["run"]["decisions"]) for r in group),
            "budgetLimitReachedCount": sum(r["run"]["finalSummary"]["decisionLimitReached"] for r in group),
            "meanExecutionWallMs": mean(r["executionWallMs"] for r in group),
            "cases": [{"scenarioId": r["scenarioId"], "seed": r["seed"], "family": r["family"],
                **{k: r["run"]["metrics"][k] for k in metrics}} for r in group]}
    return {"sourceSha256": digest(path), "runCount": len(rows), "variants": by_variant,
        "interpretation": "Four development cases, two seeds, diagnostic evidence only. No independent final assessment or post-hoc retuning of historical B4."}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "reports/milestone4_independent_results_audit.json")
    args = parser.parse_args()
    protocol = json.loads((ROOT / "config/milestone4_protocol_v2.json").read_text(encoding="utf-8-sig"))
    report = {"schemaVersion": "cascadeshield.milestone4-independent-results-audit/1.0",
        "checkedAtUtc": datetime.now(timezone.utc).isoformat(), "provenance": "SIMULATED_RESEARCH_EXPERIMENT",
        "prediction": prediction_audit(ROOT / "reports/MILESTONE_4_PREDICTION_METRICS.json", ROOT / "reports/MILESTONE_4_PREDICTION_METRICS_rows.csv", protocol),
        "developmentB4Diagnostics": diagnostic_audit(ROOT / "reports/milestone4_policy_raw/diagnostics_results.json", protocol)}
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "predictionScenarioCount": report["prediction"]["scenarioCount"], "diagnosticRunCount": report["developmentB4Diagnostics"]["runCount"]}))


if __name__ == "__main__":
    main()
