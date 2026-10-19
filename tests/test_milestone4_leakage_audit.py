"""Counterexamples for independent scenario grouping; unit fixtures are not research data."""
import copy
import unittest

from scripts.audit_milestone4_leakage import continuous_near, conservative_key, crossing_groups, descriptor, physical_configuration


def operation(split="train", service=119.9):
    return {"split": split, "scenario": {"seed": 1001, "parameters": {
        "serviceSec": service, "departureGapSec": 120., "deadlineSlackSec": 300., "contention": 0.,
        "incidentStartSec": 10., "incidentDurationSec": 240., "severity": .5, "driverRestoreSec": 300.},
        "configuration": {"seed": 1001, "trucks": [{"start": {"x": 1}, "destination": {"x": 2}}],
            "operations": {"drivers": [{"available": True}], "deliveries": [{}], "warehouses": [{}], "docks": [{}]}},
        "exogenousSchedule": []}}


class IndependentSplitAuditTests(unittest.TestCase):
    def test_seed_nonce_does_not_change_physical_configuration(self):
        a = operation(); b = copy.deepcopy(a); b["scenario"]["seed"] = 4001; b["scenario"]["configuration"]["seed"] = 4001
        self.assertEqual(physical_configuration(a), physical_configuration(b))

    def test_continuous_guard_crosses_coarse_quantization_boundary(self):
        a = operation(service=119.9); b = operation("validation", service=120.1)
        self.assertNotEqual(conservative_key(a), conservative_key(b))
        self.assertTrue(continuous_near(a, b))

    def test_unused_incident_and_restore_nonces_do_not_prove_independence(self):
        a = operation(); b = operation("final")
        b["scenario"]["parameters"].update(incidentStartSec=500., incidentDurationSec=1000., severity=1., driverRestoreSec=1000.)
        self.assertEqual(conservative_key(a), conservative_key(b)); self.assertTrue(continuous_near(a, b))

    def test_actual_resources_separate_group_not_declared_count_nonce(self):
        a = operation(); b = operation("final"); b["scenario"]["parameters"]["truckCount"] = 99
        self.assertTrue(continuous_near(a, b))
        b["scenario"]["configuration"]["trucks"].append({"start": {"x": 1}, "destination": {"x": 2}})
        self.assertFalse(continuous_near(a, b))

    def test_same_split_repeated_group_is_allowed_cross_split_is_rejected(self):
        a = operation(); b = operation()
        self.assertEqual(crossing_groups([a, b], conservative_key), [])
        b["split"] = "calibration"
        self.assertEqual(len(crossing_groups([a, b], conservative_key)), 1)

    def test_actual_unavailable_driver_activates_restoration_exposure(self):
        a = operation(); a["scenario"]["configuration"]["operations"]["drivers"][0]["available"] = False
        self.assertEqual(descriptor(a)[1]["driverRestoreSec"], 300.)


if __name__ == "__main__": unittest.main()
