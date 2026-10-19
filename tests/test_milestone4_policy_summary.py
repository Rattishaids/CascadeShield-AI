"""Statistical/audit counterexamples, using unit fixtures only, never research runs."""
import unittest

from scripts.summarize_milestone4_policies import clustered_difference


class PairedPolicySummaryTests(unittest.TestCase):
    def test_pair_then_cluster_entire_seed_instead_of_bootstrapping_snapshots(self):
        expected = {"a": {"seed": 4001, "family": "one"}, "b": {"seed": 4001, "family": "two"},
                    "c": {"seed": 4002, "family": "one"}, "d": {"seed": 4002, "family": "two"}}
        left = {sid: {"metric": value} for sid, value in zip(expected, [0., 2., 6., 8.])}
        right = {sid: {"metric": 0.} for sid in expected}
        uncertainty = {"bootstrapSeed": 4016, "pairedBootstrapReplicates": 2000, "confidenceLevel": .95}
        result = clustered_difference(left, right, expected, "metric", uncertainty)
        self.assertEqual(result["difference"], 4.)
        self.assertEqual(result["interval"], [1., 7.])
        self.assertEqual(result["seedMeanDifferences"], {"4001": 1., "4002": 7.})
        self.assertEqual(result["familyMeanDifferences"], {"one": 3., "two": 5.})
        self.assertEqual(result["seedClusterCount"], 2)
        self.assertEqual(result, clustered_difference(left, right, expected, "metric", uncertainty))

    def test_missing_policy_pairs_cannot_silently_reduce_final_denominator(self):
        expected = {"a": {"seed": 4001, "family": "one"}, "b": {"seed": 4002, "family": "one"}}
        with self.assertRaisesRegex(ValueError, "Missing paired scenarios"):
            clustered_difference({"a": {"metric": 1}}, {"a": {"metric": 0}}, expected, "metric", {})


if __name__ == "__main__":
    unittest.main()
