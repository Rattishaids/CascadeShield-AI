"""Parser/safety contracts and artifact-level validation; no research fixture data."""
import json
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import Mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from acquire_data import Acquisition, public_url
from data_common import META, REPORTS, ROOT, read_json, sha256
from load_postgis import ddl_for, table_info
from prepare_data import Profile, local_collision_time, valid_coords


class ParserContracts(unittest.TestCase):
    def test_unavailable_and_partial_responses_are_not_data(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "response"
            path.write_bytes(b"<!DOCTYPE html><html>Sign in</html>")
            for kind in ["zip", "csv", "json"]:
                with self.subTest(kind=kind), self.assertRaises(ValueError):
                    Acquisition.validate_format(path, kind)
            path.write_text(json.dumps({"elements": [], "remark": "runtime error: Query timed out"}), encoding="utf-8")
            with self.assertRaises(ValueError):
                Acquisition.validate_format(path, "json")

    def test_profile_counts_duplicates_missing_keys_and_coded_values(self):
        conn = sqlite3.connect(":memory:")
        profile = Profile(["id", "value"], conn, ["id"])
        for row in [{"id": "001", "value": "-1"}, {"id": "001", "value": "-1"}, {"id": "", "value": ""}]:
            profile.add(row)
        result = profile.result()
        self.assertEqual((result["rows"], result["duplicate_rows"], result["duplicate_keys"], result["missing_keys"]), (3, 1, 1, 1))
        self.assertEqual(result["blank_counts"]["value"], 1)
        self.assertEqual(result["raw_code_counts_not_automatically_null"]["value=-1"], 2)
        self.assertIn("001", result["column_profiles"]["id"]["examples"])
        conn.close()

    def test_invalid_coordinates_and_local_timestamp_are_explicit(self):
        for lat, lon in [("NaN", "0"), ("91", "0"), ("0", "181"), ("", "0")]:
            self.assertFalse(valid_coords(lat, lon))
        self.assertTrue(valid_coords("52.4862", "-1.8904"))
        # UK DST fall-back is ambiguous. The parser retains local wall time without inventing UTC.
        self.assertEqual(local_collision_time({"date": "27/10/2024", "time": "01:30"}), "2024-10-27T01:30:00")
        self.assertEqual(local_collision_time({"date": "31/02/2024", "time": "12:00"}), "")

    def test_redirect_credentials_are_not_logged(self):
        self.assertEqual(public_url("https://name:secret@example.com/file.zip?token=secret&Signature=abc"), "https://example.com/file.zip")

    def test_changed_api_period_cannot_reuse_an_immutable_cached_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "weather.json"
            path.write_text('{"hourly":{}}', encoding="utf-8")
            acquisition = object.__new__(Acquisition)
            acquisition.sources = {"weather": {"license": "fixture"}}
            acquisition.manifest = {"assets": {"weather": {"sha256": sha256(path),
                "requested_url": "https://example.com/archive?start_date=2024-01-01", "method": "GET", "request_body": None}}}
            acquisition.failure = Mock()
            acquisition.session = Mock()
            result = acquisition.download("weather", "weather", "https://example.com/archive", path,
                                         "json", params={"start_date": "2025-01-01"})
            self.assertIsNone(result)
            acquisition.failure.assert_called_once()
            acquisition.session.request.assert_not_called()
            self.assertEqual(path.read_text(encoding="utf-8"), '{"hourly":{}}')


class RealArtifactContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = read_json(META / "manifest.json")
        cls.outputs = read_json(META / "processed_manifest.json")
        if not cls.manifest or not cls.outputs:
            raise unittest.SkipTest("Acquire and prepare real data before artifact validation")

    def test_nine_sources_and_raw_hashes(self):
        sources = read_json(META / "source_inventory.json")
        self.assertEqual({s["id"] for s in sources}, {"dft", "porto", "nyc", "cambridge", "olist", "overpass", "osm", "traccar", "weather"})
        for key, asset in self.manifest["assets"].items():
            with self.subTest(asset=key):
                path = ROOT / asset["path"]
                self.assertEqual(path.stat().st_size, asset["bytes"])
                self.assertEqual(sha256(path), asset["sha256"])

    def test_lineage_and_license_quarantine(self):
        for output in self.outputs:
            with self.subTest(path=output["path"]):
                raw = self.manifest["assets"][output["source_asset"]]
                self.assertEqual(output["source_sha256"], raw["sha256"])
                self.assertNotIn(raw["source_id"], {"porto", "nyc", "traccar"})
                self.assertEqual(sha256(ROOT / output["path"]), output["sha256"])
                self.assertTrue(output["transformation"])

    def test_measured_counts_and_cohort_separation(self):
        quality = read_json(REPORTS / "data_quality.json")
        profiles = quality["raw_profiles"]
        self.assertTrue(profiles["cambridge_sites"]["matches_publisher_row_count"])
        self.assertTrue(profiles["weather_birmingham_2024"]["matches_expected_hours"])
        schemas = {table_info(o)[1] for o in self.outputs}
        self.assertEqual(schemas, {"cs_gb_2024", "cs_england_wales_static", "cs_brazil_olist", "cs_birmingham_2024"})
        for output in self.outputs:
            ddl = "\n".join(ddl_for(output))
            self.assertNotIn("TRUNCATE", ddl.upper())
            self.assertNotIn("DROP TABLE", ddl.upper())


if __name__ == "__main__":
    unittest.main()
