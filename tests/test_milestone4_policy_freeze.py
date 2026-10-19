"""Engineering fixtures only: immutable policy provenance must fail closed."""
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import run_frozen_milestone4_policies as frozen


class PolicyFreezeTests(unittest.TestCase):
    def test_service_same_version_with_wrong_frozen_bundle_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "manifest.json"
            path.write_text(json.dumps({"validatedModelIds": ["UNIT_TEST_MODEL"], "graphSha256": "g", "featureSchemaHash": "f"}), encoding="utf-8")
            healthy = {"status": "UP", "selectionManifestSha256": frozen.digest(path),
                       "models": [{"id": "UNIT_TEST_MODEL"}], "graphSha256": "g", "featureSchemaHash": "f"}
            with patch.object(frozen.urllib.request, "urlopen", return_value=io.StringIO(json.dumps(healthy))):
                self.assertEqual(healthy, frozen.verify_service("http://UNIT_TEST_ONLY", path))
            with patch.object(frozen.urllib.request, "urlopen", return_value=io.StringIO(json.dumps({**healthy, "selectionManifestSha256": "stale"}))):
                with self.assertRaisesRegex(ValueError, "different frozen"):
                    frozen.verify_service("http://UNIT_TEST_ONLY", path)

    def test_resume_accepts_identical_bytes_but_refuses_to_replace_changed_provenance(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "freeze.json"
            payload = {"provenance": "UNIT_FIXTURE_ONLY", "codeSha256": "a" * 64}
            frozen.immutable_freeze(path, payload)
            original = path.read_bytes()
            frozen.immutable_freeze(path, payload)
            with self.assertRaisesRegex(ValueError, "drift"):
                frozen.immutable_freeze(path, {**payload, "codeSha256": "b" * 64})
            self.assertEqual(original, path.read_bytes())

    def test_model_bound_source_and_artifact_tampering_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.py"
            source.write_text("# UNIT_FIXTURE_ONLY\n", encoding="utf-8")
            model = root / "model"
            model.mkdir()
            weights = model / "weights.bin"
            weights.write_bytes(b"UNIT_FIXTURE_ONLY")
            payload = {"frozen": True, "validatedModelIds": ["UNIT_TEST_MODEL"],
                       "implementationSha256": {"source.py": frozen.digest(source)},
                       "artifactSha256": {"weights.bin": frozen.digest(weights)}}
            manifest = model / "manifest.json"
            manifest.write_text(json.dumps(payload), encoding="utf-8")
            with patch.object(frozen, "ROOT", root):
                self.assertEqual(payload, frozen.verify_bundle(manifest))
                source.write_text("# UNIT_FIXTURE_ONLY_CHANGED\n", encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "implementation changed"):
                    frozen.verify_bundle(manifest)
                source.write_text("# UNIT_FIXTURE_ONLY\n", encoding="utf-8")
                weights.write_bytes(b"UNIT_FIXTURE_ONLY_CHANGED")
                with self.assertRaisesRegex(ValueError, "artifact changed"):
                    frozen.verify_bundle(manifest)

    def test_project_mount_and_artifact_paths_must_stay_within_their_roots(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            model = root / "model"
            model.mkdir()
            outside = root / "outside.bin"
            outside.write_bytes(b"UNIT_FIXTURE_ONLY")
            manifest = model / "manifest.json"
            manifest.write_text(json.dumps({"frozen": True, "validatedModelIds": ["UNIT_TEST_MODEL"],
                "implementationSha256": {}, "artifactSha256": {"../outside.bin": frozen.digest(outside)}}), encoding="utf-8")
            with patch.object(frozen, "ROOT", root):
                with self.assertRaisesRegex(ValueError, "inside"):
                    frozen.project_path("../other-project")
                with self.assertRaisesRegex(ValueError, "artifact changed"):
                    frozen.verify_bundle(manifest)


if __name__ == "__main__":
    unittest.main()
