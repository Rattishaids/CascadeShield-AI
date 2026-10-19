"""Execute M2 HTTP/PostGIS checks on real Chennai roads with simulated resources.

Resets only simulator resources/fleet. Never runs alongside an operator session.
Results are engineering evidence, not field observations or ML effectiveness.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import subprocess
import time

from test_simulator_integration import Harness, HttpError, ROOT, point, require, first_difference


class OperationalHarness(Harness):
    def rejected(self, status, path, body=None, method=None):
        try:
            self.request(path, body, method)
        except HttpError as error:
            require(error.status == status, f"Expected {status}, got {error}")
            return error.body
        raise AssertionError(f"{path} unexpectedly accepted a restricted/invalid request")

    def configure(self):
        state = self.control("RESET")
        for truck in state["trucks"]:
            self.request("/trucks/" + truck["id"], method="DELETE")
        ops = self.request("/operations")
        for kind in ("deliveries", "docks", "drivers", "warehouses"):
            for resource in ops[kind]:
                self.request(f"/operations/{kind}/{resource['id']}", method="DELETE")
        pair = self.pairs[0]
        route = self.request("/routes/preview", {"start": point(pair["start"]), "destination": point(pair["destination"]), "waypoints": [], "maxSpeedKph": 40})
        self.baseline = math.ceil(route["baseTravelSec"] * 10) / 10
        self.physical = self.edges[route["edgeIds"][0]]["physicalId"]
        for truck_id, departure in (("OPS-A", 0), ("OPS-B", 200)):
            self.request("/trucks", {"id": truck_id, "name": truck_id + " simulated freight", "start": point(pair["start"]), "destination": point(pair["destination"]), "waypoints": [], "maxSpeedKph": 40, "capacityKg": 1000, "loadKg": 500, "driverName": "Simulated", "priority": "NORMAL", "departureSec": departure, "deadlineSec": 4000})
        destination = self.truck(self.state(), "OPS-A")["destination"]
        self.request("/operations/warehouses", {"id": "OPS-W", "name": "Simulated receiving facility", "location": destination, "dockCapacity": 1})
        self.request("/operations/docks", {"id": "OPS-D", "name": "Simulated shared dock", "warehouseId": "OPS-W", "serviceSec": 300, "openFromSec": 0, "openUntilSec": 10000})
        for suffix in ("A", "B"):
            self.request("/operations/drivers", {"id": "OPS-DR" + suffix, "name": "Simulated driver " + suffix, "available": True, "shiftStartSec": 0, "shiftEndSec": 10000})
            self.request("/operations/deliveries", {"id": "OPS-L" + suffix, "name": "Simulated delivery " + suffix, "warehouseId": "OPS-W", "loadKg": 200, "deadlineSec": self.baseline + (600 + 30 if suffix == "B" else 600), "priority": "HIGH" if suffix == "B" else "NORMAL"})
            start = self.baseline + (300 if suffix == "B" else 0)
            self.request("/operations/assignments", {"truckId": "OPS-" + suffix, "driverId": "OPS-DR" + suffix, "dockId": "OPS-D", "deliveryIds": ["OPS-L" + suffix], "reservationStartSec": start, "reservationEndSec": start + 300})
        state = self.state()
        require(len(state["operations"]["assignments"]) == 2, "Validated dependencies missing")
        require(all(resource["provenance"] == "SIMULATED" for kind in ("warehouses", "docks", "drivers", "deliveries") for resource in state["operations"][kind]), "Manual resources lost simulated provenance")
        self.on_roads(state)
        self.export_dir = ROOT / "reports/milestone_2_exports" / state["runId"]
        self.export_dir.mkdir(parents=True, exist_ok=False)
        self.report["export_directory"] = self.export_dir.relative_to(ROOT).as_posix()
        return {"road_baseline_sec": self.baseline, "road_physical_id": self.physical, "resources": 6, "assignments": 2, "network": state["networkId"]}

    def input_guards(self):
        before = self.state()
        self.rejected(400, "/operations/docks", {"id": "EXCESS", "warehouseId": "OPS-W", "serviceSec": 300, "openFromSec": 0, "openUntilSec": 10000})
        self.rejected(400, "/operations/deliveries", {"id": "BAD", "warehouseId": "OPS-W", "loadKg": 1, "deadlineSec": 50})
        self.rejected(409, "/operations/drivers/OPS-DRA", method="DELETE")
        self.rejected(400, "/operations/drivers/OPS-DRB/availability", {}, "PATCH")
        self.rejected(400, "/operations/assignments", {"truckId": "OPS-A", "driverId": "OPS-DRA", "dockId": "OPS-D", "deliveryIds": ["OPS-LA"], "reservationStartSec": 0, "reservationEndSec": 1})
        require(self.state() == before, "Rejected resource requests mutated authoritative state")
        return {"rejected": ["dock capacity", "missing priority", "referenced driver removal", "short reservation"], "unchanged_state": True}

    def cascade_forecast(self):
        state = self.request("/incidents", {"type": "CLOSURE", "physicalId": self.physical, "severity": 1, "durationSec": 90, "startSec": 0})
        self.incident_id = state["incidents"][-1]["id"]
        ops = state["operations"]
        require(not ops["realizedImpacts"], "Forecast fabricated realized outcomes")
        require(any(i["code"] == "DOCK_OVERLAP" and "OPS-B" in i["truckIds"] for i in ops["predictedImpacts"]), "A road delay did not recalculate dependent dock queue")
        require(any(i["code"] == "DELIVERY_DEADLINE" and "DELIVERY:OPS-LB" in i["resourceIds"] for i in ops["predictedImpacts"]), "Dependent delivery deadline exposure missing")
        graph = self.request("/operations/graph")
        require({n["type"] for n in graph["nodes"]} == {"TRUCK", "DRIVER", "DOCK", "DELIVERY", "WAREHOUSE"}, "Heterogeneous resource types missing")
        require(any(e["source"] == "DOCK:OPS-D" and e["target"] == "TRUCK:OPS-B" for e in graph["edges"]), "Directed shared-dock conflict edge missing")
        cascade = self.request("/operations/cascade")
        require(all(0 <= risk["score"] <= 1 for risk in cascade["nodeRisks"]), "Unbounded cascade score")
        require("TRUCK:OPS-B" in cascade["affectedNodeIds"], "Indirect truck missing from affected subgraph")
        inspected = self.request("/incidents/" + self.incident_id)
        require(inspected["directTruckIds"] == ["OPS-A"] and inspected["affectedResources"], "Incident inspection did not distinguish direct and dependency impacts")
        affected = self.request("/operations/affected?incidentId=" + self.incident_id)
        require(any(node["id"] == "TRUCK:OPS-B" for node in affected["nodes"]), "Affected-resource tool omitted indirectly exposed truck")
        return {"direct_trucks": inspected["directTruckIds"], "affected_node_ids": cascade["affectedNodeIds"], "threshold": cascade["threshold"], "predicted_impacts": ops["predictedImpacts"], "calibrated": False}

    def ai_and_approval(self):
        before = self.state()
        predicted = self.request("/ai/predict", {})
        require(predicted["source"]["provider"] == "RULE_BASED_FALLBACK" and not predicted["source"]["calibrated"], "Provider provenance incorrect")
        batch = self.request("/ai/candidates/OPS-A", {})
        candidate = next(c for c in batch["candidates"] if c["action"] == "CONTINUE")
        evaluation = self.request("/ai/counterfactual", candidate)
        validation = self.request("/ai/validate", candidate)
        explanation = self.request("/ai/explain", candidate)
        require(validation["valid"] and explanation["facts"]["stateFingerprint"] == candidate["stateFingerprint"], "Typed evaluation/validation/explanation disagree")
        require("beforeGraphRisk" in evaluation and "afterGraphRisk" in evaluation, "Counterfactual graph risk not recomputed")
        require(self.state() == before, "Read-only AI tools mutated real simulation state")
        forged = {**candidate, "source": {**candidate["source"], "calibrated": True}}
        self.rejected(400, "/ai/counterfactual", forged)
        approval = self.request("/ai/approvals", candidate)
        self.rejected(409, f"/ai/approvals/{approval['id']}/execute", {})
        self.rejected(400, f"/ai/approvals/{approval['id']}/approve", {"approvedBy": ""})
        require(self.state() == before, "Proposal/admin audit invalidated frozen state")
        approved = self.request(f"/ai/approvals/{approval['id']}/approve", {"approvedBy": "integration-operator"})
        require(approved["status"] == "APPROVED", "Approval transition missing")
        actual = self.request(f"/ai/approvals/{approval['id']}/execute", {})
        require(self.truck(actual, "OPS-A")["position"] == self.truck(before, "OPS-A")["position"], "Approved action teleported truck")
        self.rejected(409, f"/ai/approvals/{approval['id']}/execute", {})
        candidate = next(c for c in self.request("/ai/candidates/OPS-A", {})["candidates"] if c["action"] == "CONTINUE")
        stale = self.request("/ai/approvals", candidate)
        self.request(f"/ai/approvals/{stale['id']}/approve", {"approvedBy": "integration-operator"})
        self.control("STEP", stepSec=.1)
        unchanged = self.state()
        self.rejected(409, f"/ai/approvals/{stale['id']}/execute", {})
        self.rejected(409, "/ai/validate", candidate)
        require(self.state() == unchanged, "Stale approval mutated state")
        return {"proposal_id": approval["id"], "executed_once": True, "unapproved_rejected": True, "stale_rejected": True, "forged_provenance_rejected": True, "read_tools_do_not_mutate": True}

    def availability(self):
        state = self.request("/operations/drivers/OPS-DRB/availability", {"available": False}, "PATCH")
        require(not self.truck(state, "OPS-B")["etaKnown"], "Unavailable driver received invented arrival ETA")
        prediction = self.request("/ai/predict", {})
        require(next(t for t in prediction["trucks"] if t["truckId"] == "OPS-B")["estimatedArrivalSec"] is None, "Unknown arrival must be nullable")
        self.request("/operations/drivers/OPS-DRB/availability", {"available": True}, "PATCH")
        self.rejected(409, "/operations/drivers", {"id": "LATE-EDIT", "available": True, "shiftStartSec": 0, "shiftEndSec": 10000})
        return {"runtime_availability_recorded": True, "unknown_eta_masked": True, "configuration_locked_after_start": True}

    def restart(self):
        before = self.state()
        approvals = self.request("/ai/approvals")
        result = subprocess.run(["docker", "compose", "-f", str(ROOT / "simulator/compose.yaml"), "restart", "backend"], capture_output=True, text=True, timeout=120)
        require(result.returncode == 0, result.stderr)
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            try:
                if self.request("/health", timeout=5)["status"] == "UP":
                    break
            except Exception:
                pass
            time.sleep(.5)
        else:
            raise AssertionError("Backend did not recover after actual restart")
        after = self.state()
        require(before == after, "Restart changed persisted paused operational state: " + first_difference(before, after))
        require(self.request("/ai/approvals") == approvals, "Restart lost approval records")
        time.sleep(.3)
        require(self.state()["clockSec"] == before["clockSec"], "Restart advanced paused clock")
        return {"actual_container_restart": True, "clock_sec": after["clockSec"], "resources_assignments_and_approvals_preserved": True}

    def actual_queue_and_snapshot(self):
        state = self.control("STEP", stepSec=999.9)
        require(state["clockSec"] == 1000, "Queue observation clock mismatch")
        ops = state["operations"]
        a = next(a for a in ops["assignments"] if a["truckId"] == "OPS-A")
        b = next(a for a in ops["assignments"] if a["truckId"] == "OPS-B")
        require(a["status"] == "UNLOADING" and b["status"] == "QUEUED", "Expected actual shared dock occupancy and queue")
        require(any(i["code"] == "DOCK_QUEUE" for i in ops["realizedImpacts"]), "Actual queue outcome missing")
        risk = next(r for r in ops["cascade"]["nodeRisks"] if r["nodeId"] == "TRUCK:OPS-B")
        require("INCIDENT:" + self.incident_id in risk["causeIds"], "Encountered road delay attribution vanished before downstream consequence resolved")
        require(self.truck(state, "OPS-A")["arrivalSec"] >= 0 and not self.truck(state, "OPS-A")["affectedIncidentIds"], "Arrived truck retained direct road-risk seeds")
        scenario = self.request("/scenarios", {"name": "M2 real Chennai shared-dock cascade (simulated)"})
        snapshot = self.request("/ai/graph-snapshot")
        require(snapshot["scenarioId"] == scenario["id"] and snapshot["randomSeed"] == 0, "Snapshot scenario/seed missing")
        require(snapshot["provenance"]["operations"] == "SIMULATED", "Snapshot operational provenance missing")
        require(not any(label["target"] == "actual_dock_end_sec" for label in snapshot["realizedLabels"]), "Scheduled future completion exported as realized label")
        require(all(label["atClockSec"] == 1000 for label in snapshot["realizedLabels"]), "Label observation clock mismatch")
        stored = self.request("/ai/graph-snapshots", {})
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT snapshot FROM cascadeshield_sim.graph_snapshots WHERE id=%s", (stored["id"],))
            require(cursor.fetchone()[0] == snapshot, "Persisted snapshot differs from exported state")
        directory = self.export_dir
        directory.mkdir(exist_ok=True)
        (directory / "queue_snapshot.json").write_text(json.dumps(snapshot, indent=2) + "\n", encoding="utf-8")
        return {"clock_sec": 1000, "a_actual_dock_start_sec": a["actualDockStartSec"], "a_scheduled_dock_end_sec": a["actualDockEndSec"], "b_actual_queue_sec_so_far": b["queueSec"], "incident_cause_retained": True, "snapshot_id": stored["id"], "future_labels_excluded": True}

    def completed_and_replay(self):
        state = self.control("STEP", stepSec=500)
        require(state["status"] == "COMPLETED", "Assigned dock deliveries failed to complete")
        ops = state["operations"]
        deliveries = {d["id"]: d for d in ops["deliveries"]}
        require(deliveries["OPS-LB"]["lateSec"] > 0, "Dependent lateness was not realized")
        require(ops["kpis"]["delivered"] == 2 and ops["kpis"]["lateDeliveries"] == 1, "Operational KPI disagrees with actual deliveries")
        require(math.isclose(ops["kpis"]["deliveryDelaySec"], sum(d["lateSec"] for d in deliveries.values()), abs_tol=1e-8), "Lateness KPI not derived from actual records")
        require(all(not i["predicted"] and i["provenance"] == "SIMULATED_OUTCOME" for i in ops["realizedImpacts"]), "Realized impacts mislabeled")
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT count(*) FROM cascadeshield_sim.operational_resources WHERE run_id=%s", (state["runId"],))
            require(cursor.fetchone()[0] == 6, "Resource projections missing")
            cursor.execute("SELECT count(*) FROM cascadeshield_sim.operational_assignments WHERE run_id=%s", (state["runId"],))
            require(cursor.fetchone()[0] == 2, "Assignment projections missing")
        saved = self.request("/scenarios", {"name": "M2 completed deterministic cascade engineering test"})
        snapshot = self.request("/ai/graph-snapshot")
        require(any(label["target"] == "delivery_lateness_sec" and label["value"] > 0 for label in snapshot["realizedLabels"]), "Measurable completed labels absent")
        directory = self.export_dir
        (directory / "completed_snapshot.json").write_text(json.dumps(snapshot, indent=2) + "\n", encoding="utf-8")
        export = self.request("/scenarios/" + saved["id"] + "/export")
        (directory / "cascade_scenario.json").write_text(json.dumps(export, indent=2) + "\n", encoding="utf-8")
        self.request("/scenarios/" + saved["id"] + "/replay", {})
        replay = self.control("STEP", stepSec=state["clockSec"])
        require(self.replay_snapshot(replay) == self.replay_snapshot(state), "Operational scenario changed road state during replay")
        require(replay["operations"] == ops, "Operational replay mismatch: " + first_difference(ops, replay["operations"]))
        self.rejected(409, "/operations/drivers/OPS-DRA/availability", {"available": False}, "PATCH")
        return {"scenario_id": saved["id"], "actual_clock_sec": state["clockSec"], "deliveries": list(deliveries.values()), "operational_kpis": ops["kpis"], "exact_operational_replay": True}

    def legacy_version_one(self):
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT id FROM cascadeshield_sim.scenarios WHERE configuration->>'version'='1' ORDER BY created_at LIMIT 1")
            original = cursor.fetchone()
        require(original is not None, "An original Milestone 1 scenario is required for the legacy compatibility check")
        scenario_id = str(original[0])
        before = self.request("/scenarios/" + scenario_id + "/export")
        require("operations" not in before["configuration"], "Selected scenario is not the preserved original contract")
        state = self.request("/scenarios/" + scenario_id + "/replay", {})
        require(state["scenarioId"] == scenario_id and state["clockSec"] == 0, "Legacy scenario identity or clock changed")
        require(all(not state["operations"][kind] for kind in ("warehouses", "docks", "drivers", "deliveries", "assignments")), "Legacy replay invented operational resources")
        state = self.control("STEP", stepSec=.1)
        require(state["clockSec"] == .1 and len(state["trucks"]) == len(before["configuration"]["trucks"]), "Legacy movement contract failed")
        require(self.request("/scenarios/" + scenario_id + "/export") == before, "Replay altered original scenario configuration")
        return {"original_scenario_id": scenario_id, "configuration_version": 1, "original_saved_configuration_unchanged": True, "no_resources_invented": True}

    def run(self):
        baseline = self.research_snapshot()
        self.check("real_road_manual_resource_configuration", self.configure)
        self.check("resource_assignment_validation_preserves_state", self.input_guards)
        self.check("road_delay_forecasts_indirect_dock_delivery_cascade", self.cascade_forecast)
        self.check("typed_ai_tools_approval_and_stale_execution_guards", self.ai_and_approval)
        self.check("driver_availability_and_unknown_arrival_contract", self.availability)
        self.check("actual_restart_preserves_operational_state_and_approvals", self.restart)
        self.check("actual_queue_incident_history_and_versioned_snapshot", self.actual_queue_and_snapshot)
        self.check("realized_lateness_database_projection_and_exact_replay", self.completed_and_replay)
        self.check("original_version_one_scenario_remains_replayable", self.legacy_version_one)
        self.check("historical_research_imports_preserved", lambda: self.verify_research_unchanged(baseline))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8080/api")
    parser.add_argument("--report", type=Path, default=ROOT / "reports/milestone_2_integration_tests.json")
    args = parser.parse_args()
    harness = OperationalHarness(args.base_url, os.environ.get("DATABASE_URL", "postgresql://cascadeshield:cascadeshield@127.0.0.1:55432/cascadeshield"), ROOT / "data/processed/chennai_osm/road_graph.json")
    try:
        harness.run()
        harness.report["passed"] = True
    except Exception as error:
        harness.report["passed"] = False
        harness.report["failure"] = str(error)
        raise
    finally:
        harness.report["completed_at_utc"] = datetime.now(timezone.utc).isoformat()
        harness.report["passed_checks"] = sum(check["passed"] for check in harness.report["checks"])
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(harness.report, indent=2) + "\n", encoding="utf-8")
        harness.connection.close()


if __name__ == "__main__":
    main()
