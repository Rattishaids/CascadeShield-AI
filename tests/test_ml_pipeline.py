"""Explicit unit fixtures verify ML contracts; these are never research examples."""
import copy
import json
import tempfile
import unittest
from pathlib import Path

from ml.features import FEATURES, FEATURE_HASH, FEATURE_VERSION, REQUEST_VERSION, MODEL_VERSION, feature_vector, strip_labels
from ml.data import validate_frame, load_corpus, reconstruct_labels, future_impact


def fixture(clock=0.):
    node_features = {"TRUCK": ["remaining_distance_m"], "DRIVER": ["available"], "DOCK": ["service_sec"],
                     "DELIVERY": ["deadline_sec"], "WAREHOUSE": ["dock_capacity"]}
    graph = {"schemaVersion": "cascadeshield.graph-snapshot/1.0", "simulationTime": {"clockSec": clock},
             "networkId": "TEST_FIXTURE_ONLY", "runId": "unit-run", "scenarioId": "unit-scenario", "randomSeed": 1001,
             "featureSchemas": {kind: [{"name": name, "dtype": "float64", "unit": "unit", "provenance": "SIMULATED_INPUT"} for name in names] for kind, names in node_features.items()},
             "nodes": [{"id": kind+":1", "type": kind, "resourceId": "1", "features": {names[0]: 1.},
                        "availableMask": {names[0]: True}, "provenance": "SIMULATED"} for kind, names in node_features.items()],
             "edges": [{"id": "test-edge", "source": "TRUCK:1", "target": "DRIVER:1", "type": "ASSIGNED_DRIVER",
                        "weight": .8, "validFromSec": 0, "validUntilSec": 1000, "features": {}, "provenance": "SIMULATED"}],
             "predictions": [], "realizedLabels": [],
             "provenance": {"geography": "REAL_GEOGRAPHIC", "operations": "SIMULATED", "outcomeLabels": "SIMULATED_OUTCOME"}}
    values = {name: 0. for name in FEATURES}
    values.update(clock_sec=clock, remaining_distance_m=1000., max_speed_kph=36., current_speed_kph=36.,
                  driver_available=1., capacity_kg=2000., load_kg=100., deadline_slack_sec=500.,
                  distance_speed_remaining_sec=100., rule_road_remaining_sec=100., rule_eta_known=1.)
    return {"schemaVersion": "cascadeshield.ml-frame/1.0", "featureSchemaVersion": FEATURE_VERSION,
            "featureSchemaHash": FEATURE_HASH, "clockSec": clock, "stateFingerprint": "fixture-fingerprint",
            "networkId": "TEST_FIXTURE_ONLY", "graphSha256": "a"*64, "graphSnapshot": graph,
            "trucks": [{"truckId": "1", "features": values, "baseline": {}, "etaEligible": True, "deliveryEligible": True}]}


def scenario():
    return {"schemaVersion": "cascadeshield.ml-corpus/1.0", "scenarioId": "unit-scenario", "seed": 1001,
            "split": "train", "family": "EXPLICIT_UNIT_FIXTURE_ONLY", "inputFingerprint": "unit-input",
            "horizonSec": 1000., "frames": [fixture()], "provenance": "SIMULATED_RESEARCH_EXPERIMENT",
            "outcomes": {"trucks": [{"id": "1", "arrivalSec": 300.}],
                         "deliveries": [{"id": "D", "truckId": "1", "deliveredAtSec": 500., "deadlineSec": 400.}],
                         "realizedImpacts": [{"code": "DOCK_QUEUE", "startSec": 120., "resourceIds": ["DOCK:1"],
                                              "truckIds": ["1"], "predicted": False}]}}


