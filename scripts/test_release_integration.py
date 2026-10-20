"""Run existing integration suites against an explicitly disposable ZIP database.

This adapter reuses the original milestone checks. It replaces their original
18-table research prerequisite with a strict *absent research import table*
guard, redirects generated exports, and restarts only the release Compose app.
It never creates legacy records to make an unavailable check appear to pass.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import psycopg
from psycopg.conninfo import make_conninfo

import test_benchmark_integration as benchmark
import test_operational_integration as operations
from test_simulator_integration import Harness, first_difference, require


def read_settings(path: Path) -> dict[str, str]:
    """Read literal KEY=value settings without shell execution or interpolation."""
    settings = {}
    for number, original in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        line = original.strip()
        if not line or line.startswith("#"):
            continue
        match = re.fullmatch(r"([A-Z][A-Z0-9_]*)\s*=\s*(.*)", line)
        require(match is not None, f"Invalid env-file syntax at line {number}")
        key, value = match.groups()
        if value.startswith(("'", '"')):
            require(len(value) >= 2 and value[-1] == value[0], f"Unclosed env value at line {number}")
            value = value[1:-1]
        require(key not in settings, f"Duplicate env-file key at line {number}")
        settings[key] = value
    for key in ("COMPOSE_PROJECT_NAME", "BACKEND_PORT", "POSTGRES_PORT", "POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD"):
        require(bool(settings.get(key)), "Missing required local setting: " + key)
    for key in ("BACKEND_PORT", "POSTGRES_PORT"):
        require(settings[key].isdigit() and 1 <= int(settings[key]) <= 65535, "Invalid port setting: " + key)
    require(re.fullmatch(r"[a-z0-9][a-z0-9_-]*", settings["COMPOSE_PROJECT_NAME"]) is not None, "Invalid Compose project name")
    require(settings["COMPOSE_PROJECT_NAME"] not in {"cascadeshield", "cascadeshield-simulator"}, "Refusing original research Compose project")
    return settings


class ReleaseDatabaseMixin:
    """Adapt the data boundary and process lifecycle, leaving core checks intact."""

    def research_snapshot(self):
        table = self.connection.execute("SELECT to_regclass('cascadeshield_meta.imports')").fetchone()[0]
        require(table is None, "Refusing integration mutations: research import metadata exists in the target database")
        return []

    def verify_research_unchanged(self, baseline):
        require(baseline == [] and self.research_snapshot() == [], "Unexpected historical research imports in ZIP test database")
        return {"research_tables": 0, "rows": 0, "research_import_table_absent": True, "preserved": True}

    def check(self, name, function):
        if name == "original_version_one_scenario_remains_replayable":
            count = self.connection.execute("SELECT count(*) FROM cascadeshield_sim.scenarios WHERE configuration->>'version'='1'").fetchone()[0]
            if count == 0:
                self.report["checks"].append({"name": name, "status": "NOT_AVAILABLE", "passed": None,
                    "reason": "A fresh ZIP database has no original Milestone 1 version-1 saved scenario; no legacy record was fabricated."})
                print("NOT_AVAILABLE " + name, flush=True)
                return
        return super().check(name, function)

    def release_safety(self):
        self.research_snapshot()
        state = self.state()
        persisted = self.connection.execute("SELECT state FROM cascadeshield_sim.current_state WHERE id=1").fetchone()
        require(persisted is not None, "Release database has no initialized simulator checkpoint")
        require(persisted[0]["runId"] == state["runId"] and persisted[0]["networkId"] == state["networkId"],
                "API and target database do not identify the same simulator; refusing mutations")
        require(state["status"] != "RUNNING", "Pause the disposable simulator before integration tests")
        jobs = self.request("/benchmarks/runs")
        require(not any(j["status"] in {"QUEUED", "RUNNING"} for j in jobs), "Wait for isolated benchmark jobs before integration tests")
        return {"research_import_table_absent": True, "api_matches_database": True, "reset_explicitly_authorized": True}

    def restart(self):
        """Verify an actual release-backend restart without changing saved state."""
        self.release_safety()
        before = self.state()
        scenarios = self.request("/scenarios")
        approvals = self.request("/ai/approvals")
        jobs = {j["id"]: self.request("/benchmarks/runs/" + j["id"]) for j in self.request("/benchmarks/runs")}
        persisted_before = self.connection.execute("SELECT state FROM cascadeshield_sim.current_state WHERE id=1").fetchone()[0]
        events_before = self.connection.execute("SELECT count(*),max(sequence) FROM cascadeshield_sim.simulation_events WHERE run_id=%s", (before["runId"],)).fetchone()
        command = ["docker", "compose", "--env-file", str(self.release_env_file), "-f", str(ROOT / "compose.yaml"), "restart", "backend"]
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=120)
        require(result.returncode == 0, "Release backend restart failed: " + result.stderr[-1500:])
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            try:
                if self.request("/health", timeout=5)["status"] == "UP":
                    break
            except Exception:
                pass
            time.sleep(.5)
        else:
            raise AssertionError("Release backend did not recover after actual restart")
        after = self.state()
        require(before == after, "Actual restart changed saved state: " + first_difference(before, after))
        require(self.request("/scenarios") == scenarios, "Actual restart changed saved scenarios")
        require(self.request("/ai/approvals") == approvals, "Actual restart changed operator approvals")
        require({j["id"]: self.request("/benchmarks/runs/" + j["id"]) for j in self.request("/benchmarks/runs")} == jobs,
                "Actual restart changed persisted benchmark jobs or results")
        require(self.connection.execute("SELECT state FROM cascadeshield_sim.current_state WHERE id=1").fetchone()[0] == persisted_before,
                "Actual restart changed the database checkpoint")
        require(self.connection.execute("SELECT count(*),max(sequence) FROM cascadeshield_sim.simulation_events WHERE run_id=%s", (before["runId"],)).fetchone() == events_before,
                "Actual restart changed persisted audit events")
        time.sleep(.3)
        require(self.state()["clockSec"] == before["clockSec"], "Actual restart advanced a non-running simulation")
        self.research_snapshot()
        return {"actual_container_restart": True, "clock_sec": after["clockSec"], "truck_count": len(after["trucks"]),
                "scenarios": len(scenarios), "approvals": len(approvals), "benchmark_jobs": len(jobs),
                "events": events_before[0], "state_checkpoint_scenarios_approvals_jobs_and_clock_preserved": True}


class ReleaseSimulatorHarness(ReleaseDatabaseMixin, Harness):
    pass


class ReleaseOperationalHarness(ReleaseDatabaseMixin, operations.OperationalHarness):
    pass


class ReleaseBenchmarkHarness(ReleaseDatabaseMixin, benchmark.BenchmarkHarness):
    pass


def sanitized(value, password):
    if isinstance(value, dict):
        return {key: sanitized(item, password) for key, item in value.items()}
    if isinstance(value, list):
        return [sanitized(item, password) for item in value]
    if isinstance(value, str):
        if password:
            value = value.replace(password, "<redacted>")
        value = value.replace(str(ROOT), "<release-root>").replace(ROOT.as_posix(), "<release-root>")
        return re.sub(r"(?i)C:[\\/]+Users[\\/]+[^\\/\r\n]+", "<private-user-directory>", value)
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", required=True, choices=("simulator", "operations", "benchmark"))
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--allow-reset", action="store_true", help="Explicitly permit resetting only the isolated ZIP simulation")
    parser.add_argument("--timeout-sec", type=int, default=900, help="Per benchmark job timeout")
    args = parser.parse_args()
    report = {"schemaVersion": "cascadeshield.release-integration/1.0", "suite": args.suite,
              "provenance": "ENGINEERING_TEST_EVIDENCE", "started_at_utc": datetime.now(timezone.utc).isoformat(), "checks": []}
    harness = None
    password = ""
    passed = False
    try:
        require(args.allow_reset, "This suite may reset simulated data; rerun with --allow-reset only for an isolated ZIP database")
        env_file = args.env_file if args.env_file.is_absolute() else ROOT / args.env_file
        env_file = env_file.resolve()
        settings = read_settings(env_file)
        password = settings["POSTGRES_PASSWORD"]
        dsn = make_conninfo(host="127.0.0.1", port=settings["POSTGRES_PORT"], dbname=settings["POSTGRES_DB"],
                            user=settings["POSTGRES_USER"], password=password, connect_timeout=10)
        base_url = "http://127.0.0.1:" + settings["BACKEND_PORT"] + "/api"
        graph = ROOT / "data/processed/chennai_osm/road_graph.json"
        export_root = ROOT / ".runtime/release-integration" / args.suite
        export_root.mkdir(parents=True, exist_ok=True)
        # Only module-level export roots change. Core assertions and API workflows
        # remain the original milestone implementation; no research data is loaded.
        operations.ROOT = export_root
        benchmark.ROOT = export_root
        cls = {"simulator": ReleaseSimulatorHarness, "operations": ReleaseOperationalHarness,
               "benchmark": ReleaseBenchmarkHarness}[args.suite]
        extra = (args.timeout_sec,) if args.suite == "benchmark" else ()
        harness = cls(base_url, dsn, graph, *extra)
        harness.release_env_file = env_file
        harness.report.update(report)
        report = harness.report
        harness.check("isolated_zip_database_and_api_safety_guard", harness.release_safety)
        harness.run()
        if args.suite != "operations":
            harness.check("actual_release_backend_restart_preserves_state_and_results", harness.restart)
        if "export_directory" in report:
            report["export_directory"] = (export_root / report["export_directory"]).relative_to(ROOT).as_posix()
        passed = all(row.get("passed") is True for row in report["checks"] if row.get("status") != "NOT_AVAILABLE")
    except Exception as error:
        report.update(error=str(error), traceback=traceback.format_exc())
        if not any(row.get("passed") is False for row in report["checks"]):
            report["checks"].append({"name": "suite_setup_or_completion", "passed": False, "error": str(error)})
    finally:
        if harness is not None:
            harness.connection.close()
        report.update(passed=passed, completed_at_utc=datetime.now(timezone.utc).isoformat(),
                      passed_checks=sum(row.get("passed") is True for row in report["checks"]),
                      failed_checks=sum(row.get("passed") is False for row in report["checks"]),
                      not_available_checks=sum(row.get("status") == "NOT_AVAILABLE" for row in report["checks"]))
        report_path = args.report if args.report.is_absolute() else ROOT / args.report
        report_path.parent.mkdir(parents=True, exist_ok=True)
        if report_path.exists():
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
            report_path.rename(report_path.with_name(report_path.stem + ".previous." + stamp + report_path.suffix))
        report_path.write_text(json.dumps(sanitized(report, password), indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(f"{'PASS' if passed else 'FAIL'} {args.suite}: {report['passed_checks']} passed, {report['failed_checks']} failed, {report['not_available_checks']} not available", flush=True)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
