"""Read archived M3 traces without changing historical policies, outputs or simulation state."""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import statistics


def diagnose(raw_directory: Path) -> dict:
    groups = defaultdict(list)
    hashes = {}
    inversion_examples = []
    for path in sorted(raw_directory.glob("*.json")):
        if "failed" in path.stem:
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("status") != "COMPLETED":
            continue
        hashes[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
        mode = payload["request"]["comparisonMode"]
        profile = payload["request"]["parameters"]["profile"]
        for run in payload["result"]["runs"]:
            actions, censored = Counter(), Counter()
            inversions = duplicate_vectors = rollouts = 0
            for decision in run["decisions"]:
                feasible = [a for a in decision["alternatives"] if a["feasible"]]
                selected = next(a for a in feasible if a["action"]["id"] == decision["selectedActionId"])
                actions[selected["action"]["type"]] += 1
                measured = [a for a in feasible if a.get("metrics")]
                rollouts += len(measured)
                if any(a["metrics"]["unfinishedDeliveries"] for a in measured):
                    censored[f"{profile}@{decision['clockSec']}"] += 1
                if measured:
                    min_sla = min(a["metrics"]["slaViolations"] for a in measured)
                    min_late = min(a["metrics"]["totalDeliveryLatenessSec"] for a in measured if a["metrics"]["slaViolations"] == min_sla)
                    metrics = selected["metrics"]
                    if metrics["slaViolations"] > min_sla or (metrics["slaViolations"] == min_sla and metrics["totalDeliveryLatenessSec"] > min_late + 1e-7):
                        inversions += 1
                        inversion_examples.append({"mode": mode, "scenario": run["scenarioId"], "truck": decision["truckId"], "clock": decision["clockSec"]})
                    vectors = [json.dumps({k: v for k, v in a["metrics"].items() if k not in ("decisionComputationMs", "provenance")}, sort_keys=True) for a in measured]
                    duplicate_vectors += len(vectors) - len(set(vectors))
            groups[(mode, run["policyId"])].append({"decisions": len(run["decisions"]), "decisionLimitReached": run["finalSummary"]["decisionLimitReached"], "sla": run["metrics"]["slaViolationRate"], "decisionMs": run["metrics"]["decisionComputationMs"], "actions": actions, "censored": censored, "inversions": inversions, "duplicateVectors": duplicate_vectors, "rollouts": rollouts})
    summaries = []
    for (mode, policy), rows in sorted(groups.items()):
        actions, censored = Counter(), Counter()
        for row in rows:
            actions.update(row["actions"])
            censored.update(row["censored"])
        summaries.append({"mode": mode, "policy": policy, "cases": len(rows), "meanSlaViolationRate": statistics.mean(r["sla"] for r in rows), "meanDecisionMs": statistics.mean(r["decisionMs"] for r in rows), "decisionCount": sum(r["decisions"] for r in rows), "runsAtDecisionLimit": sum(r["decisionLimitReached"] for r in rows), "selectedActions": dict(actions), "censoredForecastDecisionLocations": dict(censored), "executedForecastAlternatives": sum(r["rollouts"] for r in rows), "duplicateForecastMetricVectors": sum(r["duplicateVectors"] for r in rows), "forecastSlaLatenessRankInversions": sum(r["inversions"] for r in rows)})
    return {"schemaVersion": "cascadeshield.m3-diagnostics/1.0", "historicalFilesSha256": hashes, "summaries": summaries, "forecastRankInversionExamples": inversion_examples, "interpretation": ["Full-vs-equal results confound dock-action access and indirect-resource eligibility with planning method.", "NONE/CONTINUE/WAIT consume the original six-decision budget; this is measured behavior, not proof that removing them improves outcomes.", "Censored alternatives in original B4 occur only with unavailable drivers before their unannounced restoration. Increasing the rollout duration does not make hidden restoration known.", "No within-forecast SLA/lateness ranking inversion was found in original B4 decisions; weight retuning is not supported as a demonstrated fix by this trace audit.", "Duplicate forecast metric vectors identify repeated hypothetical outcomes; no claim of identical full states or candidate incompleteness follows.", "The original B0-B4 implementations and outcomes remain unchanged. New B5 identifiers must isolate learned predictions from action, eligibility, budget and horizon effects."]}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-directory", type=Path, default=Path("reports/benchmark_raw"))
    parser.add_argument("--output", type=Path, default=Path("reports/milestone4_b4_diagnostics.json"))
    args = parser.parse_args()
    result = diagnose(args.raw_directory)
    content = json.dumps(result, indent=2) + "\n"
    if args.output.exists() and args.output.read_text(encoding="utf-8") != content:
        raise SystemExit("Refusing to overwrite changed diagnostic evidence")
    args.output.write_text(content, encoding="utf-8")
    print(f"Audited {len(result['historicalFilesSha256'])} archived jobs; {len(result['summaries'])} method/mode groups")


if __name__ == "__main__":
    main()
