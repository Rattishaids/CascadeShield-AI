"""Small numerical unit fixtures test PyG execution; they are excluded from research data."""
import copy
import tempfile
import unittest
from pathlib import Path

import numpy as np
import torch

from ml.features import FEATURES, FEATURE_VERSION, FEATURE_HASH, REQUEST_VERSION, MODEL_VERSION
from ml.gnn import OperationalGNN, NODE_TYPES, raw_graph, fit_normalizers, tensor_graph
from ml.metrics import regression, classification, fit_calibration, calibrated, interval_radius, clustered_loss_difference
from ml.inference import ModelBundle, domain_warnings
from test_ml_pipeline import fixture, scenario


class MlGraphMetricTests(unittest.TestCase):
    def schema(self):
        f = fixture()
        return {k: list(FEATURES) if k == "TRUCK" else [v["name"] for v in f["graphSnapshot"]["featureSchemas"][k]] for k in NODE_TYPES}

    def graph(self):
        raw = raw_graph(fixture(), self.schema())
        norm = fit_normalizers([raw], self.schema())
        return tensor_graph(raw, norm)

    def test_pyg_tensors_preserve_direction_type_and_time_attributes(self):
        graph = self.graph(); s, relation, t, index, attr = graph["edges"][0]
        self.assertEqual((s, relation, t), ("TRUCK", "ASSIGNED_DRIVER", "DRIVER"))
        self.assertEqual(index.tolist(), [[0], [0]])
        self.assertAlmostEqual(float(attr[0, 0]), .8, places=6)

    def test_fitted_normalization_uses_training_only(self):
        raw = raw_graph(fixture(), self.schema()); norm = fit_normalizers([raw], self.schema())
        future = fixture(); future["trucks"][0]["features"]["remaining_distance_m"] = 1e9
        transformed = tensor_graph(raw_graph(future, self.schema()), norm)
        self.assertEqual(norm["TRUCK"]["mean"][1], 1000.)
        self.assertEqual(float(transformed["x"]["TRUCK"][0, 1]), 20.)

    def test_static_and_temporal_models_execute_real_message_passing_and_backward(self):
        for temporal in (False, True):
            model = OperationalGNN(self.schema(), hidden=8, temporal=temporal)
            out, impacts = model([self.graph()])
            self.assertEqual(tuple(out.shape), (1, 3)); self.assertGreater(float(out[0, 0]), 0.)
            (out.sum()+sum(v.sum() for v in impacts.values())).backward()
            self.assertIsNotNone(model.messages[0]["ASSIGNED_DRIVER"].transform.weight.grad)

    def test_complete_binary_label_windows_use_float_bce_targets(self):
        from ml.training import _labels, graph_loss
        s = scenario(); graph = self.graph()
        labels = _labels(s, s["frames"][0], graph, "cpu")
        self.assertEqual(labels[1].dtype, torch.float32)
        model = OperationalGNN(self.schema(), hidden=8)
        loss = graph_loss(model([graph]), labels)
        self.assertTrue(torch.isfinite(loss))
        loss.backward()

    def test_temporal_weights_cpu_save_reload_equivalence(self):
        torch.manual_seed(4001); model = OperationalGNN(self.schema(), hidden=8, temporal=True).eval()
        graph = self.graph(); expected = model([graph])[0]
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/"unit-weights.pt"; torch.save(model.state_dict(), path)
            loaded = OperationalGNN(self.schema(), hidden=8, temporal=True).eval()
            loaded.load_state_dict(torch.load(path, map_location="cpu", weights_only=True))
            self.assertTrue(torch.equal(expected, loaded([graph])[0]))

    def test_undefined_auc_and_confusion_matrix_are_explicit(self):
        result = classification([0, 0], [.1, .3])
        self.assertIsNone(result["rocAuc"]); self.assertIsNone(result["prAuc"])
        self.assertEqual(result["confusionMatrix"], [[2, 0], [0, 0]])

    def test_regression_bias_and_probability_validation(self):
        self.assertEqual(regression([1, 3], [2, 4]), {"n": 2, "mae": 1., "rmse": 1., "bias": 1.})
        with self.assertRaises(ValueError): classification([0, 1], [-.1, .5])

    def test_calibration_separate_fit_and_single_class_status(self):
        result = fit_calibration([0]*8, [.5]*8)
        self.assertIn("UNAVAILABLE", result["status"])
        result = fit_calibration([0, 1]*10, [.2, .8]*10)
        self.assertIn("PLATT", result["status"])
        self.assertTrue(np.isfinite(calibrated([0., 1.], result)).all())

    def test_residual_interval_uses_finite_sample_order_statistic(self):
        # n=20: ceil((n+1)*.9)=19, so the 19th sorted absolute residual is 18.
        result = interval_radius(np.arange(20), np.zeros(20))
        self.assertEqual(result["radiusSec"], 18.)

    def test_uncertainty_resamples_complete_seed_groups_instead_of_rows(self):
        result = clustered_loss_difference([1001]*20 + [1002]*20, [-3.]*20 + [1.]*20)
        self.assertEqual(result["clusterCount"], 2)
        self.assertEqual(result["mean"], -1.)
        self.assertEqual(result["lower"], -3.)
        self.assertEqual(result["upper"], 1.)
        self.assertIsNone(clustered_loss_difference([1001, 1001], [2., 2.])["lower"])

    def request(self):
        return {"schemaVersion": REQUEST_VERSION, "featureSchemaVersion": FEATURE_VERSION,
                "featureSchemaHash": FEATURE_HASH, "networkId": "TEST_FIXTURE_ONLY", "graphSha256": "a"*64,
                "modelId": "xgb-v1", "stateFingerprint": "fixture-fingerprint", "frame": fixture(), "history": []}

    def bundle(self):
        result = ModelBundle.__new__(ModelBundle)
        result.manifest = {"networkId": "TEST_FIXTURE_ONLY", "graphSha256": "a"*64}; result.models = {"xgb-v1": None}
        return result

    def test_inference_rejects_schema_network_and_stale_fingerprint(self):
        for key, value in (("featureSchemaHash", "wrong"), ("networkId", "wrong"), ("stateFingerprint", "stale")):
            request = self.request(); request[key] = value
            with self.assertRaises(ValueError): self.bundle().validate_request(request)

    def test_temporal_inference_cannot_read_future_or_other_scenario(self):
        request = self.request(); request["history"] = [fixture(10.)]
        with self.assertRaises(ValueError): self.bundle().validate_request(request)
        request = self.request(); old = fixture(); old["graphSnapshot"]["runId"] = "other"
        request["history"] = [old]
        with self.assertRaises(ValueError): self.bundle().validate_request(request)

    def test_inference_identifies_unvalidated_live_operational_arrangements(self):
        frame = fixture(); frame["trucks"][0]["deliveryIds"] = ["D1", "D2"]
        frame["graphSnapshot"]["edges"].append({"type": "ASSIGNED_DRIVER", "source": "TRUCK:2", "target": "DRIVER:1"})
        warnings = domain_warnings(frame, {"dataset": {"scenarioFleetSizesBySplit": {"train": [4, 8]}}})
        self.assertTrue(any("Fleet size" in w for w in warnings))
        self.assertTrue(any("Multiple deliveries" in w for w in warnings))
        self.assertTrue(any("shared driver" in w for w in warnings))


if __name__ == "__main__": unittest.main()