class MlDataContractTests(unittest.TestCase):
    def test_exact_versioned_feature_vocabulary(self):
        self.assertEqual(len(FEATURES), 32)
        self.assertEqual(FEATURE_HASH, "bfb419c7a4fde46112e53aa83a8131e2f1e33526d4d85dda51374de1a828c4d4")
        self.assertEqual(len(feature_vector(fixture()["trucks"][0]["features"])), 32)

    def test_extra_outcome_column_and_nonfinite_input_rejected(self):
        for value in ({**fixture()["trucks"][0]["features"], "delivered_at_sec": 700.},
                      {**fixture()["trucks"][0]["features"], "clock_sec": float("inf")}):
            with self.assertRaises(ValueError): feature_vector(value)

    def test_missing_values_preserved_as_nan(self):
        import math
        values = fixture()["trucks"][0]["features"]; values["driver_available"] = None
        self.assertTrue(math.isnan(feature_vector(values)[FEATURES.index("driver_available")]))

    def test_asof_clock_and_future_realized_labels_rejected(self):
        frame = fixture(); frame["graphSnapshot"]["simulationTime"]["clockSec"] = 1.
        with self.assertRaises(ValueError): validate_frame(frame)
        frame = fixture(); frame["graphSnapshot"]["realizedLabels"] = [{"nodeId": "TRUCK:1", "target": "arrival_sec", "value": 10., "atClockSec": 10., "provenance": "SIMULATED_OUTCOME"}]
        with self.assertRaises(ValueError): validate_frame(frame)

    def test_labels_reconstructed_from_later_authoritative_outcomes(self):
        s = scenario(); labels = reconstruct_labels(s, s["frames"][0], s["frames"][0]["trucks"][0])
        self.assertEqual(labels["remainingArrivalSec"], 300.)
        self.assertEqual(labels["deliveryLate"], 1); self.assertEqual(labels["futureImpact"], 1)
        self.assertNotIn("labels", s["frames"][0]["trucks"][0])

    def test_targets_already_realized_are_not_prediction_examples(self):
        s = scenario(); frame = fixture(600.)
        labels = reconstruct_labels(s, frame, frame["trucks"][0])
        self.assertIsNone(labels["remainingArrivalSec"]); self.assertIsNone(labels["deliveryLate"])

    def test_unfinished_outcomes_remain_censored_not_fabricated(self):
        s = scenario(); s["outcomes"]["trucks"][0]["arrivalSec"] = -1.; s["outcomes"]["deliveries"][0]["deliveredAtSec"] = -1.
        labels = reconstruct_labels(s, s["frames"][0], s["frames"][0]["trucks"][0])
        self.assertIsNone(labels["remainingArrivalSec"]); self.assertIsNone(labels["deliveryLate"])
        self.assertTrue(labels["arrivalCensored"]); self.assertTrue(labels["deliveryCensored"])

    def test_impact_onset_strict_cutoff_and_success_exclusion(self):
        s = scenario(); frame = fixture(120.)
        self.assertEqual(future_impact(s, frame, "TRUCK:1"), 0)
        s["outcomes"]["realizedImpacts"][0]["code"] = "DELIVERY_COMPLETED"
        self.assertEqual(future_impact(s, fixture(), "TRUCK:1"), 0)

    def test_incomplete_future_windows_are_masked_even_if_an_event_was_seen(self):
        s = scenario(); s["outcomes"].update(finalClockSec=150., completed=False)
        self.assertIsNone(future_impact(s, fixture(), "TRUCK:1"))
        self.assertIsNone(future_impact(s, fixture(), "WAREHOUSE:1"))
        s["outcomes"]["completed"] = True
        self.assertEqual(future_impact(s, fixture(), "TRUCK:1"), 1)
        self.assertEqual(future_impact(s, fixture(), "WAREHOUSE:1"), 0)

    def test_final_split_cannot_be_opened_during_training(self):
        s = scenario(); s["split"] = "final"
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/"unit.jsonl"; path.write_text(json.dumps(s)+"\n", encoding="utf-8")
            with self.assertRaises(ValueError): load_corpus(path, {"train", "validation", "calibration"})

    def test_published_benchmark_seeds_cannot_be_final_assessment(self):
        s = scenario(); s["seed"] = 44
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/"unit.jsonl"; path.write_text(json.dumps(s)+"\n", encoding="utf-8")
            with self.assertRaises(ValueError): load_corpus(path)

    def test_inference_strips_all_labels_and_rejects_later_targets(self):
        frame = fixture(); frame["nodeLabels"] = [{"nodeId": "TRUCK:1", "futureImpact": 1}]
        frame["trucks"][0]["labels"] = {"deliveryLate": 1}
        with self.assertRaises(ValueError): validate_frame(frame, inference=True)
        clean = strip_labels(frame); validate_frame(clean, inference=True)
        self.assertNotIn("nodeLabels", clean); self.assertNotIn("labels", clean["trucks"][0])

    def test_private_future_schedules_are_rejected_even_if_not_model_features(self):
        for key in ("futureSchedule", "exogenousSchedule", "outcomes"):
            frame = fixture(); frame["extra"] = {key: [{"clockSec": 1000.}]}
            with self.assertRaises(ValueError): validate_frame(frame, inference=True)

    def test_stale_or_unapproved_audit_blocks_all_fitting(self):
        from ml.training import require_training_audit, sha, ROOT, AUDITED_SOURCES
        with tempfile.TemporaryDirectory() as d:
            corpus = Path(d); protocol = corpus/"protocol.json"; protocol.write_text("{}")
            graph_sha = sha(ROOT/"data/processed/chennai_osm/road_graph.json")
            declaration = corpus/"generation_manifest.json"; declaration.write_text(json.dumps({"graphSha256": graph_sha}))
            schema = corpus/"feature_schema.json"; schema.write_text("{}")
            source_hashes = {}
            for split in ("train", "validation", "calibration"):
                source = corpus/f"{split}.jsonl"; source.write_text("EXPLICIT_UNIT_FIXTURE_ONLY")
                source_hashes[split] = sha(source)
            audit = corpus/"audit.json"
            content = {"trainingAuthorizedAfterAudit": False, "protocolSha256": sha(protocol),
                       "generationManifestSha256": sha(declaration), "graphSha256": graph_sha,
                       "featureSchemaHash": FEATURE_HASH, "featureSchemaFileSha256": sha(schema),
                       "auditImplementationSha256": sha(ROOT/"scripts/audit_milestone4_leakage.py"),
                       "reviewedSourceSha256": {name: sha(ROOT/name) for name in AUDITED_SOURCES},
                       "developmentAudit": {"passed": True, "strictAuthoritativeTargetParity": True,
                                            "asOfInferenceProjectionValidated": True, "finalOutcomesOpened": False,
                                            "sourceCorpusSha256": source_hashes}}
            audit.write_text(json.dumps(content))
            with self.assertRaises(ValueError): require_training_audit(corpus, protocol, audit)
            content["trainingAuthorizedAfterAudit"] = True; audit.write_text(json.dumps(content))
            self.assertEqual(require_training_audit(corpus, protocol, audit)["sha256"], sha(audit))
            protocol.write_text('{"changed":true}')
            with self.assertRaises(ValueError): require_training_audit(corpus, protocol, audit)
            protocol.write_text("{}")
            content["developmentAudit"]["passed"] = False; audit.write_text(json.dumps(content))
            with self.assertRaises(ValueError): require_training_audit(corpus, protocol, audit)
            content["developmentAudit"]["passed"] = True; audit.write_text(json.dumps(content))
            (corpus/"train.jsonl").write_text("ALTERED_UNIT_FIXTURE")
            with self.assertRaises(ValueError): require_training_audit(corpus, protocol, audit)


if __name__ == "__main__": unittest.main()
