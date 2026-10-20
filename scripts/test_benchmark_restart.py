"""Restart only an idle backend and verify benchmark/live/research persistence.

No HTTP mutations, scenario resets, fleet edits or experiment submissions occur.
Refuses to restart when any benchmark job is QUEUED/RUNNING or live time is RUNNING.
Run after all benchmark jobs and operator activity have stopped.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import http.client
import json
import os
from pathlib import Path
import subprocess
import time
import urllib.error

from test_simulator_integration import Harness, HttpError, ROOT, first_difference, require


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False, default=str).encode()).hexdigest()


class RestartHarness(Harness):
    def __init__(self, base_url, dsn, graph_path, job_id):
        super().__init__(base_url, dsn, graph_path)
        self.job_id = job_id
        self.report.update(data_classes=["REAL_GEOGRAPHIC_DATA", "SIMULATED_RESEARCH_EXPERIMENT", "ENGINEERING_TEST_EVIDENCE"], http_mutations=False, actual_backend_restart=False)

    def request(self, path, body=None, method=None, timeout=60):
        actual_method = method or ("POST" if body is not None else "GET")
        require(body is None and actual_method in {"GET", "HEAD"}, "Restart verification attempted an HTTP mutation")
        return super().request(path, body, actual_method, timeout)

    def ensure_idle(self):
        active = self.connection.execute("SELECT id::text,status FROM cascadeshield_sim.benchmark_jobs WHERE status IN ('QUEUED','RUNNING') ORDER BY created_at").fetchall()
        require(not active, "Refusing backend restart: active benchmark jobs " + str(active))
        state = self.state()
        require(state["status"] != "RUNNING", "Refusing backend restart: live simulator is RUNNING; this harness will not pause an operator")
        require(self.request("/health")["status"] == "UP", "Backend health is not UP")
        return state

    def all_jobs(self):
        return self.connection.execute("SELECT id::text,status,completed_runs,total_runs,request,result,error,created_at::text,finished_at::text,network_id,graph_sha256,provenance FROM cascadeshield_sim.benchmark_jobs ORDER BY id").fetchall()

    def prepared_snapshot(self):
        self.live_before = self.ensure_idle()
        if self.job_id is None:
            latest = self.connection.execute("SELECT id::text FROM cascadeshield_sim.benchmark_jobs WHERE status='COMPLETED' ORDER BY finished_at DESC LIMIT 1").fetchone()
            require(latest is not None, "No completed benchmark job exists to verify")
            self.job_id = latest[0]
        self.completed_job = self.request("/benchmarks/runs/" + self.job_id)
        require(self.completed_job["status"] == "COMPLETED" and self.completed_job["result"] is not None, "Selected benchmark job is not completed with actual results")
        self.jobs_before = self.all_jobs()
        self.current_state_before = self.connection.execute("SELECT state FROM cascadeshield_sim.current_state WHERE id=1").fetchone()[0]
        self.audit_before = self.connection.execute("SELECT count(*),max(sequence) FROM cascadeshield_sim.simulation_events WHERE run_id=%s", (self.live_before["runId"],)).fetchone()
        self.audit_rows_before = self.connection.execute("SELECT to_jsonb(e) FROM cascadeshield_sim.simulation_events e WHERE run_id=%s ORDER BY sequence", (self.live_before["runId"],)).fetchall()
        self.scenarios_before = self.request("/scenarios")
        self.scenario_rows_before = self.connection.execute("SELECT to_jsonb(s) FROM cascadeshield_sim.scenarios s ORDER BY id").fetchall()
        self.research_before = self.research_snapshot()
        self.report.update(job_id=self.job_id, benchmark_result_sha256=digest(self.completed_job["result"]), live_run_id=self.live_before["runId"], live_status=self.live_before["status"], live_clock_sec=self.live_before["clockSec"])
        return {"completed_job": self.job_id, "policy_runs": len(self.completed_job["result"]["runs"]), "persisted_jobs": len(self.jobs_before), "live_status": self.live_before["status"], "live_clock_sec": self.live_before["clockSec"], "research_tables": len(self.research_before), "research_rows": sum(row[3] for row in self.research_before)}

    @staticmethod
    def docker(arguments, timeout=60):
        result = subprocess.run(["docker", *arguments], capture_output=True, text=True, timeout=timeout)
        require(result.returncode == 0, "Docker command failed: " + result.stderr[-1500:])
        return result.stdout.strip()

    def restart_backend(self):
        # Recheck authoritative jobs immediately before the only service mutation.
        state = self.ensure_idle()
        require(state == self.live_before, "Live state changed while preparing restart: " + first_difference(self.live_before, state))
        compose = ["compose", "-f", str(ROOT / "simulator/compose.yaml")]
        container = self.docker([*compose, "ps", "-q", "backend"])
        require(bool(container) and "\n" not in container, "Expected exactly one existing backend container")
        started_before = self.docker(["inspect", "--format", "{{.State.StartedAt}}", container])
        self.docker([*compose, "restart", "backend"])
        self.report["actual_backend_restart"] = True
        deadline = time.monotonic() + 120
        last_error = ""
        while time.monotonic() < deadline:
            try:
                if self.request("/health", timeout=5)["status"] == "UP":
                    break
            except (urllib.error.URLError, HttpError, OSError, http.client.HTTPException) as error:
                last_error = str(error)
            time.sleep(.5)
        else:
            raise AssertionError("Backend did not recover after restart: " + last_error)
        started_after = self.docker(["inspect", "--format", "{{.State.StartedAt}}", container])
        require(started_before != started_after, "Backend container start timestamp did not change")
        return {"container_id": container, "started_before_utc": started_before, "started_after_utc": started_after, "health": "UP"}

    def benchmark_preserved(self):
        after = self.request("/benchmarks/runs/" + self.job_id)
        require(after == self.completed_job, "Restart changed persisted completed job: " + first_difference(self.completed_job, after))
        require(self.all_jobs() == self.jobs_before, "Restart changed persisted benchmark requests, results or statuses")
        return {"job_id": self.job_id, "policy_runs": len(after["result"]["runs"]), "exact_result_sha256": digest(after["result"]), "all_persisted_jobs_preserved": len(self.jobs_before)}

    def live_preserved(self):
        after = self.state()
        require(after == self.live_before, "Restart changed stationary live state: " + first_difference(self.live_before, after))
        require(self.request("/scenarios") == self.scenarios_before, "Restart changed saved scenarios")
        require(self.connection.execute("SELECT to_jsonb(s) FROM cascadeshield_sim.scenarios s ORDER BY id").fetchall() == self.scenario_rows_before, "Restart changed saved scenario configuration or metadata")
        checkpoint = self.connection.execute("SELECT state FROM cascadeshield_sim.current_state WHERE id=1").fetchone()[0]
        require(checkpoint == self.current_state_before, "Restart changed PostgreSQL live checkpoint")
        audit = self.connection.execute("SELECT count(*),max(sequence) FROM cascadeshield_sim.simulation_events WHERE run_id=%s", (after["runId"],)).fetchone()
        require(audit == self.audit_before, "Restart changed live audit events")
        audit_rows = self.connection.execute("SELECT to_jsonb(e) FROM cascadeshield_sim.simulation_events e WHERE run_id=%s ORDER BY sequence", (after["runId"],)).fetchall()
        require(audit_rows == self.audit_rows_before, "Restart changed persisted audit event contents")
        time.sleep(.6)
        frozen = self.state()
        require(frozen == after, "Recovered stationary live state advanced without an operator command")
        return {"run_id": after["runId"], "status": after["status"], "clock_sec": after["clockSec"], "trucks": len(after["trucks"]), "saved_scenarios": len(self.scenarios_before), "audit_events": audit[0], "exact_api_and_database_checkpoint_preserved": True}

    def run(self):
        self.check("idle_backend_live_and_research_snapshot_prepared", self.prepared_snapshot)
        self.check("actual_backend_container_restart_and_health_recovery", self.restart_backend)
        self.check("completed_benchmark_results_and_all_job_rows_exactly_preserved", self.benchmark_preserved)
        self.check("live_state_checkpoint_scenarios_audit_and_stationary_clock_exactly_preserved", self.live_preserved)
        self.check("historical_research_counts_and_import_provenance_preserved", lambda: self.verify_research_unchanged(self.research_before))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8080/api")
    parser.add_argument("--dsn", default=os.environ.get("DATABASE_URL"))
    parser.add_argument("--job-id", help="Completed job to verify; defaults to most recently completed")
    parser.add_argument("--report", type=Path, default=ROOT / "reports/milestone3_restart_tests.json")
    args = parser.parse_args()
    if not args.dsn:
        parser.error("Set DATABASE_URL privately or pass --dsn for the intended research database. For an isolated release database, use scripts/test_release_integration.py instead.")
    harness = RestartHarness(args.base_url, args.dsn, ROOT / "data/processed/chennai_osm/road_graph.json", args.job_id)
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
