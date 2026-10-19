"""Explicit unit fixtures test conversion contracts; they are not research datasets."""
import copy
import importlib.util
import math
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "convert_graph_snapshot.py"
SPEC = importlib.util.spec_from_file_location("convert_graph_snapshot", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def fixture():
    return {
        "schemaVersion": MODULE.SNAPSHOT_VERSION,
        "simulationTime": {"clockSec": 20.0, "initialClockIso": "2026-10-09T09:00:00+05:30", "simulationTimestamp": "2026-10-09T09:00:20+05:30"},
        "networkId": "TEST_FIXTURE_ONLY", "runId": "administrative-test-id", "scenarioId": None, "randomSeed": 0,
        "provenance": {"geography": "REAL_GEOGRAPHIC", "operations": "SIMULATED", "predictions": "SIMULATED_PREDICTION", "outcomeLabels": "SIMULATED_OUTCOME", "trainingStatus": "NO_TRAINED_MODEL"},
        "featureSchemas": {"TRUCK": [{"name": "load_kg", "dtype": "float64", "unit": "kg", "provenance": "SIMULATED_INPUT"}], "DRIVER": [{"name": "duty_sec", "dtype": "float64", "unit": "s", "provenance": "SIMULATED_INPUT"}]},
        "nodes": [
            {"id": "TRUCK:T1", "type": "TRUCK", "resourceId": "T1", "features": {"load_kg": 0}, "availableMask": {"load_kg": True}, "provenance": "SIMULATED"},
            {"id": "DRIVER:D1", "type": "DRIVER", "resourceId": "D1", "features": {"duty_sec": None}, "availableMask": {"duty_sec": False}, "provenance": "SIMULATED"},
        ],
        "edges": [{"id": "E1", "source": "TRUCK:T1", "target": "DRIVER:D1", "type": "ASSIGNED_DRIVER", "weight": .8, "validFromSec": 0, "validUntilSec": 100, "features": {}, "provenance": "SIMULATED"}],
        "predictions": [{"nodeId": "TRUCK:T1", "target": "estimated_arrival_sec", "value": 30, "atClockSec": 20, "provenance": "SIMULATED_PREDICTION", "source": "RULE_BASED_DIRECT_TRAVEL"}],
        "realizedLabels": [],
    }


class GraphSnapshotConverterTests(unittest.TestCase):
    def test_missing_values_use_mask_and_zero_is_preserved_as_available(self):
        pack = MODULE.convert_snapshot(fixture())
        self.assertEqual(pack["node_stores"]["TRUCK"]["x"], [[0.0]])
        self.assertEqual(pack["node_stores"]["TRUCK"]["x_mask"], [[True]])
        self.assertEqual(pack["node_stores"]["DRIVER"]["x"], [[0.0]])
        self.assertEqual(pack["node_stores"]["DRIVER"]["x_mask"], [[False]])

    def test_directed_relation_indices_preserve_source_and_target_types(self):
        pack = MODULE.convert_snapshot(fixture())
        edge = pack["edge_stores"][0]
        self.assertEqual(edge["edge_type"], ["TRUCK", "ASSIGNED_DRIVER", "DRIVER"])
        self.assertEqual(edge["edge_index"], [[0], [0]])
        self.assertEqual(edge["edge_attr"], [[.8, 0, 100]])

    def test_no_outcomes_are_invented_and_predictions_remain_separate(self):
        pack = MODULE.convert_snapshot(fixture())
        self.assertEqual(pack["realized_labels"], [])
        self.assertEqual(len(pack["predictions"]), 1)
        self.assertNotIn("estimated_arrival_sec", pack["node_stores"]["TRUCK"]["feature_names"])

    def test_realized_label_retains_simulated_provenance_and_node_index(self):
        source = fixture()
        source["realizedLabels"] = [{"nodeId": "TRUCK:T1", "target": "arrival_sec", "value": 18, "atClockSec": 20, "provenance": "SIMULATED_OUTCOME", "source": "AUTHORITATIVE_SIMULATION_ENGINE"}]
        label = MODULE.convert_snapshot(source)["realized_labels"][0]
        self.assertEqual(label["node_index"], 0)
        self.assertEqual(label["provenance"], "SIMULATED_OUTCOME")

    def test_invalid_provenance_cannot_silently_be_used_as_historical_data(self):
        for location in ("node", "label", "operations"):
            source = fixture()
            if location == "node":
                source["nodes"][0]["provenance"] = "HISTORICAL_OBSERVATION"
            elif location == "label":
                source["realizedLabels"] = [{"nodeId": "TRUCK:T1", "target": "arrival_sec", "value": 18, "atClockSec": 20, "provenance": "HISTORICAL_OBSERVATION"}]
            else:
                source["provenance"]["operations"] = "REAL_FREIGHT"
            with self.subTest(location=location), self.assertRaises(ValueError):
                MODULE.convert_snapshot(source)

    def test_malformed_graph_features_and_future_labels_are_rejected(self):
        for mutation in (
            lambda s: s["nodes"][0]["features"].update(load_kg=math.nan),
            lambda s: s["nodes"][1]["availableMask"].update(duty_sec=True),
            lambda s: s["edges"][0].update(target="missing"),
            lambda s: s["edges"][0].update(weight=1.1),
            lambda s: s["predictions"][0].update(atClockSec=25),
            lambda s: s["featureSchemas"]["TRUCK"][0].update(name="arrival_sec"),
        ):
            source = fixture()
            mutation(source)
            with self.assertRaises(ValueError):
                MODULE.convert_snapshot(source)

    def test_ordering_is_deterministic_and_input_remains_unmodified(self):
        source = fixture()
        original = copy.deepcopy(source)
        expected = MODULE.convert_snapshot(source)
        self.assertEqual(source, original)
        source["nodes"].reverse()
        actual = MODULE.convert_snapshot(source)
        self.assertEqual(expected["node_stores"], actual["node_stores"])
        self.assertEqual(expected["edge_stores"], actual["edge_stores"])
        self.assertNotEqual(expected["sourceSha256"], actual["sourceSha256"])

    def test_duplicate_nodes_and_labels_are_rejected(self):
        source = fixture()
        source["nodes"].append(copy.deepcopy(source["nodes"][0]))
        with self.assertRaises(ValueError):
            MODULE.convert_snapshot(source)
        source = fixture()
        source["predictions"].append(copy.deepcopy(source["predictions"][0]))
        with self.assertRaises(ValueError):
            MODULE.convert_snapshot(source)

    def test_empty_graph_remains_convertible_without_torch(self):
        source = fixture()
        source.update(nodes=[], edges=[], predictions=[], featureSchemas={})
        pack = MODULE.convert_snapshot(source)
        self.assertEqual(pack["node_stores"], {})
        self.assertEqual(pack["edge_stores"], [])

    def test_zero_duration_dependency_interval_is_rejected(self):
        source = fixture()
        source["edges"][0].update(validFromSec=10, validUntilSec=10)
        with self.assertRaisesRegex(ValueError, "time validity"):
            MODULE.convert_snapshot(source)

    def test_realized_timestamp_must_have_occurred_by_its_observation(self):
        for target in sorted(MODULE.REALIZED_TIMESTAMP_TARGETS):
            source = fixture()
            label = {"nodeId": "TRUCK:T1", "target": target, "value": 21, "atClockSec": 20,
                     "provenance": "SIMULATED_OUTCOME", "source": "AUTHORITATIVE_SIMULATION_ENGINE"}
            source["realizedLabels"] = [label]
            with self.subTest(target=target, condition="future snapshot event"), self.assertRaises(ValueError):
                MODULE.convert_snapshot(source)
            label.update(value=18, atClockSec=17)
            with self.subTest(target=target, condition="observed before occurrence"), self.assertRaises(ValueError):
                MODULE.convert_snapshot(source)
            label.update(value=20, atClockSec=20)
            with self.subTest(target=target, condition="measurable now"):
                self.assertEqual(MODULE.convert_snapshot(source)["realized_labels"][0]["value"], 20)

    def test_realized_durations_are_not_confused_with_event_timestamps(self):
        for target in ("arrival_delay_sec", "delivery_lateness_sec"):
            source = fixture()
            source["realizedLabels"] = [{"nodeId": "TRUCK:T1", "target": target, "value": 100,
                                         "atClockSec": 20, "provenance": "SIMULATED_OUTCOME",
                                         "source": "AUTHORITATIVE_SIMULATION_ENGINE"}]
            with self.subTest(target=target):
                self.assertEqual(MODULE.convert_snapshot(source)["realized_labels"][0]["value"], 100)


if __name__ == "__main__":
    unittest.main()
