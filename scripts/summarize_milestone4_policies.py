"""Summarize actual frozen paired policy runs; never generates or changes outcomes."""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import random
from statistics import mean

ROOT = Path(__file__).resolve().parents[1]
PROVENANCE = "SIMULATED_RESEARCH_EXPERIMENT"
METRICS = ("deliveryCount", "completedDeliveries", "unfinishedDeliveries", "slaViolations", "slaViolationRate",
           "totalDeliveryLatenessSec", "downstreamAffectedResources", "totalReroutes", "travelDistanceM",
           "signedAdditionalDistanceM", "positiveAdditionalDistanceM", "modeledOperationalCost", "recoveryTimeSec",
           "recoveryCensored", "finalClockSec", "constraintViolations", "decisionComputationMs")
CONTRASTS = (("B5_XGB_V1", "B3"), ("B5_XGB_V1", "B4"), ("B5_XGB_V1", "B5_RULE_V1"),
             ("B5_XGB_CF_V1", "B5_XGB_V1"), ("B5_XGB_V1", "B5_XGB_NO_GRAPH_V1"),
             ("B5_GNN_TEMPORAL_V1", "B5_GNN_STATIC_V1"), ("B5_GNN_TEMPORAL_V1", "B5_XGB_V1"))
CONTRAST_METRICS = ("slaViolationRate", "slaViolations", "unfinishedDeliveries", "totalDeliveryLatenessSec",
                    "downstreamAffectedResources", "positiveAdditionalDistanceM", "modeledOperationalCost",
                    "recoveryTimeSec", "recoveryCensored", "constraintViolations", "decisionComputationMs")
MODEL_POLICIES = {"B5_XGB_V1": "xgb-v1", "B5_XGB_NO_GRAPH_V1": "xgb-no-graph-v1",
                  "B5_GNN_STATIC_V1": "gnn-static-v1", "B5_GNN_TEMPORAL_V1": "gnn-temporal-v1",
                  "B5_XGB_CF_V1": "xgb-v1"}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def percentile(values, probability):
    ordered = sorted(values)
    index = (len(ordered) - 1) * probability
    low = math.floor(index); high = math.ceil(index)
    return ordered[low] + (ordered[high] - ordered[low]) * (index - low)


def clustered_difference(left: dict, right: dict, expected: dict, metric: str, uncertainty: dict) -> dict:
    """Pair cases first, average within whole seed, resample seeds, never snapshots."""
    missing = sorted(set(expected) - (set(left) & set(right)))
    if missing:
        raise ValueError("Missing paired scenarios: " + ", ".join(missing))
    groups = defaultdict(list); families = defaultdict(list)
    for sid, case in expected.items():
        difference = float(left[sid][metric]) - float(right[sid][metric])
        groups[case["seed"]].append(difference)
        families[case["family"]].append(difference)
    seeds = sorted(groups)
    seed_means = [mean(groups[seed]) for seed in seeds]
    rng = random.Random(uncertainty["bootstrapSeed"])
    boot = [mean(rng.choices(seed_means, k=len(seeds))) for _ in range(uncertainty["pairedBootstrapReplicates"])]
    tail = (1 - uncertainty["confidenceLevel"]) / 2
    return {"difference": mean(seed_means), "interval": [percentile(boot, tail), percentile(boot, 1-tail)],
            "caseCount": len(expected), "seedClusterCount": len(seeds),
            "seedMeanDifferences": {str(seed): mean(groups[seed]) for seed in seeds},
            "familyMeanDifferences": {family: mean(values) for family, values in sorted(families.items())},
            "interpretation": "Left minus right. Descriptive percentile interval over whole seed clusters; only four final seed clusters. Recovery times are restricted observations when censored."}


