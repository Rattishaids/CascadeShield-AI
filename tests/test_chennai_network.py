"""Contracts on real acquired OSM topology and explicitly labelled simulation defaults."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from prepare_chennai_network import acquire, digest, permitted, restrictions_for, route, speed_for


class ChennaiParserContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = json.loads((ROOT / "config/chennai_network.json").read_text(encoding="utf-8"))

    def test_unmapped_speed_is_explicit_simulation_assumption(self):
        value, source = speed_for({}, "residential", "forward", self.config)
        self.assertEqual((value, source), (20, "SIMULATION_ASSUMPTION"))
        value, source = speed_for({"maxspeed": "signals"}, "primary", "forward", self.config)
        self.assertEqual((value, source), (40, "SIMULATION_ASSUMPTION"))

    def test_hgv_and_directional_speed_tags_preserve_their_source(self):
        value, source = speed_for({"maxspeed": "50", "maxspeed:hgv:forward": "20 mph"}, "primary", "forward", self.config)
        self.assertAlmostEqual(value, 32.18688)
        self.assertEqual(source, "OSM_TAG:maxspeed:hgv:forward")
        self.assertEqual(speed_for({"maxspeed": "50;30"}, "primary", "backward", self.config), (30, "OSM_TAG:maxspeed"))

    def test_restricted_and_unknown_access_are_excluded(self):
        for tags in [{"access": "private"}, {"access": "military"}, {"hgv": "no"},
                     {"access": "unknown"}, {"access:conditional": "yes @ (delivery)"}, {"maxheight": "3"}]:
            with self.subTest(tags=tags):
                self.assertFalse(permitted(tags)[0])
        self.assertTrue(permitted({"access": "permissive", "hgv": "yes"})[0])

    def test_unsupported_turn_restriction_excludes_participating_ways(self):
        # Abstract parser fixture, never an acquired record or research observation.
        relation = {"id": 1, "tags": {"type": "restriction", "restriction": "no_u_turn"},
                    "members": [{"type": "way", "ref": 11, "role": "from"},
                                {"type": "way", "ref": 12, "role": "via"},
                                {"type": "way", "ref": 13, "role": "to"}]}
        supported, excluded, evidence = restrictions_for([relation])
        self.assertEqual(supported, [])
        self.assertEqual(excluded, {11, 12, 13})
        self.assertEqual(evidence[0]["reason"], "via_way_or_invalid_turn_restriction")


class RealChennaiArtifacts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = json.loads((ROOT / "config/chennai_network.json").read_text(encoding="utf-8"))
        raw_path = ROOT / cls.config["raw_path"]
        graph_path = ROOT / cls.config["graph_path"]
        if not raw_path.exists() or not graph_path.exists():
            raise unittest.SkipTest("Acquire the actual Chennai network before artifact validation")
        cls.raw = json.loads(raw_path.read_text(encoding="utf-8"))
        cls.graph = json.loads(graph_path.read_text(encoding="utf-8"))
        cls.raw_nodes = {n["id"]: n for n in cls.raw["elements"] if n["type"] == "node"}
        cls.raw_ways = {w["id"]: w for w in cls.raw["elements"] if w["type"] == "way"}
        cls.edges = {e["id"]: e for e in cls.graph["edges"]}

    def test_exact_source_bytes_and_license_provenance(self):
        self.assertEqual(digest(ROOT / self.config["raw_path"]), self.graph["metadata"]["sourceSha256"])
        self.assertEqual(self.graph["metadata"]["dataClass"], "REAL_GEOGRAPHIC_DATA")
        self.assertEqual(self.graph["metadata"]["license"], "ODbL-1.0")
        self.assertEqual(self.graph["metadata"]["attribution"], "© OpenStreetMap contributors")

    def test_query_changes_cannot_silently_reuse_immutable_source(self):
        changed_config = copy.deepcopy(self.config)
        changed_config["bbox_south_west_north_east"][0] += 0.001
        with self.assertRaises(ValueError):
            acquire(changed_config, offline=True)

    def test_every_directed_edge_follows_actual_consecutive_source_nodes(self):
        graph_nodes = {n["id"] for n in self.graph["nodes"]}
        self.assertEqual(len(self.edges), len(self.graph["edges"]))
        for edge in self.graph["edges"]:
            way_id, index, direction = edge["id"].split(":")
            way = self.raw_ways[int(way_id)]
            endpoints = way["nodes"][int(index):int(index) + 2]
            if direction == "r":
                endpoints.reverse()
            self.assertEqual([edge["from"], edge["to"]], endpoints)
            self.assertTrue(set(endpoints) <= graph_nodes)
            self.assertEqual(edge["geometry"], [[self.raw_nodes[n]["lon"], self.raw_nodes[n]["lat"]] for n in endpoints])
            self.assertEqual(edge["tags"], way.get("tags", {}))
            self.assertGreater(edge["lengthM"], 0)
            self.assertTrue(permitted(edge["tags"])[0])
            oneway = edge["tags"].get("oneway:hgv", edge["tags"].get("oneway:motor_vehicle", edge["tags"].get("oneway", "")))
            if oneway in {"yes", "1", "true"}:
                self.assertEqual(direction, "f")
            if oneway in {"-1", "reverse"}:
                self.assertEqual(direction, "r")

    def test_real_od_pairs_obey_turn_constraints_and_admit_closure_detours(self):
        for pair in self.graph["metadata"]["demoPairs"]:
            with self.subTest(pair=pair["id"]):
                initial = route(self.graph, pair["startNodeId"], pair["destinationNodeId"])
                detour = route(self.graph, pair["startNodeId"], pair["destinationNodeId"], pair["closurePhysicalId"])
                self.assertTrue(initial)
                self.assertTrue(detour)
                self.assertTrue(any(e["physicalId"] == pair["closurePhysicalId"] for e in initial))
                self.assertTrue(all(e["physicalId"] != pair["closurePhysicalId"] for e in detour))
                self.assertTrue(route(self.graph, pair["destinationNodeId"], pair["startNodeId"]))
                self.assertAlmostEqual(sum(e["lengthM"] for e in initial), pair["baseDistanceM"], places=2)
                for path in (initial, detour):
                    for previous, following in zip(path, path[1:]):
                        self.assertEqual(previous["to"], following["from"])
                        for restriction in self.graph["restrictions"]:
                            if restriction["fromWay"] != previous["wayId"] or restriction["viaNode"] != previous["to"]:
                                continue
                            if restriction["type"].startswith("no_"):
                                self.assertNotEqual(following["wayId"], restriction["toWay"])
                            else:
                                self.assertEqual(following["wayId"], restriction["toWay"])


if __name__ == "__main__":
    unittest.main()
