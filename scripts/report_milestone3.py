"""Render Milestone 3 evidence from completed actual results; refuse incomplete evidence."""
from __future__ import annotations
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import statistics

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"


def read(name):
    return json.loads((REPORTS / name).read_text(encoding="utf-8"))


def number(value, digits=2):
    return f"{value:,.{digits}f}"


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def main():
    result = read("BENCHMARK_RESULTS.json")
    validation = read("milestone3_result_validation.json")
    java, frontend, python = [read(f"milestone3_{name}_tests.json") for name in ("java", "frontend", "python")]
    integration, browser, restart = [read(f"milestone3_{name}_tests.json") for name in ("integration", "browser", "restart")]
    artifacts_audit = read("milestone3_artifact_validation/validation_run.json")
    require(artifacts_audit["validation_passed"] and not artifacts_audit["errors"], "Original and processed dataset integrity must pass")
    require(validation["passed"] is True and result["rowCount"] == 260 and result["scenarioCount"] == 20, "Full declared results and independent validation are required")
    require(java["success"] and java["totals"]["failures"] == java["totals"]["errors"] == java["totals"]["skipped"] == 0, "Complete passing Java checks are required")
    require(frontend["success"] and python["success"], "Frontend and Python checks must pass")
    require(frontend.get("production_build", {}).get("passed") is True, "Executed frontend production build evidence is required")
    for value in (integration, browser, restart):
        require(value["passed"] and all(check["passed"] for check in value["checks"]), "Integration, browser and restart evidence must pass")
    rows = result["rows"]
    require(not any(row["constraintViolations"] for row in rows), "Investigate actual hard constraint failures before completing the milestone")
    stats = result["statistics"]
    by_policy = {(group["comparison_mode"], group["policy"]): group for group in stats["descriptive"]}
    pairs = {(group["comparison_mode"], group["reference"], group["metric"]): group for group in stats["paired_comparisons"]}
    counts = {"java": java["totals"]["tests"], "frontend": frontend["numPassedTests"], "python": python["tests"],
              "isolated_api": len(integration["checks"]), "benchmark_browser": len(browser["checks"]), "restart": len(restart["checks"])}
    total_checks = sum(counts.values())
    lines = ["# Milestone 3: executed counterfactual cascade benchmarks", "",
        "Completed on 2026-10-14. **REAL GEOGRAPHIC DATA + SIMULATED RESEARCH EXPERIMENTS**. The isolated rollout engine, B0-B4 policies, controlled action comparison, ablations, persistent Benchmark Lab and reproducible exports are implemented. No GNN or autonomous LLM was trained or run.", "",
        f"The declared batch executed **{len(rows)} policy runs across 20 paired scenarios**, four profiles and five seeds (11, 22, 33, 44, 55). Eight persistent jobs completed: 160 full-comparison outcomes and 100 equal-action outcomes. Every policy and mode retained identical initial configuration and exogenous schedule fingerprints. Raw cases, adverse outcomes, ties and decision traces are preserved.", "",
        "## Measured outcomes", "",
        "Values below are scenario-weighted means over 20 cases per method. SLA mean differs from the separate delivery-weighted pooled rate in JSON. Lateness is total per scenario; cost uses declared illustrative units. Outcome completion and censor counts are reported below.", "",
        "| Mode | Policy | SLA violations (%) | Lateness (s) | Downstream footprint | Cost (units) | Reroutes | Positive extra distance (m) | Recovery (s) | Decision time (ms/run) |", "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    full_b3 = by_policy[("FULL", "B3")]["metrics"]
    full_b4 = by_policy[("FULL", "B4")]["metrics"]
    equal_b3 = by_policy[("EQUAL_ACTIONS", "B3")]["metrics"]
    equal_b4 = by_policy[("EQUAL_ACTIONS", "B4")]["metrics"]
    no_cf = by_policy[("FULL", "B4_NO_COUNTERFACTUAL")]["metrics"]
    interpretation = (f"**The executed matrix does not establish an incremental SLA/lateness benefit from counterfactual evaluation.** Full B4 mean SLA failures were {number(full_b4['slaViolationRate']['mean'] * 100)}% versus B3's {number(full_b3['slaViolationRate']['mean'] * 100)}%, with higher modeled cost and decision time. "
        f"With equal actions, B3/B4 both had {number(equal_b3['slaViolationRate']['mean'] * 100)}% mean SLA failures and {number(equal_b3['totalDeliveryLatenessSec']['mean'])} seconds mean lateness; B4 cost {number(equal_b4['modeledOperationalCost']['mean'] - equal_b3['modeledOperationalCost']['mean'])} more units. "
        f"The no-counterfactual variant's mean SLA/lateness/cost ({number(no_cf['slaViolationRate']['mean'] * 100)}%, {number(no_cf['totalDeliveryLatenessSec']['mean'])} seconds, {number(no_cf['modeledOperationalCost']['mean'])} units) were lower than full B4's. The full SLA improvement includes the wider action pipeline, including dock changes and indirect graph eligibility. It cannot be attributed specifically to executed counterfactual evaluation.")
    lines[6:6] = [interpretation, ""]
    for mode in ("FULL", "EQUAL_ACTIONS"):
        for policy in ("B0", "B1", "B2", "B3", "B4"):
            metrics = by_policy[(mode, policy)]["metrics"]
            keys = ("totalDeliveryLatenessSec", "downstreamAffectedResources", "modeledOperationalCost", "totalReroutes", "positiveAdditionalDistanceM", "recoveryTimeSec", "decisionComputationMs")
            lines.append("| " + " | ".join([mode, policy, number(metrics["slaViolationRate"]["mean"] * 100)] + [number(metrics[key]["mean"]) for key in keys]) + " |")
    unfinished = sum(row["unfinishedDeliveries"] for row in rows)
    censored = sum(row["recoveryCensored"] for row in rows)
    lines += ["", f"Across all 260 rows: **{unfinished} unfinished deliveries, {censored} censored recovery outcomes and 0 measured hard constraint violations**. Rejected proposals are reported separately; they are not counted as executed physical failures.", "",
        "## Paired differences and uncertainty", "",
        "Enhanced-minus-reference deltas use identical profile/seed cases; negative means lower. SLA deltas and intervals below are percentage points. Sample variation is available for every metric in JSON. Intervals use 2000 deterministic seed-cluster bootstrap replicates, keeping four profiles together per seed. There are only five independent seed clusters and no multiplicity correction: these are descriptive intervals for this simulated matrix.", "",
        "| Mode | Reference | SLA delta (pp), 95% interval | Lateness delta (s), 95% interval | Cost delta (units), 95% interval |", "| --- | --- | ---: | ---: | ---: |"]
    def difference(mode, reference, metric, scale=1):
        item = pairs[(mode, reference, metric)]
        low, high = item["seed_cluster_bootstrap_95_interval"]
        return f"{number(item['mean_delta_enhanced_minus_reference'] * scale)} [{number(low * scale)}, {number(high * scale)}]"
    for mode in ("FULL", "EQUAL_ACTIONS"):
        for reference in ("B0", "B1", "B2", "B3"):
            lines.append(f"| {mode} | {reference} | {difference(mode, reference, 'slaViolationRate', 100)} | {difference(mode, reference, 'totalDeliveryLatenessSec')} | {difference(mode, reference, 'modeledOperationalCost')} |")
    lines += ["", "Sample variation for the main graph/rule and enhanced comparison:", "",
        "| Mode | Policy | SLA mean +/- sample SD (%) | Lateness mean +/- sample SD (s) | Cost mean +/- sample SD |",
        "| --- | --- | ---: | ---: | ---: |"]
    for mode in ("FULL", "EQUAL_ACTIONS"):
        for policy in ("B3", "B4"):
            metrics = by_policy[(mode, policy)]["metrics"]
            values = [f"{number(metrics[key]['mean'] * scale)} +/- {number(metrics[key]['sample_sd'] * scale)}" for key, scale in (("slaViolationRate", 100), ("totalDeliveryLatenessSec", 1), ("modeledOperationalCost", 1))]
            lines.append("| " + " | ".join([mode, policy] + values) + " |")
    lines += ["", "## Profile outcomes and adverse cases", "",
        "The full-comparison B3/B4 profile means expose case dependence; they are not observed freight results.", "",
        "| Profile | B3 SLA (%) | B4 SLA (%) | B3 lateness (s) | B4 lateness (s) | B3 cost | B4 cost |", "| --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for case in result["protocol"]["cases"]:
        profile = case["profile"]
        groups = {policy: [row for row in rows if row["profile"] == profile and row["policyId"] == policy and row["comparisonMode"] == "FULL"] for policy in ("B3", "B4")}
        values = [statistics.fmean(row[key] for row in groups[policy]) * (100 if key == "slaViolationRate" else 1) for key in ("slaViolationRate", "totalDeliveryLatenessSec", "modeledOperationalCost") for policy in ("B3", "B4")]
        lines.append("| " + " | ".join([profile] + [number(v) for v in values]) + " |")
    adverse = validation["adverseTradeoffCases"]
    lines += ["", f"The independent validator retained **{len(adverse)} B4/reference case comparisons with at least one adverse SLA/lateness/cost/footprint difference** (a case may occur against multiple references). Detailed deltas are in [result validation](milestone3_result_validation.json). This milestone does not establish uniform superiority.", "",
        "## Ablations", "", "All ablations retain the full-comparison physical constraints and action set. Planning exposure/threshold or executed evaluation alone changes, as documented in the protocol.", "",
        "| Variant | SLA mean +/- sample SD (%) | Lateness mean +/- sample SD (s) | Cost mean +/- sample SD | Cases with different physical metrics from B4 |", "| --- | ---: | ---: | ---: | ---: |"]
    physical = ("slaViolationRate", "totalDeliveryLatenessSec", "downstreamAffectedResources", "totalReroutes", "travelDistanceM", "modeledOperationalCost", "recoveryTimeSec", "constraintViolations")
    indexed = {(row["profile"], row["seed"], row["policyId"]): row for row in rows if row["comparisonMode"] == "FULL"}
    for policy in ("B4", "B4_NO_TEMPORAL", "B4_NO_ADAPTIVE", "B4_NO_COUNTERFACTUAL"):
        group = by_policy[("FULL", policy)]["metrics"]
        fields = []
        for metric, scale in (("slaViolationRate", 100), ("totalDeliveryLatenessSec", 1), ("modeledOperationalCost", 1)):
            fields.append(f"{number(group[metric]['mean'] * scale)} +/- {number(group[metric]['sample_sd'] * scale)}")
        selected = [row for row in rows if row["comparisonMode"] == "FULL" and row["policyId"] == policy]
        different = sum(any(abs(row[key] - indexed[(row["profile"], row["seed"], "B4")][key]) > 1e-7 for key in physical) for row in selected)
        lines.append("| " + " | ".join([policy] + fields + [str(different)]) + " |")
    lines += ["", "These executed differences justify only the corresponding case-specific simulated outcomes. A variant with no changed physical outcomes provides no measured benefit for that component in this matrix, even though functional tests establish that its implementation changes planning behavior. Full-versus-controlled differences also include the dock action repertoire; they cannot all be credited to counterfactual intelligence."]
    budget = Counter(row["policyId"] + " / " + row["comparisonMode"] for row in rows if row["decisionLimitReached"])
    trial_count = sum(job["executedHypotheticalAlternatives"] for job in validation["jobs"])
    decisions, action_counts = 0, defaultdict(Counter)
    for job in result["jobs"]:
        raw = json.loads((ROOT / job["rawJson"]).read_text(encoding="utf-8"))
        for run in raw["result"]["runs"]:
            for trace in run["decisions"]:
                decisions += 1
                chosen = next(alt for alt in trace["alternatives"] if alt["action"]["id"] == trace["selectedActionId"])
                action_counts[run["policyId"]][chosen["action"]["type"]] += 1
    failed = result.get("failedAttempts", [])
    lines += ["", f"The batch recorded {decisions} decisions and {trial_count} executed hypothetical alternatives, whose forecast metrics remain separate from the 260 realized policy outcomes. The six-decision limit was reached in {sum(budget.values())} policy runs; selecting NONE/CONTINUE consumes a decision slot too. Per-policy/mode frequencies and actual selected action counts are recorded in the machine-readable milestone report. The finite budget remains unchanged from the declared protocol.", "",
        "## Interrupted execution and recovery", "",
        f"{len(failed)} interrupted attempt(s) are retained separately in the execution journal and failed raw archives. The service shutdown interrupted rain-multiple FULL at recorded progress 30/40; its partial outcome JSON did not survive, so that progress counter is not treated as 30 available measured rows. The runner archived the actual error and retried the full request with identical declared inputs. Completed jobs were reused. The final 260-row corpus contains only complete successful jobs, with no reconstructed or substituted outcomes. Decision timing spans the original and restored JVM sessions and should not be treated as a controlled hardware performance study.", "",
        "## Implementation and constraints", "",
        "Each alternative deep-copies identical observed state and executes the existing 0.1-second authoritative simulator. No future incident or unannounced driver restoration enters the planning copy. Supported actions are no intervention, continue, wait, local/global rerouting and feasible same-warehouse dock/reservation changes. Capacity, ownership, connected turn-aware roads, driver windows and dock calendars are validated. Delivery deadlines are soft SLA penalties. Physical audits inspect actual state every 10 seconds and after interventions; original per-tick entry guards remain active.", "",
        "Full B3 delegates to the existing graph/rule fallback; controlled B3 extends its copied heuristic to the common actions. B4 scores executed current-knowledge alternatives with fixed normalized SLA/lateness/downstream/cost/distance/recovery weights and an explicit unfinished-delivery penalty. Driver/vehicle transfers and priority changes are absent because their physical execution is not modeled. OR-Tools is omitted: bounded candidate enumeration and existing routing provide the implemented search, without a modeled fleet-wide assignment problem or global optimality claim.", "",
        "The Benchmark Lab provides scenario/seed/policy controls, full/equal-action modes, ablations, asynchronous progress, actual outcome tables, before/after dependency graphs, decision traces and CSV/JSON download. Flyway V3 persists isolated benchmark jobs. Live approval and scenario modules are reused without rewriting them.", "",
        "## Executed engineering checks", "", "| Check | Passed |", "| --- | ---: |"]
    labels = {"java": "Java (85 preserved + 39 new; real Chennai included)", "frontend": "Frontend (36 preserved + 14 new)", "python": "Python acquisition/geography/conversion/statistics", "isolated_api": "Isolated API + PostgreSQL (includes 15 malformed-input cases)", "benchmark_browser": "Actual browser workflow + exports", "restart": "Actual backend-container restart + persistence"}
    for key, count in counts.items(): lines.append(f"| {labels[key]} | {count} |")
    lines += ["", f"**{total_checks} current checks passed**, plus the frontend production build and independent raw/combined 260-row validation. Java had zero failures/errors/skips. Browser had no console/page errors or live mutation requests. Old destructive API/browser harnesses were not rerun against the operator checkpoint; their Milestone 2 evidence remains historical, while all existing unit tests were rerun.", "",
        "Evidence: [Java](milestone3_java_tests.json), [frontend/build](milestone3_frontend_tests.json), [Python](milestone3_python_tests.json), [API/database](milestone3_integration_tests.json), [browser](milestone3_browser_tests.json), [restart](milestone3_restart_tests.json), [raw outcome validation](milestone3_result_validation.json), [actual lab screenshot](screenshots/milestone-3-benchmark-lab.png), [decision trace screenshot](screenshots/milestone-3-benchmark-trace.png). Engineering validation jobs are excluded from the declared benchmark corpus. Their deliberately short 300-second rollout produced adverse B4 lateness, demonstrating censoring/horizon limitations rather than being suppressed.", "",
        "## Preserved state, data and provenance", "",
        f"The existing completed three-truck live run stayed at **{number(restart['live_clock_sec'], 1)} simulated seconds**. The batch and real container restart preserved its exact API state, PostgreSQL checkpoint, assignments, commands, scenarios and audit events. Frontend: http://127.0.0.1:5173; API health: http://127.0.0.1:8080/api/health.", "",
        "All 18 eligible historical research tables and **2,414,128 rows** remain unchanged, with recorded checksums/provenance intact. A fresh [artifact audit](milestone3_artifact_validation/validation_run.json) checked all 12 original raw files and all 18 processed files, including every CSV row/header, with zero errors (54 validation records). Source artifacts, processed cohorts, previous reports and licensing quarantine are preserved. GB, England/Wales, Brazil and Birmingham are not joined to simulated Chennai operations. No new observed freight data is claimed.", "",
        "Real topology is the existing central Chennai OSM extract dated 2026-10-09T05:33:21Z, SHA-256 `38ab5bdea18ca7859daea5a3801f1a5d138d320e29a841aa8d67f00c1c87e80d`. Graph SHA-256 is `c943bac278192042b22342d8e1be898cc68512fb936e314633645bc3e0304e60`: 12,386 nodes, 23,907 directed edges, 14,147 physical map segments and 10 supported turn restrictions. ODbL 1.0/OpenStreetMap attribution and missing-speed assumptions remain in [CHENNAI_NETWORK.md](CHENNAI_NETWORK.md).", "",
        "## Reproduce and stop boundary", "", "```powershell", "powershell -ExecutionPolicy Bypass -File scripts/start_simulator.ps1 -UseMavenRelay", r".venv\Scripts\python.exe scripts/run_benchmarks.py", r".venv\Scripts\python.exe scripts/validate_benchmark_results.py", r".venv\Scripts\python.exe scripts/report_milestone3.py", "```", "",
        "The journal resumes existing jobs and refuses a changed protocol in the same output directory. Use a new output directory for a separately declared fresh execution. Do not restart while jobs are active: interrupted jobs are marked failed. Raw exports/checksums are retained in [BENCHMARK_RESULTS.json](BENCHMARK_RESULTS.json), [CSV](BENCHMARK_RESULTS.csv), `benchmark_raw/` and [execution journal](benchmark_execution_journal.json). Details: [engine](../docs/COUNTERFACTUAL_ENGINE.md), [protocol/API](../docs/BENCHMARK_PROTOCOL.md), [launch instructions](../simulator/README.md).", "",
        "Limitations: bounded geography and repeated prepared OD pairs; parameterized workloads/weather, uncalibrated rule risk and abstract costs; finite six-decision sequential search rather than a fleet optimum; known active-incident duration but hidden future announcements/restoration; horizon-dependent copied outcomes; five seed clusters and unadjusted descriptive intervals. Equal action availability still permits different graph/trigger eligibility, so the no-counterfactual ablation is the closer component contrast. Downstream direct/non-direct classification is policy-dependent and is not causal cascade attribution. Fixed policy order, JVM warm-up and host load affect decision timing, and computation is excluded from modeled operational cost.", "",
        "The future seed partition is prospective bookkeeping only. Both groups are published; no model was fit or evaluated, and tuning on these results would require a new held-out ML assessment. These experiments support only the measured model-specific differences above, not uniform superiority or real-world effectiveness. **Work stops after Milestone 3.**", ""]
    (REPORTS / "MILESTONE_3_RESULTS.md").write_text("\n".join(lines), encoding="utf-8")
    artifacts = ["BENCHMARK_RESULTS.json", "BENCHMARK_RESULTS.csv", "benchmark_execution_journal.json", "MILESTONE_3_RESULTS.md"] + [f"milestone3_{name}_tests.json" for name in ("java", "frontend", "python", "integration", "browser", "restart")] + ["milestone3_result_validation.json", "milestone3_artifact_validation/validation_run.json"]
    manifest = {name: {"bytes": (REPORTS / name).stat().st_size, "sha256": hashlib.sha256((REPORTS / name).read_bytes()).hexdigest()} for name in artifacts}
    sources = list((ROOT / "simulator/backend/src/main/java").rglob("*.java"))
    sources += list((ROOT / "simulator/backend/src/test/java").rglob("*.java"))
    sources += [ROOT / name for name in ("simulator/backend/src/main/resources/db/migration/V3__benchmark_jobs.sql", "simulator/backend/pom.xml", "simulator/backend/Dockerfile", "simulator/compose.yaml", "simulator/frontend/src/BenchmarkLab.tsx", "simulator/frontend/src/benchmark.ts", "simulator/frontend/src/benchmark.css", "simulator/frontend/src/App.tsx", "simulator/frontend/package-lock.json", "scripts/run_benchmarks.py", "scripts/benchmark_statistics.py", "scripts/validate_benchmark_results.py", "scripts/report_milestone3.py", "config/benchmark_protocol.json")]
    sources += [ROOT / name for name in ("scripts/test_benchmark_integration.py", "scripts/test_benchmark_browser.py", "scripts/test_benchmark_restart.py", "tests/test_benchmark_statistics.py", "simulator/frontend/src/benchmark.test.ts")]
    source_hashes = {path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(sources)}
    summary = {"schemaVersion": "cascadeshield.milestone-results/3.0", "status": "COMPLETE", "completedOnLocalDate": "2026-10-14", "recordedAtUtc": datetime.now(timezone.utc).isoformat(), "provenance": "SIMULATED_RESEARCH_EXPERIMENT", "tests": counts, "totalExecutedCurrentChecks": total_checks, "allFinalChecksPassed": True, "pairedScenarios":20,"seeds":5,"executedPolicyRows":260,"completedPersistentBatchJobs":8,"failedAttempts":failed,"constraintViolations":0,"unfinishedDeliveries":unfinished,"censoredRecoveryRows":censored,"decisionTraces":decisions,"executedHypotheticalAlternatives":trial_count,"decisionBudgetReachedByPolicyAndMode":dict(budget),"selectedActionsByPolicy":{key:dict(value) for key,value in action_counts.items()},"adverseTradeoffComparisons":len(adverse),"liveStatePreserved":True,"liveClockSec":restart["live_clock_sec"],"historicalTables":18,"historicalRows":2414128,"graphSha256":result["catalog"]["graphSha256"],"protocolSha256":result["protocolSha256"],"artifacts":manifest,"implementationSha256":source_hashes,"trainedGnn":False,"autonomousLlm":False,"stopBoundary":"Milestone 3 complete; no ML development."}
    (REPORTS / "MILESTONE_3_RESULTS.json").write_text(json.dumps(summary,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    print(f"Rendered completed evidence: {total_checks} checks, 260 actual policy rows")

if __name__ == "__main__": main()
