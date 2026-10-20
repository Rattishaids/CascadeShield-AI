"""Verify isolated persistent M3 jobs through HTTP and PostgreSQL.

Only /benchmarks/runs receives POST requests, including invalid-input probes.
The live simulator, scenarios and historical freight cohorts are read-only.
These two bounded seeded comparisons are engineering checks, not the research
benchmark corpus or evidence of real-world effectiveness.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
import math
import os
from pathlib import Path
import time
import urllib.error
import urllib.request

from test_simulator_integration import Harness, HttpError, ROOT, require, first_difference

PROVENANCE = "SIMULATED_RESEARCH_EXPERIMENT"
TIMING_KEYS = {"decisionComputationMs", "computationMs", "computationNanos"}


def without_wallclock(value):
    if isinstance(value, dict):
        return {key: without_wallclock(item) for key, item in value.items() if key not in TIMING_KEYS}
    if isinstance(value, list):
        return [without_wallclock(item) for item in value]
    return value


class BenchmarkHarness(Harness):
    def __init__(self, base_url, dsn, graph_path, timeout_sec):
        super().__init__(base_url, dsn, graph_path)
        self.timeout_sec = timeout_sec
        self.mutation_paths = []
        self.report.update(data_classes=["REAL_GEOGRAPHIC_DATA", "SIMULATED_RESEARCH_EXPERIMENT", "ENGINEERING_TEST_EVIDENCE"], autonomous_llm_used=False)
        self.body = {"parameters": {"profile": "closure-contention", "seeds": [73], "truckCount": 2,
            "maxDecisions": 2, "rolloutHorizonSec": 300, "horizonSec": 2400},
            "policies": ["B0", "B4"], "comparisonMode": "EQUAL_ACTIONS", "ablations": ["FULL"]}

    def request(self, path, body=None, method=None, timeout=60):
        actual_method = method or ("POST" if body is not None else "GET")
        if actual_method not in {"GET", "HEAD"}:
            require(path == "/benchmarks/runs" and actual_method == "POST", "Harness attempted a live mutation: " + path)
            self.mutation_paths.append(path)
        return super().request(path, body, method, timeout)

    def rejected(self, status, path, body=None):
        try:
            self.request(path, body)
        except HttpError as error:
            require(error.status == status, f"Expected HTTP {status}, received {error}")
            return error.body
        raise AssertionError(path + " unexpectedly accepted invalid input")

    def raw_export(self, job_id, format_name):
        with urllib.request.urlopen(self.base_url + f"/benchmarks/runs/{job_id}/export?format={format_name}", timeout=60) as response:
            require("attachment" in response.headers.get("Content-Disposition", ""), "Export is missing attachment disposition")
            return response.read()

    def catalog_check(self):
        require(self.request("/health")["status"] == "UP", "Backend health unavailable")
        self.catalog = self.request("/benchmarks/catalog")
        require(self.catalog["provenance"] == PROVENANCE and self.catalog["liveStateIsolated"], "Benchmark provenance/isolation missing")
        require(self.catalog["networkId"] == self.graph["networkId"], "Benchmarks use a different physical network")
        digest = hashlib.sha256(self.graph_path.read_bytes()).hexdigest()
        require(self.catalog["graphSha256"] == digest, "Immutable geographic graph checksum differs")
        require({p["id"] for p in self.catalog["policies"]} == {"B0", "B1", "B2", "B3", "B4"}, "Conventional policy catalog incomplete")
        common = [p["allowedActions"] for p in self.catalog["equalActionPolicies"]]
        require(all(actions == common[0] for actions in common), "Controlled policies do not share the declared action set")
        require(abs(sum(self.catalog["selectionWeights"].values()) - 1) < 1e-9, "Objective weights are not normalized")
        require(self.catalog["unsupportedActions"] and self.catalog["modeledCostRates"], "Unsupported actions/cost assumptions are hidden")
        self.initial_live = self.state()
        require(self.initial_live["status"] != "RUNNING", "Read-only isolation test requires an already paused/draft/completed live scenario; it will not pause an operator")
        self.initial_current_state = self.connection.execute("SELECT state FROM cascadeshield_sim.current_state WHERE id=1").fetchone()[0]
        return {"network_id": self.catalog["networkId"], "graph_sha256": digest, "policies": 5, "equal_action_set": common[0], "live_status": self.initial_live["status"]}

    def input_guards(self):
        invalid = [
            ("missing parameters", {}),
            ("unknown policy", {**self.body, "policies": ["UNKNOWN"]}),
            ("null policy", {**self.body, "policies": [None]}),
            ("blank policy", {**self.body, "policies": [" "]}),
            ("null ablation", {**self.body, "ablations": [None]}),
            ("blank ablation", {**self.body, "ablations": [""]}),
            ("duplicate policy", {**self.body, "policies": ["B0", "B0"]}),
            ("unknown ablation", {**self.body, "ablations": ["UNKNOWN"]}),
            ("unknown comparison", {**self.body, "comparisonMode": "UNKNOWN"}),
            ("duplicate seeds", {**self.body, "parameters": {**self.body["parameters"], "seeds": [73, 73]}}),
            ("fractional seed", {**self.body, "parameters": {**self.body["parameters"], "seeds": [1.5]}}),
            ("excess trucks", {**self.body, "parameters": {**self.body["parameters"], "truckCount": 9}}),
            ("short horizon", {**self.body, "parameters": {**self.body["parameters"], "horizonSec": 20}}),
            ("unknown profile", {**self.body, "parameters": {**self.body["parameters"], "profile": "MISSING"}}),
            ("unknown parameter", {**self.body, "parameters": {**self.body["parameters"], "inventedColumn": 1}}),
        ]
        before_ids = {job["id"] for job in self.request("/benchmarks/runs")}
        for name, body in invalid:
            self.rejected(400, "/benchmarks/runs", body)
        require(self.state() == self.initial_live, "Invalid benchmark input changed live state")
        after_ids = {job["id"] for job in self.request("/benchmarks/runs")}
        require(before_ids <= after_ids, "Validation removed existing persisted jobs")
        self.rejected(404, "/benchmarks/runs/00000000-0000-0000-0000-000000000000")
        return {"http_400_cases": [name for name, _ in invalid], "unknown_job_http_404": True, "live_unchanged": True}

    def submit_complete(self):
        job = self.request("/benchmarks/runs", self.body)
        self.report.setdefault("job_ids", []).append(job["id"])
        deadline = time.monotonic() + self.timeout_sec
        while job["status"] not in {"COMPLETED", "FAILED"} and time.monotonic() < deadline:
            time.sleep(.5)
            job = self.request("/benchmarks/runs/" + job["id"])
        require(job["status"] == "COMPLETED", "Isolated benchmark did not complete: " + str(job.get("error") or job["status"]))
        require(job["totalRuns"] == job["completedRuns"] == 2, "Missing policy outcomes were silently substituted")
        return job

    def first_job(self):
        self.job = self.submit_complete()
        require(self.job["request"] == self.body, "Persisted request differs from submitted input")
        require(self.job["graphSha256"] == self.catalog["graphSha256"], "Job geographic provenance differs")
        return {"id": self.job["id"], "status": self.job["status"], "completed_policy_runs": 2}

    def paired_inputs(self):
        result = self.job["result"]
        require(result["provenance"] == PROVENANCE, "Generated research experiment lost provenance")
        require(len(result["scenarios"]) == 1 and len(result["runs"]) == 2, "Unexpected repeated-condition structure")
        scenario = result["scenarios"][0]
        require(scenario["seed"] == 73 and scenario["provenance"] == PROVENANCE, "Seed or simulated source changed")
        require(scenario["configuration"]["commands"] == [], "Hidden schedule was loaded into policy-visible replay")
        require(scenario["exogenousSchedule"], "Disruption schedule missing")
        require({run["policyId"] for run in result["runs"]} == {"B0", "B4"}, "Paired policy set differs")
        require(all(run["inputFingerprint"] == scenario["inputFingerprint"] for run in result["runs"]), "Policies did not run the identical input conditions")
        require(len({run["finalSummary"]["initialFingerprint"] for run in result["runs"]}) == 1, "Physical initial state changed by policy")
        require(all(run["finalSummary"]["comparisonMode"] == "EQUAL_ACTIONS" for run in result["runs"]), "Equal-action comparison mode differs")
        return {"scenario_id": scenario["id"], "input_fingerprint": scenario["inputFingerprint"], "seed": 73, "policies": ["B0", "B4"]}

    def realized_metrics(self):
        scenario = self.job["result"]["scenarios"][0]
        deadlines = {delivery["id"]: delivery["deadlineSec"] for delivery in scenario["configuration"]["operations"]["deliveries"]}
        details = []
        for run in self.job["result"]["runs"]:
            metrics = run["metrics"]
            require(metrics["provenance"] == PROVENANCE, "Final policy metrics are not realized simulated outcomes")
            times = run["finalSummary"]["deliveredAtSec"]
            completed = sum(value >= 0 for value in times.values())
            violations = sum(value < 0 or value > deadlines[key] + 1e-7 for key, value in times.items())
            lateness = sum(max(0, (value if value >= 0 else metrics["finalClockSec"]) - deadlines[key]) for key, value in times.items())
            require(metrics["deliveryCount"] == len(deadlines), "Delivery denominator includes invented records")
            require(metrics["completedDeliveries"] == completed and metrics["unfinishedDeliveries"] == len(deadlines) - completed, "Completed/censored counts do not match actual delivery records")
            require(metrics["slaViolations"] == violations and abs(metrics["slaViolationRate"] - violations / len(deadlines)) < 1e-9, "SLA aggregation differs from actual records")
            require(abs(metrics["totalDeliveryLatenessSec"] - lateness) < 1e-6, "Delivery lateness includes heuristic substitutes")
            require(all(math.isfinite(value) for value in metrics.values() if isinstance(value, (float, int))), "Nonfinite experimental metric")
            details.append({"policy": run["policyId"], "completed": completed, "sla_violations": violations, "actual_lateness_sec": lateness})
        return {"measured_outcomes": details}

    def predicted_vs_actual(self):
        enhanced = next(run for run in self.job["result"]["runs"] if run["policyId"] == "B4")
        require(enhanced["decisions"], "Disrupted case produced no actual enhanced decision trace")
        count = 0
        allowed = set(next(policy["allowedActions"] for policy in self.catalog["equalActionPolicies"] if policy["id"] == "B4"))
        for decision in enhanced["decisions"]:
            alternatives = decision["alternatives"]
            require(any(alt["action"]["id"] == decision["selectedActionId"] and alt["feasible"] for alt in alternatives), "Selected action lacks a feasible executed comparison")
            require(len(decision["knowledgeFingerprint"]) == 64, "Current-knowledge trial fingerprint missing")
            for alternative in alternatives:
                require(alternative["action"]["type"] in allowed, "Controlled policy received an extra action")
                require(alternative["metrics"]["provenance"] == "MODEL_ROLLOUT_FORECAST", "Hypothetical outcomes presented as realized policy outcomes")
                require(math.isfinite(alternative["score"]), "Decision score is not finite")
                count += 1
        return {"executed_hypothetical_alternatives": count, "decision_count": len(enhanced["decisions"]), "forecast_provenance": "MODEL_ROLLOUT_FORECAST", "actual_provenance": PROVENANCE}

    def physical_audits(self):
        for run in self.job["result"]["runs"]:
            summary = run["finalSummary"]
            require(summary["constraintAuditCadenceSec"] == 10, "Physical audit cadence missing")
            require(run["metrics"]["constraintViolations"] == len(summary["constraintAudit"]), "Constraint metric counts rejected proposals instead of measured invariants")
            require(run["metrics"]["constraintViolations"] == 0, "Bounded validated scenario physically violated modeled constraints")
            require(summary["constraintRejections"] >= 0, "Rejected-action attempts are not separately recorded")
            require(summary["beforeGraph"]["nodes"] and summary["afterGraph"]["nodes"], "Dependency snapshots absent")
        return {"policy_runs_audited": 2, "measured_violations": 0, "rejections_separate": True, "observation_cadence_sec": 10}

    def persistent_results(self):
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT status,request,result,graph_sha256,provenance FROM cascadeshield_sim.benchmark_jobs WHERE id=%s", (self.job["id"],))
            status, request, result, digest, provenance = cursor.fetchone()
        require(status == "COMPLETED" and request == self.body and result == self.job["result"], "HTTP result differs from committed PostgreSQL evidence")
        require(digest == self.catalog["graphSha256"] and provenance == PROVENANCE, "Database job provenance missing")
        require(any(job["id"] == self.job["id"] and job["status"] == "COMPLETED" for job in self.request("/benchmarks/runs")), "Completed job missing from history")
        return {"postgresql_job_persisted": self.job["id"], "jsonb_matches_http": True, "history_contains_completed_job": True}

    def export_results(self):
        directory = ROOT / "reports/milestone3_integration_exports" / self.job["id"]
        directory.mkdir(parents=True, exist_ok=False)
        payloads = {name: self.raw_export(self.job["id"], name) for name in ("json", "csv")}
        exported = json.loads(payloads["json"])
        require(exported == self.job, "JSON export differs from actual persisted job")
        rows = list(csv.DictReader(io.StringIO(payloads["csv"].decode("utf-8"))))
        require(len(rows) == 2 and {row["policyId"] for row in rows} == {"B0", "B4"}, "CSV has missing/substituted policy rows")
        for row in rows:
            run = next(run for run in self.job["result"]["runs"] if run["policyId"] == row["policyId"])
            require(row["inputFingerprint"] == run["inputFingerprint"] and row["provenance"] == PROVENANCE, "CSV input/provenance differs")
            require(abs(float(row["totalDeliveryLatenessSec"]) - run["metrics"]["totalDeliveryLatenessSec"]) < 1e-7, "CSV altered measured lateness")
        for name, payload in payloads.items():
            (directory / ("comparison." + name)).write_bytes(payload)
        self.rejected(400, f"/benchmarks/runs/{self.job['id']}/export?format=unsupported")
        self.report["export_directory"] = directory.relative_to(ROOT).as_posix()
        return {"json_runs": 2, "csv_rows": 2, "sha256": {name: hashlib.sha256(payload).hexdigest() for name, payload in payloads.items()}}

    def repeated_determinism(self):
        self.repeat = self.submit_complete()
        expected, actual = without_wallclock(self.job["result"]), without_wallclock(self.repeat["result"])
        require(expected == actual, "Repeated physical outcome differs: " + first_difference(expected, actual))
        require(self.repeat["id"] != self.job["id"], "Repeated run reused an old result instead of execution")
        return {"first_job": self.job["id"], "repeat_job": self.repeat["id"], "identical_physical_outcomes": True, "wallclock_fields_excluded": sorted(TIMING_KEYS)}

    def live_unchanged(self):
        require(self.state() == self.initial_live, "Isolated jobs changed live state: " + first_difference(self.initial_live, self.state()))
        saved = self.connection.execute("SELECT state FROM cascadeshield_sim.current_state WHERE id=1").fetchone()[0]
        require(saved == self.initial_current_state, "Benchmark changed persisted live checkpoint")
        require(set(self.mutation_paths) == {"/benchmarks/runs"}, "Harness issued an unapproved live mutation")
        return {"live_state_exactly_preserved": True, "persisted_live_checkpoint_preserved": True, "mutation_endpoint": "/benchmarks/runs"}

    def run(self):
        baseline = self.research_snapshot()
        self.check("catalog_and_immutable_geographic_provenance", self.catalog_check)
        self.check("malformed_inputs_return_http400_without_live_mutation", self.input_guards)
        self.check("bounded_seeded_job_executes_both_policies", self.first_job)
        self.check("paired_equal_action_inputs_and_hidden_schedule_boundary", self.paired_inputs)
        self.check("realized_delivery_metrics_match_actual_completion_records", self.realized_metrics)
        self.check("executed_hypothetical_predictions_separate_from_actual_outcomes", self.predicted_vs_actual)
        self.check("physical_constraint_audits_separate_from_rejected_candidates", self.physical_audits)
        self.check("actual_postgresql_job_persistence_and_history", self.persistent_results)
        self.check("csv_json_exports_match_persisted_outcomes", self.export_results)
        self.check("repeated_seeded_execution_is_deterministic_except_wallclock", self.repeated_determinism)
        self.check("live_and_persisted_scenario_exactly_preserved", self.live_unchanged)
        self.check("historical_research_tables_counts_and_checksums_preserved", lambda: self.verify_research_unchanged(baseline))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8080/api")
    parser.add_argument("--dsn", default=os.environ.get("DATABASE_URL"))
    parser.add_argument("--graph", type=Path, default=ROOT / "data/processed/chennai_osm/road_graph.json")
    parser.add_argument("--report", type=Path, default=ROOT / "reports/milestone3_integration_tests.json")
    parser.add_argument("--job-timeout-sec", type=float, default=600)
    args = parser.parse_args()
    if not args.dsn:
        parser.error("Set DATABASE_URL privately or use test_release_integration.py with an isolated --env-file.")
    harness = BenchmarkHarness(args.base_url, args.dsn, args.graph, args.job_timeout_sec)
    try:
        harness.run()
        harness.report["passed"] = True
    except Exception as error:
        harness.report.update(passed=False, failure=str(error))
        raise
    finally:
        harness.report["completed_at_utc"] = datetime.now(timezone.utc).isoformat()
        harness.report["passed_checks"] = sum(check["passed"] for check in harness.report["checks"])
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(harness.report, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
        harness.connection.close()


if __name__ == "__main__":
    main()