def flatten(record: dict, case: dict, protocol: dict) -> dict:
    run = record["run"]; metrics = run["metrics"]; summary = run["finalSummary"]
    for field in ("scenarioId", "seed", "policyId", "inputFingerprint"):
        if record[field] != run[field]:
            raise ValueError("Outer/run identity disagreement: " + field)
    if record["seed"] != case["seed"] or record["family"] != case["family"] or record["inputFingerprint"] != case["inputFingerprint"]:
        raise ValueError("Run differs from frozen scenario declaration")
    if run["provenance"] != PROVENANCE or metrics["provenance"] != PROVENANCE:
        raise ValueError("Unlabelled outcome provenance")
    if summary.get("comparisonMode") != "EQUAL_ACTIONS":
        raise ValueError("Policy did not use the controlled common action set")
    for field in ("decisionIntervalSec", "rolloutHorizonSec", "maxDecisions"):
        if record["parameters"][field] != protocol["policyBudget"][field]:
            raise ValueError("Run differs from declared policy budget: " + field)
    if summary["decisionLimit"] != protocol["policyBudget"]["maxDecisions"]:
        raise ValueError("Final summary decision limit differs from declared budget")
    decisions = run["decisions"]
    if len(decisions) > protocol["policyBudget"]["maxDecisions"]:
        raise ValueError("Policy exceeds frozen maximum decision budget")
    actions = Counter(); candidate_count = 0; executed_candidates = 0
    for decision in decisions:
        alternatives = decision["alternatives"]; candidate_count += len(alternatives)
        executed_candidates += sum(a.get("metrics") is not None for a in alternatives)
        if any(a["action"]["type"] not in protocol["comparisonActions"] for a in alternatives):
            raise ValueError("Unexpected policy action in comparison")
        selected = [a for a in alternatives if a["action"]["id"] == decision["selectedActionId"]]
        if len(selected) != 1 or not selected[0]["feasible"]:
            raise ValueError("Selected action is missing, duplicated, or infeasible")
        actions[selected[0]["action"]["type"]] += 1
    row = {name: record[name] for name in ("scenarioId", "seed", "family", "policyId", "inputFingerprint")}
    for name in METRICS:
        value = metrics[name]
        if not isinstance(value, (int, float, bool)) or not math.isfinite(value):
            raise ValueError("Missing/nonfinite policy metric: " + name)
        row[name] = value
    row.update(decisionCount=len(decisions), candidateCount=candidate_count,
               simulationRolloutCount=summary.get("simulationRolloutCount", executed_candidates),
               inferenceRequests=summary.get("inferenceRequests", 0), failedInferenceRequests=summary.get("failedInferenceRequests", 0),
               fallbackDecisions=summary.get("fallbackDecisions", 0), inferenceServiceMs=summary.get("inferenceServiceMs", 0),
               constraintRejections=summary["constraintRejections"], decisionLimitReached=summary["decisionLimitReached"],
               constraintAuditEntries=len(summary["constraintAudit"]), finalRunComplete=summary["complete"],
               finalRunCensored=summary["censored"],
               executionWallMs=record["executionWallMs"], javaHeapPoolPeakBytes=record["javaHeapPoolPeakBytes"],
               actionCounts=dict(actions), failureReasons=summary.get("failureReasons", {}))
    return row


