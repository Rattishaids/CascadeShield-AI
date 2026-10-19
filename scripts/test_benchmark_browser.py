"""Execute the Benchmark Lab browser workflow without mutating the live simulator.

This is browser engineering evidence, not research effectiveness evidence.
Generated experiment outcomes are validated against the actual backend export.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import re
import urllib.request

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ui", default="http://127.0.0.1:5173")
    parser.add_argument("--api", default="http://127.0.0.1:8080/api")
    parser.add_argument("--report", type=Path, default=ROOT / "reports/milestone3_browser_tests.json")
    parser.add_argument("--timeout-ms", type=int, default=600000)
    args = parser.parse_args()
    report = {"started_at_utc": datetime.now(timezone.utc).isoformat(), "data_class": "BROWSER_ENGINEERING_TEST_EVIDENCE", "checks": [], "console_errors": [], "page_errors": [], "live_mutation_requests": []}
    screenshots = ROOT / "reports/screenshots"
    screenshots.mkdir(exist_ok=True)
    downloads = ROOT / ".runtime/benchmark-browser"
    downloads.mkdir(parents=True, exist_ok=True)

    def api(path):
        with urllib.request.urlopen(args.api + path, timeout=60) as response:
            return json.load(response)

    def record(name, **details):
        report["checks"].append({"name": name, "passed": True, **details})
        print("PASS " + name, flush=True)

    def live_configuration(state):
        return {"runId": state["runId"], "scenarioId": state.get("scenarioId"), "initialTrucks": [{"id": truck["id"], "initialAssignment": truck.get("initialAssignment")} for truck in state["trucks"]], "initialOperations": state.get("initialOperations"), "commandHistory": state.get("commandHistory"), "replaying": state.get("replaying")}

    try:
        before = api("/state")
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True, args=["--enable-webgl", "--use-gl=angle", "--use-angle=swiftshader"])
            context = browser.new_context(viewport={"width": 1680, "height": 1080}, device_scale_factor=1, accept_downloads=True)
            page = context.new_page()
            page.on("pageerror", lambda error: report["page_errors"].append(str(error)))
            page.on("console", lambda message: report["console_errors"].append(message.text) if message.type == "error" else None)

            def inspect_request(request):
                if request.method not in ("GET", "HEAD", "OPTIONS") and "/api/" in request.url and "/api/benchmarks/" not in request.url:
                    report["live_mutation_requests"].append({"method": request.method, "url": request.url})

            page.on("request", inspect_request)
            page.goto(args.ui, wait_until="domcontentloaded")
            lab = page.get_by_role("region", name="Benchmark Lab", exact=True)
            expect(lab).to_be_visible(timeout=30000)
            expect(lab.get_by_text("SIMULATED RESEARCH EXPERIMENTS", exact=True)).to_be_visible()
            expect(lab.get_by_role("button", name="Run benchmark comparison", exact=True)).to_be_enabled(timeout=30000)
            record("Benchmark Lab loads real catalog separately from live simulator")

            lab.get_by_label("Benchmark scenario profile").select_option("closure-contention")
            lab.get_by_label("Benchmark random seeds").fill("11")
            for label, value in {"Trucks": "2", "Dock service (s)": "30", "Deadline slack (s)": "20", "Departure gap (s)": "60", "Incident duration (s)": "60", "Outcome horizon (s)": "1200"}.items():
                lab.get_by_label(label, exact=True).fill(value)
            for policy in ("B1", "B2", "B3"):
                lab.get_by_role("checkbox", name=re.compile(r"^" + policy + r"\s")).uncheck()
            lab.get_by_role("radio", name=re.compile("^Equal action set")).check()
            lab.locator(".benchmark-advanced summary").click()
            lab.get_by_label("Decision interval (s)", exact=True).fill("60")
            lab.get_by_label("Branch rollout horizon (s)", exact=True).fill("300")
            lab.get_by_label("Maximum decisions per run", exact=True).fill("2")

            with page.expect_response(lambda response: response.request.method == "POST" and response.url.endswith("/api/benchmarks/runs"), timeout=30000) as submitted:
                lab.get_by_role("button", name="Run benchmark comparison", exact=True).click()
            assert submitted.value.ok, submitted.value.text()
            initial_job = submitted.value.json()
            report["job_id"] = initial_job["id"]
            record("UI submits configurable deterministic equal-action comparison", job_id=initial_job["id"])
            expect(lab.locator(".benchmark-job-status")).to_have_text("COMPLETED", timeout=args.timeout_ms)
            expect(lab.locator('[data-benchmark-results="true"]')).to_be_visible()
            result_job = api("/benchmarks/runs/" + initial_job["id"])
            result = result_job["result"]
            assert result["provenance"] == "SIMULATED_RESEARCH_EXPERIMENT"
            assert len(result["runs"]) == 2
            assert {row["policyId"] for row in result["runs"]} == {"B0", "B4"}
            assert len({row["inputFingerprint"] for row in result["runs"]}) == 1
            assert all(row["seed"] == 11 for row in result["runs"])
            expect(lab.get_by_role("table", name="Realized benchmark outcomes").locator("tbody tr")).to_have_count(2)
            record("completed UI metrics match actual paired backend result", policy_runs=2, input_fingerprint=result["runs"][0]["inputFingerprint"])

            lab.get_by_role("button", name="Inspect B4 seed 11", exact=True).click()
            expect(lab.get_by_text("B4 · seed 11: dependencies and decisions", exact=True)).to_be_visible()
            for phase in ("Before", "After"):
                graph_region = lab.get_by_role("region", name=f"{phase} benchmark dependency graph", exact=True)
                assert graph_region.locator(".dependency-node").count() > 0
            b4 = next(row for row in result["runs"] if row["policyId"] == "B4")
            assert b4["decisions"], "The generated disrupted case must expose an actual decision trace."
            expect(lab.locator(".benchmark-trace-detail")).to_be_visible()
            assert lab.locator(".benchmark-trace-list button").count() == len(b4["decisions"])
            assert lab.locator(".benchmark-trace-detail tbody tr").count() == len(b4["decisions"][0]["alternatives"])
            record("exported dependency snapshots and actual counterfactual trace inspected", decisions=len(b4["decisions"]))

            exports = {}
            for format_name in ("CSV", "JSON"):
                with page.expect_download(timeout=30000) as download_info:
                    lab.get_by_role("button", name="Export " + format_name, exact=True).click()
                downloaded = download_info.value
                target = downloads / downloaded.suggested_filename
                downloaded.save_as(target)
                exports[format_name] = target
            json_export = json.loads(exports["JSON"].read_text(encoding="utf-8-sig"))
            # Export is the actual comparison result, or the persisted job containing it.
            exported_result = json_export.get("result", json_export)
            assert exported_result["runs"] == result["runs"]
            csv_rows = list(csv.DictReader(io.StringIO(exports["CSV"].read_text(encoding="utf-8-sig"))))
            assert len(csv_rows) == len(result["runs"])
            record("CSV and JSON downloads contain real backend policy rows", csv_rows=len(csv_rows), json_runs=len(exported_result["runs"]))

            lab.get_by_role("button", name="Refresh benchmark history").click()
            expect(lab.locator(".benchmark-history").get_by_role("button").filter(has_text=initial_job["id"][:12])).to_be_visible()
            record("completed comparison remains available in job history")
            lab.screenshot(path=str(screenshots / "milestone-3-benchmark-lab.png"))
            lab.locator(".benchmark-trace").screenshot(path=str(screenshots / "milestone-3-benchmark-trace.png"))
            page.screenshot(path=str(screenshots / "milestone-3-dashboard.png"), full_page=True)
            browser.close()

        after = api("/state")
        assert live_configuration(before) == live_configuration(after), "Benchmark changed live scenario configuration or commands."
        if before["status"] != "RUNNING":
            assert before["clockSec"] == after["clockSec"], "Isolated experiment advanced paused live clock."
            assert before["trucks"] == after["trucks"], "Isolated experiment mutated paused live trucks."
        assert not report["live_mutation_requests"], report["live_mutation_requests"]
        record("live run, assignments, command schedule and paused clock preserved", run_id=after["runId"], clock_before=before["clockSec"], clock_after=after["clockSec"])
        assert not report["page_errors"], report["page_errors"]
        # External public basemap requests can fail independently of lab logic.
        lab_errors = [message for message in report["console_errors"] if "tile.openstreetmap" not in message and "ERR_CONNECTION" not in message]
        assert not lab_errors, lab_errors
        record("browser workflow has no application page or console errors")
        report["passed"] = True
    except Exception as error:
        report["passed"] = False
        report["error"] = str(error)
        raise
    finally:
        report["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
