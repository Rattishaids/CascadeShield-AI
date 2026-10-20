"""Record existing Python contract tests into a new release-evidence file."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ml", action="store_true", help="Run optional ML/audit tests instead of the acquisition/geography contracts")
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    target = args.report if args.report.is_absolute() else ROOT / args.report
    if target.exists():
        raise FileExistsError("Use a fresh report path to preserve previous evidence")
    patterns = ("test_ml*.py", "test_milestone4*.py") if args.ml else (
        "test_data_pipeline.py", "test_chennai_network.py", "test_graph_snapshot_converter.py", "test_benchmark_statistics.py")
    report = {"provenance": "RELEASE_ENGINEERING_TEST_EVIDENCE", "ml": args.ml,
              "checkedAtUtc": datetime.now(timezone.utc).isoformat(), "suites": [], "notAvailable": []}
    def applicable(suite):
        result = unittest.TestSuite()
        for item in suite:
            if isinstance(item, unittest.TestSuite):
                result.addTests(applicable(item))
            elif not args.ml and item.__class__.__name__ in ("RealArtifactContracts", "RealChennaiArtifacts"):
                report["notAvailable"].append({"test": item.id(), "status": "NOT_AVAILABLE",
                    "reason": "Requires original raw source bytes or full historical cohorts intentionally excluded from the simulator ZIP. Their historical results are archived separately; no substitute records are created."})
            else:
                result.addTest(item)
        return result
    for pattern in patterns:
        output = io.StringIO()
        suite = applicable(unittest.TestLoader().discover(str(ROOT / "tests"), pattern=pattern))
        result = unittest.TextTestRunner(stream=output, verbosity=2).run(suite)
        report["suites"].append({"pattern": pattern, "tests": result.testsRun,
                                 "failures": len(result.failures), "errors": len(result.errors),
                                 "skipped": len(result.skipped), "passed": result.wasSuccessful(),
                                 "output": output.getvalue()})
    for field in ("tests", "failures", "errors", "skipped"):
        report[field] = sum(row[field] for row in report["suites"])
    report["passed"] = all(row["passed"] for row in report["suites"]) and report["skipped"] == 0
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({**{k: report[k] for k in ("passed", "tests", "failures", "errors", "skipped")},
                      "notAvailable": len(report["notAvailable"])}))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
