"""Exercise the running milestone through HTTP and PostgreSQL, using actual OSM roads.

This test resets the local SIMULATED fleet, creates three test assignments, injects
incidents and saves/replays a test scenario. It never changes historical datasets.
Run only after the simulator API is available. Results are test evidence, not field
observations, trained-model metrics or experimental effectiveness claims.
"""
from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import math
import os
import subprocess
import time
import traceback
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import psycopg
from psycopg import sql

ROOT = Path(__file__).resolve().parents[1]


class HttpError(RuntimeError):
    def __init__(self, status: int, body: Any):
        self.status, self.body = status, body
        super().__init__(f"HTTP {status}: {body}")


def distance_m(a: list[float], b: list[float]) -> float:
    lon1, lat1, lon2, lat2 = map(math.radians, [*a, *b])
    angle = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6_371_008.8 * math.asin(min(1.0, math.sqrt(angle)))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def point(coordinates: list[float]) -> dict[str, float]:
    return {"longitude": coordinates[0], "latitude": coordinates[1]}


def first_difference(expected: Any, actual: Any, path: str = "state") -> str:
    if type(expected) is not type(actual):
        return f"{path}: expected {type(expected).__name__}, got {type(actual).__name__}"
    if isinstance(expected, dict):
        if expected.keys() != actual.keys():
            return path + ": differing keys"
        for key in expected:
            if expected[key] != actual[key]:
                return first_difference(expected[key], actual[key], path + "." + key)
    elif isinstance(expected, list):
        if len(expected) != len(actual):
            return f"{path}: expected length {len(expected)}, got {len(actual)}"
        for index, (before, after) in enumerate(zip(expected, actual)):
            if before != after:
                return first_difference(before, after, f"{path}[{index}]")
    elif expected != actual:
        return f"{path}: expected {expected!r}, got {actual!r}"
    return "No difference"


