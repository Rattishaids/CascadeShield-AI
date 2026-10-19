"""Real browser verification of manually configured simulated operational resources.

Uses real Chennai roads, operator UI configuration, backend commands for exact
observation times, and actual browser screenshots. Resets simulator only.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re
import urllib.request
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ui", default="http://127.0.0.1:5173")
    parser.add_argument("--api", default="http://127.0.0.1:8080/api")
    parser.add_argument("--report", type=Path, default=ROOT / "reports/milestone_2_browser_tests.json")
    args = parser.parse_args()
    report = {"started_at_utc": datetime.now(timezone.utc).isoformat(), "data_class": "BROWSER_ENGINEERING_TEST_EVIDENCE", "checks": [], "console_errors": [], "page_errors": [], "trained_model": False}
    shots = ROOT / "reports/screenshots"
    shots.mkdir(exist_ok=True)

    def api(path, body=None, method=None):
        payload = None if body is None else json.dumps(body, allow_nan=False).encode()
        req = urllib.request.Request(args.api + path, data=payload, method=method or ("POST" if payload is not None else "GET"), headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as response:
            return json.load(response)

    def record(name, **details):
        report["checks"].append({"name": name, "passed": True, **details})
        print("PASS " + name, flush=True)

    graph = json.loads((ROOT / "data/processed/chennai_osm/road_graph.json").read_text(encoding="utf-8"))
    pair, bbox = graph["metadata"]["demoPairs"][0], graph["bbox"]
    edges = {e["id"]: e for e in graph["edges"]}

    def mercator(lat):
        return (1 - math.log(math.tan(math.pi / 4 + math.radians(lat) / 2)) / math.pi) / 2

    try:
        state = api("/control", {"action": "RESET"})
        for truck in state["trucks"]:
            api("/trucks/" + truck["id"], method="DELETE")
        ops = api("/operations")
        for kind in ("deliveries", "docks", "drivers", "warehouses"):
            for resource in ops[kind]:
                api(f"/operations/{kind}/{resource['id']}", method="DELETE")
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True, args=["--enable-webgl", "--use-gl=angle", "--use-angle=swiftshader"])
            page = browser.new_page(viewport={"width": 1680, "height": 1080}, device_scale_factor=1)
            page.on("pageerror", lambda error: report["page_errors"].append(str(error)))
            page.on("console", lambda message: report["console_errors"].append(message.text) if message.type == "error" else None)
            page.goto(args.ui, wait_until="domcontentloaded")
            expect(page.get_by_role("button", name="Backend connected")).to_be_visible(timeout=30000)
            expect(page.locator(".map-wrap")).to_have_attribute("data-road-network-ready", "true", timeout=30000)

            def map_click(coords):
                canvas = page.locator(".maplibregl-canvas").bounding_box()
                west, east = (bbox[1] + 180) / 360, (bbox[3] + 180) / 360
                north, south = mercator(bbox[2]), mercator(bbox[0])
                scale = min((canvas["width"] - 92) / (east - west), (canvas["height"] - 92) / (south - north))
                x = canvas["x"] + canvas["width"] / 2 + ((coords[0] + 180) / 360 - (west + east) / 2) * scale
                y = canvas["y"] + canvas["height"] / 2 + (mercator(coords[1]) - (north + south) / 2) * scale
                page.mouse.click(x, y)

            for index, suffix in enumerate(("A", "B"), 1):
                page.get_by_role("button", name="Add truck", exact=True).click()
                page.get_by_label("Truck ID", exact=True).fill("BROW-" + suffix)
                map_click(pair["start"])
                map_click(pair["destination"])
                page.get_by_role("button", name="Calculate road route").click()
                expect(page.get_by_text("CONNECTED ROAD ROUTE", exact=True)).to_be_visible(timeout=20000)
                if suffix == "B":
                    page.get_by_label(re.compile("Depart after")).fill(str(200 / 60))
                page.get_by_role("button", name="Add truck to fleet").click()
                expect(page.locator(".fleet-card")).to_have_count(index, timeout=20000)
                page.get_by_role("button", name="Close truck details").click()
            state = api("/state")
            baseline = math.ceil(state["trucks"][0]["route"]["baseTravelSec"] * 10) / 10
            physical = edges[state["trucks"][0]["route"]["edgeIds"][0]]["physicalId"]
            record("two trucks manually routed on actual Chennai map", baseline_sec=baseline)

            page.get_by_role("button", name="Configure resources", exact=True).click()
            dialog = page.get_by_role("dialog")
            tabs = dialog.locator(".operations-tabs")

            def tab(label):
                tabs.get_by_role("button", name=re.compile("^" + label)).click()

            def identify(resource_id, name):
                dialog.get_by_label("Resource ID", exact=True).fill(resource_id)
                dialog.get_by_label("Resource name", exact=True).fill(name)

            def create(kind):
                with page.expect_response(lambda response: response.url.endswith("/api/operations/" + kind) and response.request.method == "POST") as response:
                    dialog.get_by_role("button", name="Create simulated resource", exact=True).click()
                assert response.value.ok, response.value.text()
                expect(dialog.get_by_role("button", name="Save resource changes", exact=True)).to_be_enabled(timeout=10000)

            identify("BROW-W", "Browser simulated receiving warehouse")
            dialog.get_by_label("Copy truck destination").select_option("BROW-A")
            create("warehouses")
            tab("Docks")
            identify("BROW-D", "Browser simulated shared dock")
            dialog.get_by_label("Dock warehouse").select_option("BROW-W")
            dialog.get_by_label("Dock service duration").fill("300")
            dialog.get_by_label("Dock open until").fill("10000")
            create("docks")
            tab("Drivers")
            for index, suffix in enumerate(("A", "B")):
                if index:
                    dialog.get_by_role("button", name="New", exact=True).click()
                identify("BROW-DR" + suffix, "Browser simulated driver " + suffix)
                dialog.get_by_label("Driver shift ends").fill("10000")
                create("drivers")
            tab("Deliveries")
            for index, suffix in enumerate(("A", "B")):
                if index:
                    dialog.get_by_role("button", name="New", exact=True).click()
                identify("BROW-L" + suffix, "Browser simulated delivery " + suffix)
                dialog.get_by_label("Delivery warehouse").select_option("BROW-W")
                dialog.get_by_label("Delivery load kg").fill("200")
                dialog.get_by_label("Delivery deadline", exact=True).fill(str(baseline + (630 if suffix == "B" else 600)))
                create("deliveries")
            tab("Assignments")
            for suffix in ("A", "B"):
                dialog.get_by_label("Assignment truck").select_option("BROW-" + suffix)
                dialog.get_by_label("Assignment driver").select_option("BROW-DR" + suffix)
                dialog.get_by_label("Assignment dock").select_option("BROW-D")
                start = baseline + (300 if suffix == "B" else 0)
                dialog.get_by_label("Reservation begins").fill(str(start))
                dialog.get_by_label("Reservation ends").fill(str(start + 300))
                dialog.get_by_label("Assign delivery BROW-L" + suffix, exact=True).check()
                with page.expect_response(lambda response: response.url.endswith("/api/operations/assignments") and response.request.method == "POST") as response:
                    dialog.get_by_role("button", name="Save truck dependencies", exact=True).click()
                assert response.value.ok, response.value.text()
                expect(dialog.locator(".assignment-card")).to_have_count(1 if suffix == "A" else 2, timeout=10000)
                expect(dialog.get_by_role("button", name="Save truck dependencies", exact=True)).to_be_enabled()
            dialog.get_by_role("button", name="Close operational resources").click()
            state = api("/state")
            assert len(state["operations"]["assignments"]) == 2
            expect(page.get_by_role("button", name=re.compile("Simulated warehouse BROW-W"))).to_have_count(1)
            expect(page.get_by_role("button", name="Inspect resource DOCK:BROW-D", exact=True)).to_have_count(1)
            record("warehouse dock drivers deliveries and assignments created through UI", simulated_resources=6, directed_dependencies=len(state["operations"]["graph"]["edges"]))

            page.get_by_role("button", name="Add truck", exact=True).click()
            page.get_by_role("button", name=re.compile("Simulated warehouse BROW-W")).click()
            expect(page.locator(".map-instruction")).to_contain_text("destination")
            map_click(pair["start"])
            page.get_by_role("button", name="Calculate road route").click()
            expect(page.get_by_text("CONNECTED ROAD ROUTE", exact=True)).to_be_visible(timeout=20000)
            page.get_by_role("button", name="Close truck editor", exact=True).click()
            record("existing truck and warehouse markers support route endpoint selection")

            # Exact disruption timing is supplied via the authoritative API; M1 browser
            # checks independently exercise physical-road selection and injection.
            api("/incidents", {"type": "CLOSURE", "physicalId": physical, "severity": 1, "durationSec": 90})
            expect(page.locator(".consequence-list")).to_contain_text("DOCK OVERLAP", timeout=20000)
            expect(page.locator(".consequence-list")).to_contain_text("DELIVERY DEADLINE")
            expect(page.locator(".affected-resources")).to_contain_text("BROW-B")
            page.get_by_role("button", name="Inspect resource TRUCK:BROW-B", exact=True).click()
            expect(page.locator(".graph-inspector")).to_contain_text("INCIDENT:I001")
            page.get_by_label("Affected only", exact=True).check()
            expect(page.get_by_role("button", name="Inspect resource TRUCK:BROW-B", exact=True)).to_have_count(1)
            page.get_by_label("Affected only", exact=True).uncheck()
            page.screenshot(path=str(shots / "milestone-2-predicted-cascade.png"), full_page=True)
            record("computed indirect graph risk and predicted consequence timeline rendered", closure_physical_id=physical)

            api("/control", {"action": "STEP", "stepSec": 1})
            page.get_by_role("button", name="Configure resources", exact=True).click()
            tab("Drivers")
            toggle = dialog.get_by_role("button", name="Toggle availability for driver BROW-DRB", exact=True)
            toggle.click()
            expect(toggle).to_have_text("Unavailable", timeout=10000)
            expect(page.locator(".fleet-card").filter(has_text="BROW-B")).to_contain_text("Operational ETA unknown")
            api("/control", {"action": "STEP", "stepSec": 219})
            held = next(t for t in api("/state")["trucks"] if t["id"] == "BROW-B")
            assert held["status"] == "DRIVER_UNAVAILABLE" and held["distanceTravelledM"] == 0
            toggle.click()
            expect(toggle).to_have_text("Available", timeout=10000)
            dialog.get_by_role("button", name="Close operational resources").click()
            record("driver availability toggle constrains backend movement and unknown ETA", held_clock_sec=220)

            state = api("/control", {"action": "STEP", "stepSec": 780})
            assignments = {a["truckId"]: a for a in state["operations"]["assignments"]}
            assert assignments["BROW-A"]["status"] == "UNLOADING" and assignments["BROW-B"]["status"] == "QUEUED"
            page.get_by_role("button", name=re.compile("^Realized ")).click()
            expect(page.locator(".consequence-list")).to_contain_text("DOCK QUEUE", timeout=20000)
            expect(page.locator(".consequence-list")).to_contain_text("SIMULATED_OUTCOME")
            page.screenshot(path=str(shots / "milestone-2-realized-queue.png"), full_page=True)
            record("actual dock queue and realized consequence timeline rendered", clock_sec=state["clockSec"], queue_sec_so_far=assignments["BROW-B"]["queueSec"])

            name = "M2 browser verified cascade " + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            page.get_by_role("button", name="Scenarios", exact=True).click()
            page.get_by_label("Scenario name", exact=True).fill(name)
            page.get_by_role("button", name="Save current scenario", exact=True).click()
            item = page.locator(".scenario-item").filter(has_text=name)
            expect(item).to_have_count(1, timeout=20000)
            with page.expect_download() as download:
                item.get_by_role("button", name="Export " + name).click()
            exported = json.loads(Path(download.value.path()).read_text(encoding="utf-8"))
            assert exported["configuration"]["version"] == 2 and len(exported["configuration"]["operations"]["assignments"]) == 2
            page.get_by_role("button", name="Close scenario library", exact=True).click()
            completed = api("/control", {"action": "STEP", "stepSec": 500})
            assert completed["operations"]["kpis"]["lateDeliveries"] == 1
            expect(page.locator(".consequence-list")).to_contain_text("DELIVERY LATE", timeout=20000)
            expect(page.locator(".operational-summary")).to_contain_text("2 / 2")
            with page.expect_download() as download:
                page.get_by_role("button", name="Export operational graph snapshot", exact=True).click()
            snapshot = json.loads(Path(download.value.path()).read_text(encoding="utf-8"))
            assert snapshot["schemaVersion"] == "cascadeshield.graph-snapshot/1.0"
            assert snapshot["realizedLabels"] and snapshot["provenance"]["outcomeLabels"] == "SIMULATED_OUTCOME"
            record("realized delivery lateness KPIs and versioned snapshot download", operational_kpis=completed["operations"]["kpis"], outcome_labels=len(snapshot["realizedLabels"]))

            page.get_by_role("button", name="Scenarios", exact=True).click()
            item = page.locator(".scenario-item").filter(has_text=name)
            item.get_by_role("button", name="Replay", exact=True).click()
            expect(page.get_by_role("dialog")).to_have_count(0, timeout=10000)
            state = api("/state")
            assert state["replaying"] and state["clockSec"] == 0 and len(state["operations"]["assignments"]) == 2
            replay = api("/control", {"action": "STEP", "stepSec": completed["clockSec"]})
            assert replay["operations"] == completed["operations"]
            record("saved operational resources and recorded availability changes replay exactly", scenario_id=exported["id"])
            # Leave an inspectable, paused replay at the actual queue for the operator.
            api("/scenarios/" + exported["id"] + "/replay", {})
            api("/control", {"action": "STEP", "stepSec": 1000})
            page.wait_for_timeout(500)
            page.screenshot(path=str(shots / "milestone-2-dashboard.png"), full_page=True)
            assert not report["page_errors"], report["page_errors"]
            assert not report["console_errors"], report["console_errors"]
            record("operational dashboard has no console or page errors")
            report["demonstration_scenario_id"] = exported["id"]
            browser.close()
        report["passed"] = True
    except Exception as error:
        report["passed"] = False
        report["error"] = str(error)
        raise
    finally:
        report["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