def summarize(directory: Path, manifest: Path, protocol_path: Path) -> tuple[dict, list[dict]]:
    protocol = json.loads(protocol_path.read_text(encoding="utf-8-sig"))
    generation = json.loads(manifest.read_text(encoding="utf-8-sig"))
    frozen_path = directory / "final_assessment_freeze.json"
    frozen = json.loads(frozen_path.read_text(encoding="utf-8-sig"))
    expected = {r["scenario"]["id"]: {"seed": r["scenario"]["seed"], "family": r["scenario"]["profile"],
                "inputFingerprint": r["scenario"]["inputFingerprint"]} for r in generation["cases"] if r["split"] == "final"}
    omissions_path = directory / "omitted_policy_variants.json"
    omissions = json.loads(omissions_path.read_text(encoding="utf-8-sig")) if omissions_path.exists() else {"omittedPolicyIds": []}
    omitted = set(omissions["omittedPolicyIds"])
    selection = frozen["selectionManifest"]
    expected_omissions = {policy for policy, model in MODEL_POLICIES.items() if model not in selection["validatedModelIds"]}
    if omitted != expected_omissions:
        raise ValueError("Omitted policies differ from actually validated model eligibility")
    policies = [p for p in protocol["finalPolicyIds"] if p not in omitted]
    if frozen["protocolSha256"] != sha(protocol_path) or generation["protocolSha256"] != sha(protocol_path):
        raise ValueError("Final outcomes/inputs use a different frozen protocol")
    if frozen["graphSha256"] != generation["graphSha256"]:
        raise ValueError("Final outcomes/inputs use a different network")
    if selection["generationManifestSha256"] != sha(manifest):
        raise ValueError("Generation manifest differs from frozen model-selection inputs")
    development_cases = {r["scenario"]["id"]: {"seed": r["scenario"]["seed"],
        "family": r["scenario"]["profile"], "inputFingerprint": r["scenario"]["inputFingerprint"]}
        for r in generation["cases"] if r["split"] in protocol["developmentDiagnostics"]["splits"]
        and r["scenario"]["seed"] in protocol["developmentDiagnostics"]["seeds"]
        and r["scenario"]["profile"] in protocol["developmentDiagnostics"]["families"]}
    diagnostic_variants = {v["id"]: v for v in protocol["developmentDiagnostics"]["variants"]}
    diagnostic_pairs = {(sid, policy) for sid in development_cases for policy in diagnostic_variants}
    rows = []; hashes = {}; seen = set(); diagnostics = {}; seen_diagnostics = set()
    for path in sorted(directory.glob("*__*.json")):
        record = json.loads(path.read_text(encoding="utf-8-sig"))
        sid = record["scenarioId"]; policy = record["policyId"]
        # Development diagnostics share the append-only raw directory. Check their
        # identities and declared budgets explicitly; never pool them into final rows.
        if (sid, policy) in diagnostic_pairs:
            if (sid, policy) in seen_diagnostics:
                raise ValueError("Duplicate development diagnostic")
            if record["selectionManifestSha256"] != "NOT_APPLICABLE":
                raise ValueError("Development diagnostic unexpectedly uses final model selection")
            if any(record[key] != frozen[key] for key in ("protocolSha256", "graphSha256")):
                raise ValueError("Development diagnostic differs from declared protocol/network")
            variant = diagnostic_variants[policy]
            if any(record["parameters"][key] != variant[key] for key in ("maxDecisions", "rolloutHorizonSec")):
                raise ValueError("Development diagnostic differs from its declared budget")
            diagnostic_protocol = {**protocol, "policyBudget": {**protocol["policyBudget"], **variant}}
            diagnostics[path.name] = {"sha256": sha(path),
                "row": flatten(record, development_cases[sid], diagnostic_protocol)}
            seen_diagnostics.add((sid, policy))
            continue
        if sid not in expected or policy not in policies:
            raise ValueError("Undeclared scenario or policy in raw directory: " + path.name)
        identity = (sid, policy)
        if identity in seen:
            raise ValueError("Duplicate paired policy run")
        seen.add(identity)
        if any(record[key] != frozen[key] for key in ("protocolSha256", "graphSha256", "selectionManifestSha256")):
            raise ValueError("Run checksum differs from frozen experiment")
        rows.append(flatten(record, expected[sid], protocol)); hashes[path.name] = sha(path)
    if seen_diagnostics and seen_diagnostics != diagnostic_pairs:
        raise ValueError(f"Incomplete declared development diagnostics: {len(seen_diagnostics)}/{len(diagnostic_pairs)}")
    all_pairs = {(sid, policy) for sid in expected for policy in policies}
    if seen != all_pairs:
        raise ValueError(f"Incomplete paired execution: {len(seen)}/{len(all_pairs)}; missing {len(all_pairs-seen)}")
    by_policy = defaultdict(list)
    for row in rows:
        by_policy[row["policyId"]].append(row)
    summaries = {}
    numeric = [name for name in rows[0] if name not in {"scenarioId", "seed", "family", "policyId", "inputFingerprint", "actionCounts", "failureReasons"}]
    for policy, group in sorted(by_policy.items()):
        actions = Counter(); failures = Counter()
        for row in group:
            actions.update(row["actionCounts"]); failures.update(row["failureReasons"])
        summaries[policy] = {"caseCount": len(group), "meansPerRun": {key: mean(float(r[key]) for r in group) for key in numeric},
            "totals": {key: sum(r[key] for r in group) for key in ("deliveryCount", "completedDeliveries", "unfinishedDeliveries", "slaViolations", "constraintViolations", "decisionCount", "inferenceRequests", "failedInferenceRequests", "fallbackDecisions", "simulationRolloutCount")},
            "pooledSlaViolationRate": sum(r["slaViolations"] for r in group) / sum(r["deliveryCount"] for r in group),
            "recoveriesCensored": sum(r["recoveryCensored"] for r in group), "selectedActions": dict(actions), "failureReasons": dict(failures),
            "finalRunsComplete": sum(r["finalRunComplete"] for r in group),
            "finalRunsCensored": sum(r["finalRunCensored"] for r in group),
            "constraintAuditEntries": sum(r["constraintAuditEntries"] for r in group),
            "maximumJavaHeapPoolPeakBytes": max(r["javaHeapPoolPeakBytes"] for r in group),
            "families": {family: {metric: mean(float(r[metric]) for r in group if r["family"] == family) for metric in CONTRAST_METRICS} for family in sorted({r["family"] for r in group})}}
    contrasts = {}
    for left, right in CONTRASTS:
        if left in by_policy and right in by_policy:
            a = {r["scenarioId"]: r for r in by_policy[left]}; b = {r["scenarioId"]: r for r in by_policy[right]}
            contrasts[left + " minus " + right] = {metric: clustered_difference(a, b, expected, metric, protocol["uncertainty"]) for metric in CONTRAST_METRICS}
    report = {"schemaVersion": "cascadeshield.milestone4-policy-summary/1.0", "checkedAtUtc": datetime.now(timezone.utc).isoformat(),
        "provenance": PROVENANCE, "pairedExecutionComplete": True, "caseCount": len(expected), "policyCount": len(policies), "runCount": len(rows),
        "seedClusterCount": len({c["seed"] for c in expected.values()}), "protocolSha256": sha(protocol_path), "generationManifestSha256": sha(manifest),
        "selectionManifestSha256": frozen["selectionManifestSha256"], "rawOutcomeSha256": hashes, "omissions": omissions,
        "separatelyCheckedDevelopmentDiagnostics": diagnostics,
        "executionAudit": {"matchedDeclaredFinalPairs": len(seen), "declaredFinalPairs": len(all_pairs),
            "developmentDiagnosticRunCountExcludedFromFinal": len(diagnostics),
            "allSelectedActionsWereDeclaredAndFeasible": True,
            "allRunBudgetsMatchedFrozenDeclarations": True,
            "totalDecisionCount": sum(r["decisionCount"] for r in rows),
            "totalCandidateCount": sum(r["candidateCount"] for r in rows),
            "totalSimulationRolloutCount": sum(r["simulationRolloutCount"] for r in rows),
            "totalConstraintViolations": sum(r["constraintViolations"] for r in rows),
            "totalConstraintAuditEntries": sum(r["constraintAuditEntries"] for r in rows),
            "totalUnfinishedDeliveries": sum(r["unfinishedDeliveries"] for r in rows),
            "finalRunCensoredCount": sum(r["finalRunCensored"] for r in rows),
            "recoveryCensoredCount": sum(r["recoveryCensored"] for r in rows),
            "totalInferenceRequests": sum(r["inferenceRequests"] for r in rows),
            "totalFailedInferenceRequests": sum(r["failedInferenceRequests"] for r in rows),
            "totalFallbackDecisions": sum(r["fallbackDecisions"] for r in rows)},
        "policies": summaries, "pairedContrasts": contrasts, "uncertainty": protocol["uncertainty"],
        "limitations": ["Actual simulated outcomes on real bounded Chennai geography; no observed freight or field effectiveness evidence.",
            "Only four independent final seed clusters; intervals are descriptive and uncorrected for multiple comparisons.",
            "Censored recoveryTimeSec is a restricted observation, not an observed recovery event; unfinished deliveries and censoring are reported separately.",
            "Model-assisted candidate states can differ from no-intervention training trajectories; forecasts do not identify causal action effects.",
            "Java heap-pool peaks exclude Python service, GPU and native/container memory and are not simultaneous process RSS.",
            "Equal maximum action/budget/horizon declarations do not imply identical eligibility rules, realized decisions, or wall-clock compute."]}
    return report, rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", type=Path, default=ROOT / "reports/milestone4_policy_raw")
    parser.add_argument("--manifest", type=Path, default=ROOT / "data/processed/milestone4/corpus_v2/generation_manifest.json")
    parser.add_argument("--protocol", type=Path, default=ROOT / "config/milestone4_protocol_v2.json")
    parser.add_argument("--output", type=Path, default=ROOT / "reports/MILESTONE_4_POLICY_BENCHMARK.json")
    parser.add_argument("--csv", type=Path, default=ROOT / "reports/MILESTONE_4_POLICY_BENCHMARK.csv")
    args = parser.parse_args()
    report, rows = summarize(args.raw, args.manifest, args.protocol)
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    with args.csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0])); writer.writeheader()
        for row in rows:
            writer.writerow({key: json.dumps(value, sort_keys=True) if isinstance(value, dict) else value for key, value in row.items()})
    print(json.dumps({key: report[key] for key in ("pairedExecutionComplete", "caseCount", "policyCount", "runCount")}))


if __name__ == "__main__":
    main()
