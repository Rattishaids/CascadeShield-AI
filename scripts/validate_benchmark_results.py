"""Independently inspect immutable declared M3 exports; never submit jobs or alter the simulator."""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import time

ROOT = Path(__file__).resolve().parents[1]
PROVENANCE = "SIMULATED_RESEARCH_EXPERIMENT"
INCIDENT_PATTERN = re.compile(r"\bI\d{3,}\b")
WEIGHTS = (.35, .25, .15, .15, .05, .05)
GRAPH = json.loads((ROOT / "data/processed/chennai_osm/road_graph.json").read_text(encoding="utf-8"))
GRAPH_SHA256 = hashlib.sha256((ROOT / "data/processed/chennai_osm/road_graph.json").read_bytes()).hexdigest()
EDGES = {edge["id"]: edge for edge in GRAPH["edges"]}
RESTRICTIONS = GRAPH["restrictions"]


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def close(actual, expected, name, tolerance=1e-6):
    require(math.isfinite(actual) and abs(actual - expected) <= tolerance, f"{name}: {actual!r} != {expected!r}")


def json_file(path):
    # The acquisition journal is written by the independent running process.
    for attempt in range(3):
        try:
            return json.loads(path.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError:
            if attempt == 2:
                raise
            time.sleep(.05)


def validate_failed_attempt(attempt, entry, selected_ids):
    """Keep interrupted progress evidence distinct from complete outcome rows."""
    path = (ROOT / attempt["rawJson"]).resolve()
    require(path.is_relative_to(ROOT) and path.is_file(), "Failed-attempt archive is unavailable/outside the project")
    require(hashlib.sha256(path.read_bytes()).hexdigest() == attempt["rawSha256"], "Failed-attempt archive checksum changed")
    failed = json_file(path)
    require(failed["id"] == attempt["id"] and failed["id"] not in selected_ids, "A failed attempt entered the selected complete corpus")
    require(failed["status"] == "FAILED" and failed["request"] == entry["request"], "Failed archive status/inputs differ from the retried declared request")
    require(failed["provenance"] == PROVENANCE and failed["graphSha256"] == GRAPH_SHA256, "Failed attempt geographic source/provenance changed")
    require(failed["completedRuns"] == attempt["completedRuns"] and failed["error"] == attempt["error"], "Failed progress/error evidence changed")
    require(0 <= failed["completedRuns"] <= failed["totalRuns"], "Failed progress is outside its declared run count")
    persisted = len((failed.get("result") or {}).get("runs", []))
    require(persisted <= failed["completedRuns"], "Failed archive claims more persisted outcomes than executed progress")
    return {"id": failed["id"], "completedProgressRows": failed["completedRuns"], "persistedPartialOutcomeRows": persisted,
            "rawJson": attempt["rawJson"], "rawSha256": attempt["rawSha256"], "excludedFromFinalCorpus": True}


def validate_statistics(final):
    """Recompute moments and paired deltas without the production statistics helper."""
    rows, statistics = final["rows"], final["statistics"]
    groups = {}
    indexed = {}
    for row in rows:
        groups.setdefault((row["comparisonMode"], row["policyId"]), []).append(row)
        indexed[(row["comparisonMode"], row["profile"], row["seed"], row["policyId"])] = row
    descriptions = statistics["descriptive"]
    require(len(descriptions) == len(groups), "A descriptive policy group is missing/repeated")
    for group in descriptions:
        values = groups[(group["comparison_mode"], group["policy"])]
        require(group["scenario_count"] == len(values) and group["seed_count"] == len({r["seed"] for r in values}), "Descriptive condition counts differ")
        require(group["recovery_censored_count"] == sum(r["recoveryCensored"] for r in values), "Descriptive recovery censoring count differs")
        require(group["unfinished_deliveries"] == sum(r["unfinishedDeliveries"] for r in values), "Descriptive unfinished-delivery count differs")
        close(group["pooled_sla_violation_rate"], sum(r["slaViolations"] for r in values) / sum(r["deliveryCount"] for r in values), "Pooled SLA rate")
        for metric, description in group["metrics"].items():
            measured = [r[metric] for r in values]
            mean = sum(measured) / len(measured)
            sd = math.sqrt(sum((value - mean) ** 2 for value in measured) / (len(measured) - 1))
            require(description["n"] == len(measured), "Descriptive metric count differs")
            for field, expected in (("mean", mean), ("sample_sd", sd), ("minimum", min(measured)), ("maximum", max(measured))):
                close(description[field], expected, "Descriptive " + metric + " " + field)
    comparisons = statistics["paired_comparisons"]
    expected_comparisons = sum(len({r["policyId"] for r in rows if r["comparisonMode"] == mode}) - 1 for mode in {r["comparisonMode"] for r in rows}) * 9
    require(len(comparisons) == expected_comparisons, "A paired metric comparison is missing/repeated")
    identities = set()
    for comparison in comparisons:
        mode, reference, metric = comparison["comparison_mode"], comparison["reference"], comparison["metric"]
        identity = (mode, reference, metric)
        require(identity not in identities and comparison["enhanced"] == "B4", "Repeated/changed paired comparison")
        identities.add(identity)
        pairs = [(r, indexed[(mode, r["profile"], r["seed"], reference)]) for r in rows if r["comparisonMode"] == mode and r["policyId"] == "B4"]
        differences = [enhanced[metric] - baseline[metric] for enhanced, baseline in pairs]
        mean = sum(differences) / len(differences)
        sd = math.sqrt(sum((delta - mean) ** 2 for delta in differences) / (len(differences) - 1))
        require(comparison["paired_scenarios"] == len(pairs) and comparison["independent_seed_clusters"] == len({enhanced["seed"] for enhanced, _ in pairs}), "Paired scenario/cluster counts differ")
        close(comparison["mean_delta_enhanced_minus_reference"], mean, "Paired " + metric + " mean")
        close(comparison["sample_sd_of_scenario_deltas"], sd, "Paired " + metric + " variation")
        lower, upper = comparison["seed_cluster_bootstrap_95_interval"]
        require(lower is not None and upper is not None and math.isfinite(lower) and math.isfinite(upper) and lower <= upper, "Bootstrap interval is unavailable/nonfinite/reversed")
        require(comparison["supports_lower_metric_in_this_simulated_matrix"] == (upper < 0), "Reported directional support differs from its interval")
        censored = sum(enhanced["recoveryCensored"] or baseline["recoveryCensored"] for enhanced, baseline in pairs) if metric == "recoveryTimeSec" else 0
        require(comparison["censored_recovery_pair_count"] == censored, "Paired recovery censoring count differs")
    return {"descriptiveGroups": len(descriptions), "pairedMetricComparisons": len(comparisons),
            "meansVariationAndCountsRecomputed": True, "bootstrapIntervals": "Finite ordered intervals checked; bootstrap resampling relies on the separately executed statistics tests"}


def validate_job(job, entry, pairing, report):
    require(job["id"] == entry["id"] and job["request"] == entry["request"], "Raw job differs from declared journal request")
    require(job["status"] == "COMPLETED", "Declared job is incomplete/failed")
    require(job["provenance"] == PROVENANCE and job["result"]["provenance"] == PROVENANCE, "Actual experiment provenance missing")
    require(job["graphSha256"] == GRAPH_SHA256 and job["networkId"] == GRAPH["networkId"], "A declared job changed the immutable geographic source")
    result = job["result"]
    scenarios = {scenario["id"]: scenario for scenario in result["scenarios"]}
    mode = job["request"]["comparisonMode"]
    expected_policies = set(job["request"]["policies"])
    expected_policies |= {"B4_" + name for name in job["request"]["ablations"] if name != "FULL"}
    require(len(result["runs"]) == len(scenarios) * len(expected_policies), "Policy outcome missing or substituted")
    require(job["completedRuns"] == job["totalRuns"] == len(result["runs"]), "Job progress differs from actual result rows")
    seed_set = set(job["request"]["parameters"]["seeds"])
    require({scenario["seed"] for scenario in scenarios.values()} == seed_set, "Executed seed set differs from protocol")
    rows, decisions, rollouts, initial_pairings = [], 0, 0, {}
    for run in result["runs"]:
        scenario = scenarios[run["scenarioId"]]
        key = (scenario["profile"], run["seed"])
        require(run["seed"] == scenario["seed"] and run["inputFingerprint"] == scenario["inputFingerprint"], "Policy changed its paired scenario")
        require(scenario["provenance"] == PROVENANCE and scenario["configuration"]["commands"] == [], "Policy-visible configuration contains hidden replay commands")
        initial = run["finalSummary"]["initialFingerprint"]
        require(len(initial) == 64, "Initial physical fingerprint missing")
        if key in pairing:
            require(pairing[key] == (scenario["inputFingerprint"], initial), "Physical initial conditions differ across policies/modes")
        pairing[key] = (scenario["inputFingerprint"], initial)
        initial_pairings.setdefault(scenario["id"], set()).add(initial)
        summary, metrics = run["finalSummary"], run["metrics"]
        require(run["provenance"] == metrics["provenance"] == PROVENANCE, "Final policy outcomes lack realized simulation provenance")
        require(summary["comparisonMode"] == mode, "Policy comparison mode differs from submitted condition")
        audit = summary["constraintAudit"]
        audit_keys = {(item["code"], tuple(sorted(item["resourceIds"]))) for item in audit}
        require(len(audit_keys) == len(audit) == metrics["constraintViolations"], "Constraint aggregation is not unique measured violations")
        require(not audit and metrics["constraintViolations"] == 0, "Declared benchmark physically violated modeled invariants")
        require(summary["constraintAuditCadenceSec"] == 10 and summary["constraintRejections"] >= 0, "Audit cadence/rejection separation missing")
        deliveries = {d["id"]: d for d in scenario["configuration"]["operations"]["deliveries"]}
        actual = summary["deliveredAtSec"]
        require(actual.keys() == deliveries.keys(), "Actual delivery IDs differ from configured records")
        completed = sum(at >= 0 for at in actual.values())
        failures = sum(at < 0 or at > deliveries[id]["deadlineSec"] + 1e-7 for id, at in actual.items())
        lateness = sum(max(0, (at if at >= 0 else metrics["finalClockSec"]) - deliveries[id]["deadlineSec"]) for id, at in actual.items())
        require(metrics["deliveryCount"] == len(deliveries) and metrics["completedDeliveries"] == completed, "Actual delivery counts differ")
        require(metrics["unfinishedDeliveries"] == len(deliveries) - completed and metrics["slaViolations"] == failures, "Censoring/SLA aggregation differs")
        require(0 <= metrics["finalClockSec"] <= scenario["horizonSec"] + 1e-7, "Actual policy clock escaped the declared horizon")
        if metrics["unfinishedDeliveries"]:
            close(metrics["finalClockSec"], scenario["horizonSec"], "Censored actual policy horizon")
        close(metrics["slaViolationRate"], failures / len(deliveries), "SLA rate")
        close(metrics["totalDeliveryLatenessSec"], lateness, "actual lateness")
        require(metrics["recoveryCensored"] == (completed < len(deliveries)), "Recovery censoring differs from unfinished records")
        first_incident = min((command["clockSec"] for command in scenario["exogenousSchedule"] if command["kind"] == "INCIDENT_ADD"), default=0)
        recovery_end = scenario["horizonSec"] if metrics["recoveryCensored"] else metrics["finalClockSec"]
        close(metrics["recoveryTimeSec"], max(0, recovery_end - first_incident), "actual recovery")
        require(metrics["positiveAdditionalDistanceM"] >= max(0, metrics["signedAdditionalDistanceM"]) - 1e-6, "Positive additional distance is below signed aggregate")
        require(0 <= metrics["positiveAdditionalDistanceM"] <= metrics["travelDistanceM"] + 1e-6, "Additional distance outside physical movement bounds")
        incident_commands = [command for command in scenario["exogenousSchedule"] if command["kind"] == "INCIDENT_ADD"]
        announced = {f"I{index + 1:03d}": command["clockSec"] for index, command in enumerate(incident_commands)}
        selected_types = []
        warehouses = {w["id"]: w for w in scenario["configuration"]["operations"]["warehouses"]}
        docks = {d["id"]: d for d in scenario["configuration"]["operations"]["docks"]}
        trucks = {truck["id"]: truck for truck in scenario["configuration"]["trucks"]}
        assignments = {a["truckId"]: a for a in scenario["configuration"]["operations"]["assignments"]}
        active_dock_ids = {id: a["dockId"] for id, a in assignments.items()}
        for decision in run["decisions"]:
            decisions += 1
            known = {id for id, at in announced.items() if at <= decision["clockSec"] + 1e-7}
            trace_ids = set(decision["observedIncidentIds"]) | set(INCIDENT_PATTERN.findall(decision["trigger"]))
            require(trace_ids <= known, f"Future incident ID leaked into trace {run['policyId']} @ {decision['clockSec']}: {trace_ids - known}")
            alternatives = decision["alternatives"]
            selected = [alt for alt in alternatives if alt["action"]["id"] == decision["selectedActionId"]]
            require(len(selected) == 1 and selected[0]["feasible"], "Chosen action has no unique feasible comparison")
            require(not any(item["hard"] for item in selected[0]["violations"]), "Chosen action had a hard constraint violation")
            selected_types.append(selected[0]["action"]["type"])
            action = selected[0]["action"]
            require(action["truckId"] == decision["truckId"] and action["truckId"] in trucks, "Selected truck reference is inconsistent")
            truck = trucks[action["truckId"]]
            require(0 <= truck["loadKg"] <= truck["capacityKg"], "Selected vehicle input violates cargo capacity")
            if action["type"] in {"LOCAL_REROUTE", "GLOBAL_REROUTE"}:
                route = action["routeEdgeIds"]
                require(route and all(id in EDGES for id in route), "Selected reroute contains an inaccessible/unknown edge")
                for before, after in zip(route, route[1:]):
                    left, right = EDGES[before], EDGES[after]
                    require(left["to"] == right["from"], "Selected actual reroute is disconnected")
                    for restriction in RESTRICTIONS:
                        if restriction["viaNode"] != left["to"] or restriction["fromWay"] != left["wayId"]:
                            continue
                        require(not (restriction["type"].startswith("only_") and restriction["toWay"] != right["wayId"]), "Selected reroute violates an only-turn restriction")
                        require(not (restriction["type"].startswith("no_") and restriction["toWay"] == right["wayId"]), "Selected reroute violates a no-turn restriction")
            elif action["type"] == "ADJUST_DOCK_RESERVATION":
                target = docks[action["dockId"]]
                previous = docks[active_dock_ids[action["truckId"]]]
                require(target["warehouseId"] == previous["warehouseId"] and target["warehouseId"] in warehouses, "Selected dock change moved to an unsupported warehouse")
                require(action["reservationStartSec"] >= max(decision["clockSec"], target["openFromSec"]) - 1e-7, "Selected reservation precedes observation/opening")
                require(action["reservationEndSec"] <= target["openUntilSec"] + 1e-7 and action["reservationEndSec"] - action["reservationStartSec"] >= target["serviceSec"] - 1e-7, "Selected dock interval does not fit service/opening")
                active_dock_ids[action["truckId"]] = target["id"]
            available = {driver["id"]: driver["available"] for driver in scenario["configuration"]["operations"]["drivers"]}
            for command in scenario["exogenousSchedule"]:
                if command["kind"] == "DRIVER_AVAILABILITY" and command["clockSec"] <= decision["clockSec"] + 1e-7:
                    available[command["payload"]["id"]] = command["payload"]["available"]
            known_available_deliveries = sum(len(a["deliveryIds"]) for a in scenario["configuration"]["operations"]["assignments"] if available[a["driverId"]])
            for alt in alternatives:
                projected = alt["metrics"]
                require(math.isfinite(alt["score"]), "Nonfinite decision score")
                if projected is None:
                    require(not run["policyId"] in {"B4", "B4_NO_TEMPORAL", "B4_NO_ADAPTIVE"}, "Executed counterfactual policy substituted a heuristic score")
                    continue
                rollouts += 1
                require(projected["provenance"] == "MODEL_ROLLOUT_FORECAST", "Hypothetical alternative presented as an actual policy outcome")
                require(projected["completedDeliveries"] <= known_available_deliveries, "Unknown future driver restoration leaked into projected completion")
                require(projected["completedDeliveries"] + projected["unfinishedDeliveries"] == projected["deliveryCount"], "Projected censoring counts differ")
                require(projected["slaViolations"] >= projected["unfinishedDeliveries"], "Unfinished projected deliveries were presented as timely")
            forecast = [alt for alt in alternatives if alt["feasible"] and alt["metrics"] is not None]
            if forecast:
                def dimensions(m):
                    return (m["slaViolationRate"], m["totalDeliveryLatenessSec"], m["downstreamAffectedResources"], m["modeledOperationalCost"], m["positiveAdditionalDistanceM"], m["recoveryTimeSec"])
                bounds = [(min(dimensions(a["metrics"])[k] for a in forecast), max(dimensions(a["metrics"])[k] for a in forecast)) for k in range(6)]
                for alt in forecast:
                    values = dimensions(alt["metrics"])
                    score = 2 * alt["metrics"]["unfinishedDeliveries"] + sum(w * (value - lower) / (upper - lower) for value, w, (lower, upper) in zip(values, WEIGHTS, bounds) if upper - lower > 1e-9)
                    close(alt["score"], score, "candidate-only normalized objective")
                require(selected[0]["score"] <= min(a["score"] for a in forecast) + 1e-8, "Counterfactual policy did not choose the measured minimum objective")
        reroutes = sum(kind in {"GLOBAL_REROUTE", "LOCAL_REROUTE"} for kind in selected_types)
        dock_changes = selected_types.count("ADJUST_DOCK_RESERVATION")
        require(metrics["totalReroutes"] == reroutes, "Actual reroute metric differs from executed decisions")
        require(metrics["modeledOperationalCost"] >= metrics["travelDistanceM"] / 1000 + .5 * reroutes + .25 * dock_changes - 1e-6, "Modeled cost undercounts declared nonnegative action/distance components")
        rows.append({"scenarioId": scenario["id"], "profile": scenario["profile"], "seed": run["seed"], "comparisonMode": mode, "policyId": run["policyId"], "inputFingerprint": run["inputFingerprint"], **metrics})
    for scenario in scenarios.values():
        actual_policies = [run["policyId"] for run in result["runs"] if run["scenarioId"] == scenario["id"]]
        require(set(actual_policies) == expected_policies and len(actual_policies) == len(expected_policies), "Repeated/missing policy condition")
        require(len(initial_pairings[scenario["id"]]) == 1, "Initial physical state differs by policy")
    report["jobs"].append({"id": job["id"], "comparisonMode": mode, "scenarios": len(scenarios), "policyRows": len(rows), "decisionTraces": decisions, "executedHypotheticalAlternatives": rollouts, "constraintViolations": 0})
    return rows


def audit(output):
    protocol_path = ROOT / "config/benchmark_protocol.json"
    protocol = json_file(protocol_path)
    journal = json_file(output / "benchmark_execution_journal.json")
    require(journal["protocolSha256"] == hashlib.sha256(protocol_path.read_bytes()).hexdigest(), "Declared protocol changed while executing")
    final_available = bool(journal.get("completedAtUtc")) and (output / "BENCHMARK_RESULTS.json").exists() and (output / "BENCHMARK_RESULTS.csv").exists()
    report = {"schemaVersion": "cascadeshield.independent-result-validation/1.0", "validatedAtUtc": datetime.now(timezone.utc).isoformat(), "provenance": "INDEPENDENT_SIMULATION_EVIDENCE_VALIDATION", "jobs": [], "issues": [], "finalResultsAvailable": final_available}
    pairing, rows = {}, []
    selected_ids = {entry["id"] for entry in journal["jobs"].values()}
    declared_requests = {}
    for case in protocol["cases"]:
        for mode in protocol["comparisons"]:
            declared_requests[case["profile"] + ":" + mode] = {
                "parameters": {**protocol["commonParameters"], **case["parameters"], "profile": case["profile"], "seeds": protocol["seeds"]},
                "policies": protocol["policyIds"], "comparisonMode": mode,
                "ablations": protocol["fullComparisonAblations"] if mode == "FULL" else ["FULL"]}
    report["failedAttempts"] = []
    archived_attempts = []
    for key, entry in journal["jobs"].items():
        require(key in declared_requests and entry["request"] == declared_requests[key], "Acquisition journal differs from the predeclared protocol inputs")
        for attempt in entry.get("failedAttempts", []):
            report["failedAttempts"].append(validate_failed_attempt(attempt, entry, selected_ids))
            archived_attempts.append(attempt)
        path = output / "benchmark_raw" / (entry["id"] + ".json")
        if path.exists():
            rows.extend(validate_job(json_file(path), entry, pairing, report))
    report["validatedPolicyRows"] = len(rows)
    report["pairedUniqueScenarios"] = len(pairing)
    adverse = []
    index = {(r["profile"], r["seed"], r["comparisonMode"], r["policyId"]): r for r in rows}
    for row in rows:
        if row["policyId"] != "B4":
            continue
        for reference in ("B0", "B1", "B2", "B3"):
            base = index.get((row["profile"], row["seed"], row["comparisonMode"], reference))
            if base is None:
                continue
            differences = {name: row[name] - base[name] for name in ("slaViolationRate", "totalDeliveryLatenessSec", "modeledOperationalCost", "downstreamAffectedResources")}
            if any(delta > 1e-7 for delta in differences.values()):
                adverse.append({"profile": row["profile"], "seed": row["seed"], "comparisonMode": row["comparisonMode"], "reference": reference, "enhancedMinusReference": differences})
    report["adverseTradeoffCases"] = adverse
    report["adverseDifferenceCounts"] = {metric: sum(case["enhancedMinusReference"][metric] > 1e-7 for case in adverse)
                                          for metric in ("slaViolationRate", "totalDeliveryLatenessSec", "modeledOperationalCost", "downstreamAffectedResources")}
    report["interpretation"] = "Positive enhanced-minus-reference is an adverse difference for these lower-is-better measures. Cost/SLA tradeoffs are not hidden, and these are simulated outcomes. Direct exposure classifications are policy-dependent; downstream resource counts are a non-direct footprint rather than a causal field effect."
    report["auditLimits"] = "Compact exported traces omit the exact pre-action occupied-edge position and complete driver ownership history. Internal route turns and resource references are independently inspected here; first-edge continuity and microtick road-entry gates rely on executed unit tests and the stored physical state audits."
    if report["finalResultsAvailable"]:
        final = json_file(output / "BENCHMARK_RESULTS.json")
        expected_scenarios = len(protocol["cases"]) * len(protocol["seeds"])
        expected_rows = expected_scenarios * (len(protocol["policyIds"]) * len(protocol["comparisons"]) + len(protocol["fullComparisonAblations"]) - 1)
        require(expected_scenarios == 20 and expected_rows == 260, "Final declared condition count differs from reviewed protocol")
        require(len(rows) == final["rowCount"] == len(final["rows"]) == expected_rows, "Final policy row count differs from raw actual exports")
        require(len(pairing) == final["scenarioCount"] == expected_scenarios, "Unique scenario count differs")
        require(len(report["jobs"]) == len(protocol["cases"]) * len(protocol["comparisons"]), "A declared case/mode job is unavailable")
        require(final.get("failedAttempts", []) == archived_attempts, "Final results silently omitted/changed failed-attempt archives")
        require(not ({attempt["id"] for attempt in archived_attempts} & {row["jobId"] for row in final["rows"]}), "Failed-attempt progress was counted as a complete final policy outcome")
        raw_metrics = {(r["profile"], r["seed"], r["comparisonMode"], r["policyId"]): r for r in rows}
        for row in final["rows"]:
            key = (row["profile"], row["seed"], row["comparisonMode"], row["policyId"])
            require(key in raw_metrics and all(row[field] == value for field, value in raw_metrics[key].items()), "Combined result altered a raw policy outcome")
            expected_partition = "reserved_assessment" if row["seed"] in protocol["futureMlPartition"]["reservedAssessmentSeeds"] else "development"
            require(row["futureMlPartition"] == expected_partition, "Future split mixed related seed conditions")
        with (output / "BENCHMARK_RESULTS.csv").open(encoding="utf-8-sig", newline="") as stream:
            csv_rows = list(csv.DictReader(stream))
        require(len(csv_rows) == expected_rows, "CSV contains missing/substituted rows")
        for row in csv_rows:
            key = (row["profile"], int(row["seed"]), row["comparisonMode"], row["policyId"])
            raw = raw_metrics[key]
            require(row["inputFingerprint"] == raw["inputFingerprint"] and row["provenance"] == PROVENANCE, "CSV pairing/provenance changed")
            for metric in ("slaViolationRate", "totalDeliveryLatenessSec", "modeledOperationalCost", "constraintViolations"):
                close(float(row[metric]), raw[metric], "CSV " + metric)
        for job in final["jobs"]:
            require(hashlib.sha256((ROOT / job["rawJson"]).read_bytes()).hexdigest() == job["rawSha256"], "Raw export checksum changed")
        require(final["provenance"] == PROVENANCE and final["liveStatePreserved"] and not final["trainedModel"] and not final["autonomousLlm"], "Final provenance/stop boundary missing")
        report["statisticsValidation"] = validate_statistics(final)
        report.update(passed=True, finalPolicyRows=expected_rows, uniqueScenarios=expected_scenarios, comparisonModes=protocol["comparisons"], seedCount=len(protocol["seeds"]), rawAndCombinedMetricsAgree=True, csvJsonRowsAgree=True, allMeasuredConstraintViolations=0)
    else:
        report["passed"] = None
        report["stage"] = "IN_PROGRESS"
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "reports")
    parser.add_argument("--report", type=Path, default=ROOT / "reports/milestone3_result_validation.json")
    parser.add_argument("--watch", action="store_true")
    args = parser.parse_args()
    prior = None
    while True:
        try:
            report = audit(args.output)
        except Exception as error:
            report = {"passed": False, "validatedAtUtc": datetime.now(timezone.utc).isoformat(), "issues": [str(error)]}
            args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
            raise
        args.report.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        progress = (len(report["jobs"]), report["validatedPolicyRows"], report["finalResultsAvailable"])
        if progress != prior:
            print(f"VALIDATED jobs={progress[0]} policyRows={progress[1]} final={progress[2]} adverseTradeoffs={len(report['adverseTradeoffCases'])}", flush=True)
            prior = progress
        if report.get("passed") is True or not args.watch:
            return
        time.sleep(10)


if __name__ == "__main__":
    main()
