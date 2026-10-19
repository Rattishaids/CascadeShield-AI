"""Small TEST_FIXTURE_ONLY values validate aggregation; never benchmark results."""
import importlib.util
from pathlib import Path
import unittest

PATH = Path(__file__).resolve().parents[1] / "scripts/benchmark_statistics.py"
SPEC = importlib.util.spec_from_file_location("benchmark_statistics", PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def row(seed, policy, value, profile="TEST_FIXTURE_ONLY"):
    result = {metric: value for metric in MODULE.METRICS}
    result.update(profile=profile, seed=seed, comparisonMode="EQUAL_ACTIONS", policyId=policy,
                  inputFingerprint=f"FIXTURE-{profile}-{seed}", provenance="SIMULATED_RESEARCH_EXPERIMENT",
                  recoveryCensored=False, unfinishedDeliveries=0, deliveryCount=2, slaViolations=int(value))
    return result


class BenchmarkStatisticsTests(unittest.TestCase):
    def test_sample_variation_is_not_population_sd(self):
        result = MODULE.describe([0, .5, 1])
        self.assertEqual(result["mean"], .5)
        self.assertEqual(result["sample_sd"], .5)
        self.assertIsNone(MODULE.describe([1])["sample_sd"])

    def test_paired_delta_uses_identical_scenarios_and_seed_clusters(self):
        rows = [row(seed, policy, value, profile) for seed in (1, 2, 3) for profile in ("FIXTURE-A", "FIXTURE-B") for policy, value in (("B1", 1), ("B4", 0))]
        result = MODULE.summarize(rows, bootstrap_samples=100)
        pair = result["paired_comparisons"][0]
        self.assertEqual(pair["paired_scenarios"], 6)
        self.assertEqual(pair["independent_seed_clusters"], 3)
        self.assertEqual(pair["mean_delta_enhanced_minus_reference"], -1)
        self.assertEqual(pair["seed_cluster_bootstrap_95_interval"], [-1, -1])

    def test_mismatched_fingerprints_and_missing_comparator_are_rejected(self):
        rows = [row(1, "B1", 1), row(1, "B4", 0)]
        rows[1]["inputFingerprint"] = "DIFFERENT"
        with self.assertRaises(ValueError): MODULE.summarize(rows)
        with self.assertRaises(ValueError): MODULE.summarize([row(1, "B1", 1), row(2, "B4", 0)])

    def test_predictions_duplicates_and_nonfinite_values_cannot_be_results(self):
        r = row(1, "B4", 0)
        r["provenance"] = "MODEL_ROLLOUT_FORECAST"
        with self.assertRaises(ValueError): MODULE.summarize([r])
        with self.assertRaises(ValueError): MODULE.summarize([row(1, "B4", 0)] * 2)
        with self.assertRaises(ValueError): MODULE.describe([float("nan")])

    def test_one_seed_does_not_claim_uncertainty_or_improvement(self):
        result = MODULE.summarize([row(1, "B1", 1), row(1, "B4", 0)])
        pair = result["paired_comparisons"][0]
        self.assertEqual(pair["seed_cluster_bootstrap_95_interval"], [None, None])
        self.assertFalse(pair["supports_lower_metric_in_this_simulated_matrix"])


if __name__ == "__main__": unittest.main()
