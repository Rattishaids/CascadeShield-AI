"""Verify recorded pre-Milestone-4 files after relocation without changing them."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def verify(root: Path, manifest: dict) -> dict:
    checks = []
    for name, expected in manifest["files"].items():
        path = (root / name).resolve()
        if not path.is_relative_to(root.resolve()):
            raise ValueError("Recorded path escapes project: " + name)
        check = {"path": name, "exists": path.is_file(), "expectedSha256": expected["sha256"]}
        if path.is_file():
            actual = hashlib.file_digest(path.open("rb"), "sha256").hexdigest()
            check.update(actualSha256=actual, bytes=path.stat().st_size,
                         passed=actual == expected["sha256"] and path.stat().st_size == expected["bytes"])
        else:
            check["passed"] = False
        checks.append(check)
    return {"schemaVersion": "cascadeshield.milestone4-preservation-check/1.0",
            "checkedAtUtc": datetime.now(timezone.utc).isoformat(),
            "projectRoot": str(root.resolve()), "fileCount": len(checks),
            "passedCount": sum(row["passed"] for row in checks),
            "passed": all(row["passed"] for row in checks), "files": checks,
            "scope": "Only files recorded in the immutable pre-M4 preservation manifest; this does not re-count database rows or claim every unrecorded file was checked."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=ROOT / "reports/milestone4_preservation_manifest.json")
    parser.add_argument("--output", type=Path, default=ROOT / "reports/milestone4_d_drive_preservation.json")
    args = parser.parse_args()
    result = verify(ROOT, json.loads(args.manifest.read_text(encoding="utf-8-sig")))
    result["manifestSha256"] = hashlib.sha256(args.manifest.read_bytes()).hexdigest()
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: result[key] for key in ("fileCount", "passedCount", "passed")}))
    raise SystemExit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