class Harness:
    def __init__(self, base_url: str, dsn: str, graph_path: Path):
        self.base_url = base_url.rstrip("/")
        self.connection = psycopg.connect(dsn, autocommit=True)
        self.graph_path = graph_path
        self.graph = json.loads(graph_path.read_text(encoding="utf-8"))
        self.edges = {edge["id"]: edge for edge in self.graph["edges"]}
        self.pairs = self.graph["metadata"]["demoPairs"][:3]
        require(len(self.pairs) == 3, "Three real route demo pairs are required")
        self.report: dict[str, Any] = {
            "started_at_utc": datetime.now(timezone.utc).isoformat(),
            "api_base_url": self.base_url,
            "data_classes": ["REAL_GEOGRAPHIC_DATA", "SIMULATED_OPERATIONS", "TEST_RESULTS"],
            "trained_ml_used": False,
            "checks": [],
        }

    def request(self, path: str, body: Any = None, method: str | None = None, timeout: float = 60) -> Any:
        payload = None if body is None else json.dumps(body, allow_nan=False).encode()
        request = urllib.request.Request(
            self.base_url + path, data=payload,
            headers={"Content-Type": "application/json"} if payload is not None else {},
            method=method or ("POST" if payload is not None else "GET"),
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read()
        except urllib.error.HTTPError as error:
            raw = error.read().decode()
            try:
                body = json.loads(raw)
            except json.JSONDecodeError:
                body = raw[:1000]
            raise HttpError(error.code, body) from error
        return json.loads(raw) if raw else None

    def control(self, action: str, **extra: float) -> dict:
        return self.request("/control", {"action": action, **extra})

    def state(self) -> dict:
        return self.request("/state")

    def truck(self, state: dict, identifier: str) -> dict:
        return next(truck for truck in state["trucks"] if truck["id"] == identifier)

    def check(self, name: str, function: Callable[[], dict | None]) -> None:
        started = time.monotonic()
        result = {"name": name}
        try:
            details = function()
            result.update(passed=True, details=details or {})
        except Exception as error:
            result.update(passed=False, error=str(error), traceback=traceback.format_exc())
            raise
        finally:
            result["duration_sec"] = round(time.monotonic() - started, 4)
            self.report["checks"].append(result)
            print(("PASS " if result["passed"] else "FAIL ") + name, flush=True)

    def research_snapshot(self) -> list[tuple]:
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT processed_path,raw_sha256,processed_sha256,row_count,table_schema,table_name FROM cascadeshield_meta.imports ORDER BY processed_path")
            imports = cursor.fetchall()
            require(len(imports) == 18, "The original 18 eligible imports must be present")
            for row in imports:
                cursor.execute(sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(row[4], row[5])))
                require(cursor.fetchone()[0] == row[3], "Historical import row count changed: " + row[0])
            return imports

    def verify_network(self) -> dict:
        network = self.request("/network")
        require(network["networkId"] == self.graph["networkId"], "API network differs from acquired OSM graph")
        roads = self.request("/network/roads")
        require(roads["type"] == "FeatureCollection" and len(roads["features"]) > 3, "Road API must provide real vector geometry")
        physical = {edge["physicalId"] for edge in self.edges.values()}
        require({feature["properties"]["physicalId"] for feature in roads["features"]} == physical, "Map roads and routing roads differ")
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT count(*), count(*) FILTER(WHERE ST_SRID(geom)<>4326 OR NOT ST_IsValid(geom)) FROM cascadeshield_sim.road_edges WHERE network_id=%s", (self.graph["networkId"],))
            count, invalid = cursor.fetchone()
            require(count == len(self.edges) and invalid == 0, "PostGIS road geometry/count mismatch")
            cursor.execute("SELECT count(*) FROM cascadeshield_sim.road_nodes WHERE network_id=%s", (self.graph["networkId"],))
            require(cursor.fetchone()[0] == len(self.graph["nodes"]), "PostGIS node count mismatch")
            cursor.execute("SELECT graph_sha256 FROM cascadeshield_sim.network_versions WHERE id=%s", (self.graph["networkId"],))
            require(cursor.fetchone()[0] == hashlib.sha256(self.graph_path.read_bytes()).hexdigest(), "Network provenance hash mismatch")
        return {"network_id": network["networkId"], "directed_edges": count, "map_roads": len(physical), "invalid_geometry_or_srid": invalid}

    def clean_fleet(self) -> None:
        state = self.control("RESET")
        require(state["status"] == "DRAFT", "RESET must return editable DRAFT state")
        for truck in state["trucks"]:
            self.request("/trucks/" + truck["id"], method="DELETE")
        require(not self.state()["trucks"], "Test starts with an empty simulated fleet")

    def spec(self, number: int) -> dict:
        pair = self.pairs[number - 1]
        return {
            "id": f"TEST-T{number:02}", "name": f"Integration truck {number}",
            "start": point(pair["start"]), "destination": point(pair["destination"]),
            "waypoints": [], "capacityKg": 1000, "loadKg": 600, "maxSpeedKph": 60,
            "driverName": f"Simulated test driver {number}", "priority": "NORMAL",
            "departureSec": 0, "deadlineSec": max(30, pair["baseTravelSeconds"] / 2),
        }

    def validate_input(self) -> dict:
        invalid = self.spec(1)
        invalid["loadKg"] = invalid["capacityKg"] + 1
        try:
            self.request("/trucks", invalid)
        except HttpError as error:
            require(400 <= error.status < 500, "Invalid load must produce a validation response")
            require(not self.state()["trucks"], "Invalid input must not mutate fleet")
            return {"capacity_violation_status": error.status}
        raise AssertionError("Load above vehicle capacity was accepted")

    def validate_route(self, route: dict) -> None:
        ids = route["edgeIds"]
        require(ids and route["distanceM"] > 0, "Route must contain directed road edges")
        require(all(identifier in self.edges for identifier in ids), "Route refers to an unknown OSM edge")
        for before, after in zip(ids, ids[1:]):
            require(self.edges[before]["to"] == self.edges[after]["from"], "Route jumps across disconnected road nodes")
            previous, following = self.edges[before], self.edges[after]
            for restriction in self.graph["restrictions"]:
                if restriction["viaNode"] != previous["to"] or restriction["fromWay"] != previous["wayId"]:
                    continue
                if restriction["type"].startswith("no_"):
                    require(following["wayId"] != restriction["toWay"], "Route violates a retained conservative no-turn restriction")
                elif restriction["type"].startswith("only_"):
                    require(following["wayId"] == restriction["toWay"], "Route violates a retained only-turn restriction")
        require(math.isclose(route["distanceM"], sum(self.edges[identifier]["lengthM"] for identifier in ids), abs_tol=0.1), "Route distance differs from its real road edges")
        geometry = route["geometry"]
        require(len(geometry) >= 2, "Route geometry missing")
        require(distance_m(geometry[0], self.edges[ids[0]]["geometry"][0]) < 0.5, "Route start geometry mismatch")
        require(distance_m(geometry[-1], self.edges[ids[-1]]["geometry"][-1]) < 0.5, "Route end geometry mismatch")

    def create_trucks(self) -> dict:
        for number in range(1, 4):
            spec = self.spec(number)
            preview = self.request("/routes/preview", {key: spec[key] for key in ("start", "destination", "waypoints", "maxSpeedKph")})
            self.validate_route(preview)
            self.request("/trucks", spec)
        state = self.state()
        require(len(state["trucks"]) == 3, "Three manually-created trucks are required")
        require(state["operationsProvenance"] == "SIMULATED", "Operational data must be explicitly simulated")
        for truck in state["trucks"]:
            self.validate_route(truck["route"])
        return {"trucks": [truck["id"] for truck in state["trucks"]], "route_lengths_m": [truck["route"]["distanceM"] for truck in state["trucks"]]}

    def freeze(self) -> dict:
        self.control("START")
        time.sleep(0.5)
        first = self.control("PAUSE")
        time.sleep(0.6)
        second = self.state()
        require(first["clockSec"] == second["clockSec"], "Pause must freeze authoritative simulation time")
        require([truck["position"] for truck in first["trucks"]] == [truck["position"] for truck in second["trucks"]], "Pause must freeze backend vehicle positions")
        return {"frozen_clock_sec": second["clockSec"]}

    def real_time_speed(self) -> dict:
        samples = []
        for speed in (1, 10):
            initial = self.control("SET_SPEED", speed=speed)
            require(initial["speed"] == speed, "Requested speed setting was not applied")
            started = time.monotonic()
            self.control("RESUME")
            time.sleep(0.8)
            final = self.control("PAUSE")
            elapsed = time.monotonic() - started
            samples.append((final["clockSec"] - initial["clockSec"]) / elapsed)
        require(samples[0] > 0 and samples[1] > samples[0] * 3, "10x setting must increase backend time rate materially")
        return {"observed_clock_seconds_per_wall_second": samples, "ratio": samples[1] / samples[0]}

    def on_roads(self, state: dict) -> None:
        with self.connection.cursor() as cursor:
            for truck in state["trucks"]:
                index = min(truck["edgeIndex"], len(truck["route"]["edgeIds"]) - 1)
                identifier = truck["route"]["edgeIds"][index]
                cursor.execute("SELECT ST_Distance(ST_SetSRID(ST_MakePoint(%s,%s),4326)::geography,geom::geography) FROM cascadeshield_sim.road_edges WHERE network_id=%s AND id=%s", (*truck["position"], state["networkId"], identifier))
                require(cursor.fetchone()[0] < 0.5, "Backend truck position is off its current real road")

    def movement(self) -> dict:
        self.control("RESET")
        before = self.state()
        after = self.control("STEP", stepSec=5)
        require(after["clockSec"] == 5, "STEP must use explicit simulation time, independent of speed setting")
        for truck in after["trucks"]:
            original = self.truck(before, truck["id"])
            travelled = truck["distanceTravelledM"] - original["distanceTravelledM"]
            require(0 < travelled <= truck["maxSpeedKph"] / 3.6 * 5 + 0.001, "Motion violates distance/speed/time bounds")
            require(distance_m(original["position"], truck["position"]) <= travelled + 0.5, "Vehicle teleported beyond distance it travelled")
        self.on_roads(after)
        return {"clock_sec": after["clockSec"], "positions_checked_with_postgis": 3}

    def inject(self, kind: str, pair_number: int, severity: float, duration: float = 600) -> tuple[dict, str]:
        before = {incident["id"] for incident in self.state()["incidents"]}
        state = self.request("/incidents", {"type": kind, "physicalId": self.pairs[pair_number - 1]["closurePhysicalId"], "severity": severity, "durationSec": duration})
        created = next(incident["id"] for incident in state["incidents"] if incident["id"] not in before)
        return state, created

    def severity(self) -> dict:
        initial = self.truck(self.state(), "TEST-T01")["etaSec"]
        mild, mild_id = self.inject("SLOWDOWN", 1, 0.2)
        mild_eta = self.truck(mild, "TEST-T01")["etaSec"]
        self.request("/incidents/" + mild_id, method="DELETE")
        severe, severe_id = self.inject("SLOWDOWN", 1, 0.85)
        severe_eta = self.truck(severe, "TEST-T01")["etaSec"]
        self.request("/incidents/" + severe_id, method="DELETE")
        require(initial < mild_eta < severe_eta, "Increasing slowdown severity must increase actual backend ETA")
        return {"base_eta_sec": initial, "severity_0_2_eta_sec": mild_eta, "severity_0_85_eta_sec": severe_eta}

    def closure(self) -> dict:
        state, self.closure_id = self.inject("CLOSURE", 1, 1)
        truck = self.truck(state, "TEST-T01")
        require(self.closure_id in truck["affectedIncidentIds"], "Closure must identify directly affected truck")
        require(truck["speedKph"] >= 0, "Truck speed must remain valid")
        physical = self.pairs[0]["closurePhysicalId"]
        edge = self.edges[self.pairs[0]["closureEdgeId"]]
        tested_directions = 0
        for start, destination in ((edge["geometry"][0], edge["geometry"][-1]), (edge["geometry"][-1], edge["geometry"][0])):
            try:
                route = self.request("/routes/preview", {"start": point(start), "destination": point(destination), "waypoints": [], "maxSpeedKph": 60})
            except HttpError as error:
                require(error.status in (400, 409, 422), "Impossible route must return a clear client error")
            else:
                self.validate_route(route)
                require(all(self.edges[identifier]["physicalId"] != physical for identifier in route["edgeIds"]), "A closed physical road remained routable in one direction")
            tested_directions += 1
        return {"incident_id": self.closure_id, "physical_id": physical, "directions_tested": tested_directions, "affected_truck": truck["id"]}

    def recommendations(self) -> dict:
        state = self.state()
        require(state["recommendations"], "Affected trucks require decision outputs")
        for truck in state["trucks"]:
            require(0 <= truck["risk"]["score"] <= 1 and truck["risk"]["source"] == "RULE_BASED", "Truck risk must be bounded and explicitly rule based")
        for recommendation in state["recommendations"]:
            require(0 <= recommendation["beforeRisk"] <= 1 and 0 <= recommendation["afterRisk"] <= 1, "Recommendation risk exceeds valid bounds")
            require(recommendation["riskSource"] == "RULE_BASED", "No trained model is available")
            require({option["action"] for option in recommendation["options"]} >= {"WAIT", "REROUTE"}, "Wait and reroute must be compared")
            require(any(option["action"] == recommendation["recommendedAction"] and option["feasible"] for option in recommendation["options"]), "Recommended action must be feasible")
            require(bool(recommendation["reason"]) and all(option["explanation"] for option in recommendation["options"]), "Explanations must come from decision output")
        return {"recommendations": len(state["recommendations"]), "risk_source": "RULE_BASED"}

    def apply(self, truck_id: str, action: str) -> dict:
        state = self.state()
        recommendation = next(item for item in state["recommendations"] if item["truckId"] == truck_id)
        require(any(option["action"] == action and option["feasible"] for option in recommendation["options"]), action + " must be feasible before approval")
        return self.request("/decisions", {"truckId": truck_id, "action": action, "recommendationId": recommendation["id"]})

    def wait(self) -> dict:
        # This road lies later in the real route: keep the incident scheduled
        # beyond the projected traversal so the truck is actually affected.
        self.inject("CLOSURE", 2, 1, duration=900)
        before = self.truck(self.state(), "TEST-T02")
        after = self.truck(self.apply("TEST-T02", "WAIT"), "TEST-T02")
        require(after["position"] == before["position"], "Approving wait must not change position")
        require(after["waitUntilSec"] > 5, "Waiting must change authoritative movement constraints")
        current = self.edges[before["route"]["edgeIds"][before["edgeIndex"]]]
        occupied = before["offsetM"] > 1e-7
        remaining = current["lengthM"] - before["offsetM"] if occupied else 0
        finish_sec = math.ceil((remaining / (min(current["speedKph"], before["maxSpeedKph"]) / 3.6) + 0.5) * 10) / 10
        require(self.state()["clockSec"] + finish_sec + 5 < after["waitUntilSec"], "Selected test edge must permit a measurable wait before incident resolves")
        stopped_state = self.control("STEP", stepSec=finish_sec)
        stopped = self.truck(stopped_state, "TEST-T02")
        require(math.isclose(stopped["distanceTravelledM"] - before["distanceTravelledM"], remaining, abs_tol=0.001), "Wait must finish only the occupied edge before holding at a safe road node")
        self.on_roads(stopped_state)
        next_state = self.control("STEP", stepSec=5)
        waiting = self.truck(next_state, "TEST-T02")
        require(waiting["position"] == stopped["position"] and waiting["distanceTravelledM"] == stopped["distanceTravelledM"], "Approved wait did not hold the truck at its next safe node")
        return {"truck": after["id"], "wait_until_sec": after["waitUntilSec"], "occupied_edge_completed_m": remaining, "stationary_for_step_sec": 5}

    def reroute(self) -> dict:
        before = self.truck(self.state(), "TEST-T01")
        after_state = self.apply("TEST-T01", "REROUTE")
        after = self.truck(after_state, "TEST-T01")
        require(after["position"] == before["position"], "Reroute approval teleported a moving truck")
        require(after["distanceTravelledM"] == before["distanceTravelledM"], "Reroute changed past travelled distance")
        require(after["reroutes"] == before["reroutes"] + 1, "Reroute must record intervention count")
        require(after["route"]["edgeIds"] != before["route"]["edgeIds"], "Reroute did not change authoritative road route")
        require(all(self.edges[identifier]["physicalId"] != self.pairs[0]["closurePhysicalId"] for identifier in after["route"]["edgeIds"][after["edgeIndex"]:]), "Rerouted remainder uses closed road")
        self.on_roads(after_state)
        return {"truck": after["id"], "reroutes": after["reroutes"], "position_preserved": True}

    def kpis_and_persistence(self) -> dict:
        state = self.control("STEP", stepSec=2400)
        self.final_state = state
        trucks, kpis = state["trucks"], state["kpis"]
        arrived = [truck for truck in trucks if truck["arrivalSec"] >= 0]
        require(len(arrived) == 3, "Test trips must complete before checking realized KPIs")
        require(kpis["totalTrucks"] == len(trucks), "Fleet count differs from backend records")
        require(kpis["arrived"] == kpis["completedTrips"] == len(arrived), "Arrival KPI mismatch")
        require(kpis["lateDeliveries"] == sum(truck["arrivalSec"] > truck["deadlineSec"] for truck in arrived), "SLA KPI differs from actual arrival records")
        require(math.isclose(kpis["totalDelaySec"], sum(max(0, truck["arrivalSec"] - truck["baselineArrivalSec"]) for truck in arrived), abs_tol=0.001), "Realized delay KPI differs from actual arrivals against initial baseline")
        require(math.isclose(kpis["distanceTravelledM"], sum(truck["distanceTravelledM"] for truck in trucks), abs_tol=0.001), "Distance KPI differs from recorded truck outputs")
        require(kpis["reroutes"] == sum(truck["reroutes"] for truck in trucks), "Reroute KPI mismatch")
        require(kpis["activeIncidents"] == sum(incident["status"] == "ACTIVE" for incident in state["incidents"]), "Active incident KPI mismatch")
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT state FROM cascadeshield_sim.current_state WHERE id=1")
            persisted = cursor.fetchone()[0]
            require(persisted["clockSec"] == state["clockSec"] and persisted["kpis"] == kpis, "PostgreSQL checkpoint disagrees with authoritative API state")
            cursor.execute("SELECT count(*) FROM cascadeshield_sim.simulation_events WHERE run_id=%s", (state["runId"],))
            require(cursor.fetchone()[0] == len(state["events"]), "Persisted audit event count differs from displayed timeline")
        self.on_roads(state)
        return {"realized_simulated_kpis": kpis, "clock_sec": state["clockSec"], "postgres_checkpoint_matches": True}

    @staticmethod
    def replay_snapshot(state: dict) -> dict:
        truck_fields = ("id", "position", "status", "edgeIndex", "offsetM", "distanceTravelledM", "remainingDistanceM", "etaSec", "arrivalSec", "reroutes", "waitUntilSec", "route", "risk", "affectedIncidentIds")
        return {"clockSec": state["clockSec"], "kpis": state["kpis"], "incidents": state["incidents"], "trucks": [{key: truck[key] for key in truck_fields} for truck in state["trucks"]]}

    def save_export(self) -> dict:
        scenario = self.request("/scenarios", {"name": "HTTP integration — simulated Chennai roads"})
        self.scenario_id = scenario["id"]
        exported = self.request("/scenarios/" + self.scenario_id + "/export")
        require(self.scenario_id in {item["id"] for item in self.request("/scenarios")}, "Saved scenario missing from API")
        require(bool(exported), "Scenario export is empty")
        require(exported["configuration"]["operationsProvenance"] == "SIMULATED", "Export must label the operational schedule as simulated")
        require(len(exported["configuration"]["trucks"]) == 3 and exported["configuration"]["commands"], "Export must retain initial assignments and actual operator command schedule")
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT network_id,configuration FROM cascadeshield_sim.scenarios WHERE id=%s", (self.scenario_id,))
            row = cursor.fetchone()
            require(row and row[0] == self.graph["networkId"] and row[1], "Scenario was not persisted with real network provenance")
        return {"scenario_id": self.scenario_id, "export_available": True, "evidence_class": "SIMULATED_OPERATIONS"}

    def replay(self) -> dict:
        expected = self.replay_snapshot(self.final_state)
        self.request("/scenarios/" + self.scenario_id + "/replay", {})
        state = self.control("STEP", stepSec=self.final_state["clockSec"])
        actual = self.replay_snapshot(state)
        require(actual == expected, "Saved assignments and command schedule did not reproduce backend state: " + first_difference(expected, actual))
        return {"scenario_id": self.scenario_id, "replayed_clock_sec": state["clockSec"], "exact_vehicle_incident_and_kpi_snapshot_match": True}

    def run(self) -> None:
        baseline = self.research_snapshot()
        self.check("real_osm_network_and_postgis", self.verify_network)
        self.clean_fleet()
        self.check("capacity_input_validation", self.validate_input)
        self.check("three_manual_trucks_connected_real_routes", self.create_trucks)
        self.check("pause_freezes_time_and_positions", self.freeze)
        self.check("speed_changes_real_backend_clock_rate", self.real_time_speed)
        self.check("backend_motion_on_connected_postgis_geometry", self.movement)
        self.check("slowdown_severity_increases_eta", self.severity)
        self.check("physical_closure_blocks_both_directions_and_identifies_truck", self.closure)
        self.check("rule_based_risk_bounds_and_feasible_explanations", self.recommendations)
        self.check("manual_wait_updates_backend_motion", self.wait)
        self.check("manual_reroute_changes_route_without_teleport", self.reroute)
        self.check("realized_kpis_timeline_and_postgresql_checkpoint", self.kpis_and_persistence)
        self.check("scenario_save_list_export_and_persistence", self.save_export)
        self.check("saved_command_sequence_replay_is_reproducible", self.replay)
        self.check("historical_research_imports_preserved", lambda: self.verify_research_unchanged(baseline))

    def verify_research_unchanged(self, baseline: list[tuple]) -> dict:
        require(self.research_snapshot() == baseline, "Research import provenance or counts changed during simulator tests")
        return {"research_tables": len(baseline), "rows": sum(row[3] for row in baseline), "preserved": True}

    def restart_persistence(self) -> dict:
        """Restart only the backend and prove paused state survived actual process loss."""
        research_before = self.research_snapshot()
        self.control("RESET")
        self.control("STEP", stepSec=17.3)
        self.inject("SLOWDOWN", 1, 0.65, duration=600)
        before = self.state()
        require(before["status"] == "PAUSED", "Restart verification must begin paused")
        scenarios_before = self.request("/scenarios")
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT count(*),max(sequence) FROM cascadeshield_sim.simulation_events WHERE run_id=%s", (before["runId"],))
            audit_before = cursor.fetchone()
        restart = subprocess.run(
            ["docker", "compose", "-f", str(ROOT / "simulator/compose.yaml"), "restart", "backend"],
            capture_output=True, text=True, timeout=120,
        )
        require(restart.returncode == 0, "Backend container restart failed: " + restart.stderr[-1000:])
        deadline = time.monotonic() + 90
        last_error = ""
        while time.monotonic() < deadline:
            try:
                health = self.request("/health", timeout=5)
                if health["status"] == "UP":
                    break
            except (urllib.error.URLError, HttpError, OSError, http.client.HTTPException) as error:
                last_error = str(error)
            time.sleep(0.5)
        else:
            raise AssertionError("Backend did not recover after restart: " + last_error)
        after = self.state()
        require(after["status"] == "PAUSED" and after["runId"] == before["runId"], "Restart must preserve paused run identity")
        require(self.replay_snapshot(after) == self.replay_snapshot(before), "Restart changed paused vehicle/incident/KPI checkpoint: " + first_difference(self.replay_snapshot(before), self.replay_snapshot(after)))
        require(after["events"] == before["events"], "Restart changed the saved event timeline")
        require(self.request("/scenarios") == scenarios_before, "Restart changed saved scenarios")
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT count(*),max(sequence) FROM cascadeshield_sim.simulation_events WHERE run_id=%s", (before["runId"],))
            require(cursor.fetchone() == audit_before, "Restart changed persisted audit events")
            cursor.execute("SELECT state FROM cascadeshield_sim.current_state WHERE id=1")
            require(cursor.fetchone()[0]["clockSec"] == before["clockSec"], "PostgreSQL restart checkpoint clock mismatch")
        time.sleep(0.6)
        frozen = self.state()
        require(frozen["clockSec"] == before["clockSec"], "Recovered paused simulation advanced without operator command")
        require(self.research_snapshot() == research_before, "Backend restart altered historical imports")
        self.on_roads(after)
        return {"paused_clock_sec": after["clockSec"], "vehicles_preserved": len(after["trucks"]), "saved_scenarios_preserved": len(scenarios_before), "audit_events_preserved": audit_before[0], "active_incidents_preserved": after["kpis"]["activeIncidents"], "actual_backend_container_restart": True, "research_imports_preserved": True}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8080/api")
    parser.add_argument("--graph", type=Path, default=ROOT / "data/processed/chennai_osm/road_graph.json")
    parser.add_argument("--report", type=Path, default=ROOT / "reports/simulator_integration_tests.json")
    parser.add_argument("--test-restart", action="store_true", help="Also restart only the Docker backend and verify actual paused-state persistence")
    parser.add_argument("--restart-only", action="store_true", help="Run the restart persistence check against an already tested local fleet, recording a separate report if --report is supplied")
    args = parser.parse_args()
    dsn = os.environ.get("DATABASE_URL", "postgresql://cascadeshield:cascadeshield@127.0.0.1:55432/cascadeshield")
    harness = Harness(args.base_url, dsn, args.graph)
    try:
        if not args.restart_only:
            harness.run()
        if args.test_restart or args.restart_only:
            harness.check("actual_backend_restart_preserves_paused_state_scenarios_and_events", harness.restart_persistence)
        harness.report["passed"] = True
    except Exception as error:
        harness.report["passed"] = False
        harness.report["failure"] = str(error)
        raise
    finally:
        harness.report["completed_at_utc"] = datetime.now(timezone.utc).isoformat()
        harness.report["passed_checks"] = sum(check["passed"] for check in harness.report["checks"])
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(harness.report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        harness.connection.close()


if __name__ == "__main__":
    main()
