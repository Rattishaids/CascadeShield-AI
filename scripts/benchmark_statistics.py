"""Paired, seed-clustered descriptive statistics for executed simulated experiments.

No training, imputation, optimization or missing benchmark rows are performed.
Bootstrap intervals describe this scenario generator, not observed field effects.
"""
from __future__ import annotations

from collections import defaultdict
import math
import random
import statistics

METRICS = (
    "slaViolationRate", "totalDeliveryLatenessSec", "downstreamAffectedResources",
    "totalReroutes", "positiveAdditionalDistanceM", "modeledOperationalCost",
    "recoveryTimeSec", "decisionComputationMs", "constraintViolations",
)


def describe(values):
    values = [float(v) for v in values]
    if not values or not all(math.isfinite(v) for v in values):
        raise ValueError("Statistics require nonempty finite measured values")
    return {"n": len(values), "mean": statistics.fmean(values),
            "sample_sd": statistics.stdev(values) if len(values) > 1 else None,
            "minimum": min(values), "maximum": max(values)}


def percentile(values, fraction):
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    low, high = math.floor(position), math.ceil(position)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def summarize(rows, *, bootstrap_samples=2000, bootstrap_seed=3013):
    """Rows include profile, seed, comparisonMode, policyId and actual Metrics columns."""
    if not rows:
        raise ValueError("No executed results to aggregate")
    by_scenario = defaultdict(list)
    groups = defaultdict(list)
    for row in rows:
        if row.get("provenance") != "SIMULATED_RESEARCH_EXPERIMENT":
            raise ValueError("Only realized simulated experiment rows are accepted")
        key = (row["profile"], int(row["seed"]), row["comparisonMode"])
        by_scenario[key].append(row)
        groups[(row["comparisonMode"], row["policyId"])].append(row)
    for key, paired in by_scenario.items():
        if len({r["inputFingerprint"] for r in paired}) != 1:
            raise ValueError(f"Mismatched paired initial inputs: {key}")
        ids = [r["policyId"] for r in paired]
        if len(set(ids)) != len(ids):
            raise ValueError(f"Duplicate policy result for scenario: {key}")
    descriptive = []
    for (mode, policy), values in sorted(groups.items()):
        item = {"comparison_mode": mode, "policy": policy,
                "scenario_count": len(values), "seed_count": len({int(r["seed"]) for r in values}),
                "recovery_censored_count": sum(bool(r["recoveryCensored"]) for r in values),
                "unfinished_deliveries": sum(int(r["unfinishedDeliveries"]) for r in values),
                "pooled_sla_violation_rate": sum(int(r["slaViolations"]) for r in values) / sum(int(r["deliveryCount"]) for r in values),
                "metrics": {metric: describe([r[metric] for r in values]) for metric in METRICS}}
        item["metrics"]["recoveryTimeSec"]["interpretation"] = "Includes horizon lower bounds for censored recovery; inspect censor count"
        descriptive.append(item)
    paired_results = []
    for mode in sorted({r["comparisonMode"] for r in rows}):
        policies = {r["policyId"] for r in rows if r["comparisonMode"] == mode}
        if "B4" not in policies:
            continue
        for reference in sorted(policies - {"B4"}):
            pairs = []
            for key, scenario_rows in sorted(by_scenario.items()):
                if key[2] != mode:
                    continue
                indexed = {r["policyId"]: r for r in scenario_rows}
                if "B4" not in indexed or reference not in indexed:
                    raise ValueError(f"Missing paired B4/{reference} outcome: {key}")
                pairs.append((key, indexed["B4"], indexed[reference]))
            for metric in METRICS:
                differences = [(key[1], float(b4[metric]) - float(baseline[metric])) for key, b4, baseline in pairs]
                clusters = defaultdict(list)
                for seed, delta in differences:
                    clusters[seed].append(delta)
                cluster_means = [statistics.fmean(values) for _, values in sorted(clusters.items())]
                rng = random.Random(bootstrap_seed)
                bootstrap = [statistics.fmean(rng.choices(cluster_means, k=len(cluster_means))) for _ in range(bootstrap_samples)] if len(cluster_means) > 1 else []
                lower, upper = (percentile(bootstrap, .025), percentile(bootstrap, .975)) if bootstrap else (None, None)
                pair_mean = statistics.fmean(delta for _, delta in differences)
                paired_results.append({"comparison_mode": mode, "enhanced": "B4", "reference": reference,
                    "metric": metric, "paired_scenarios": len(pairs), "independent_seed_clusters": len(clusters),
                    "mean_delta_enhanced_minus_reference": pair_mean,
                    "sample_sd_of_scenario_deltas": statistics.stdev(delta for _, delta in differences) if len(differences) > 1 else None,
                    "seed_cluster_bootstrap_95_interval": [lower, upper],
                    "negative_delta_means_lower_metric": True,
                    "supports_lower_metric_in_this_simulated_matrix": upper is not None and upper < 0,
                    "censored_recovery_pair_count": sum(bool(a["recoveryCensored"] or b["recoveryCensored"]) for _, a, b in pairs) if metric == "recoveryTimeSec" else 0})
    return {"method": "Paired scenario deltas; profiles kept together in deterministic seed-cluster bootstrap",
            "bootstrap_samples": bootstrap_samples, "bootstrap_seed": bootstrap_seed,
            "uncertainty_scope": "Configured simulated generator and policy budgets; no field generalization, no multiplicity-adjusted significance claim",
            "descriptive": descriptive, "paired_comparisons": paired_results}
