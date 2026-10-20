"""Verify the optional published model bundle without training or reading a database."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def check() -> dict:
    directory = ROOT / "models/milestone4/v1"
    manifest_bytes = (directory / "manifest.json").read_bytes()
    manifest = json.loads(manifest_bytes)
    if not manifest.get("frozen") or manifest.get("trainedOnObservedFreight"):
        raise ValueError("Expected the frozen simulation-domain model bundle")
    count = 0
    for base, records in ((ROOT, manifest["implementationSha256"]),
                          (directory, manifest["artifactSha256"])):
        for name, expected in records.items():
            path = (base / name).resolve()
            if not path.is_relative_to(base.resolve()):
                raise ValueError("Unsafe model provenance path")
            if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                raise ValueError("Frozen model checksum mismatch: " + name)
            count += 1
    graph = ROOT / "data/processed/chennai_osm/road_graph.json"
    if hashlib.sha256(graph.read_bytes()).hexdigest() != manifest["graphSha256"]:
        raise ValueError("Chennai network differs from the trained bundle")
    return {"passed": True, "checkedFiles": count + 1,
            "selectionManifestSha256": hashlib.sha256(manifest_bytes).hexdigest(),
            "provenance": "TRAINED_ON_SIMULATED_LOGISTICS_ONLY"}


if __name__ == "__main__":
    print(json.dumps(check()))
