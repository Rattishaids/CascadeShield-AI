"""Independently verify original hashes and every processed CSV row/header."""
from __future__ import annotations

import csv
import importlib.metadata
import os
import platform
import shutil
import sys

from data_common import CONFIG, META, REPORTS, ROOT, read_json, sha256, utc_now, write_json


def main():
    manifest = read_json(META / "manifest.json", {"assets": {}})
    outputs = read_json(META / "processed_manifest.json", [])
    sources = read_json(META / "source_inventory.json", [])
    errors = []
    checks = []
    if len(sources) != 9:
        errors.append("Expected inventories for all 9 requested sources")
    if not outputs:
        errors.append("No processed outputs found")
    for key, asset in manifest["assets"].items():
        path = ROOT / asset["path"]
        matches = path.is_file() and path.stat().st_size == asset["bytes"] and sha256(path) == asset["sha256"]
        checks.append({"asset": key, "raw_or_evidence_checksum_matches": matches})
        if not matches:
            errors.append("Original/evidence integrity mismatch: " + key)
    for output in outputs:
        path = ROOT / output["path"]
        raw = manifest["assets"].get(output["source_asset"])
        if not raw or raw["sha256"] != output["source_sha256"]:
            errors.append("Lineage mismatch: " + output["path"])
        if raw and raw["source_id"] in {"porto", "nyc", "traccar"}:
            errors.append("Unexpected quarantined/unavailable cohort in processed data")
        if not path.exists() or sha256(path) != output["sha256"]:
            errors.append("Processed integrity mismatch: " + output["path"])
            continue
        with path.open(encoding="utf-8", newline="") as f:
            reader = csv.reader(f)
            header = next(reader)
            count = 0
            malformed = 0
            for row in reader:
                count += 1
                malformed += len(row) != len(header)
        check = {"path": output["path"], "actual_rows": count, "expected_rows": output["rows"],
                 "header_matches": header == output["columns"], "malformed_rows": malformed}
        checks.append(check)
        if count != output["rows"] or header != output["columns"] or malformed:
            errors.append("Processed row/schema validation failed: " + output["path"])
    sql_validation = {"method": "PostgreSQL grammar parse only; not server execution", "files": {}, "available": False}
    try:
        from pglast import parse_sql
    except ImportError:
        sql_validation["status"] = "pglast not installed; install requirements-validation.txt for grammar validation"
    else:
        sql_validation["available"] = True
        for path in (ROOT / "sql").glob("*.sql"):
            try:
                statements = parse_sql(path.read_text(encoding="utf-8"))
                sql_validation["files"][path.name] = {"parsed": True, "statements": len(statements)}
            except Exception as exc:
                sql_validation["files"][path.name] = {"parsed": False, "error": str(exc)}
                errors.append("SQL grammar validation failed: " + path.name)
    raw = [a for a in manifest["assets"].values() if a["path"].startswith("data/raw/")]
    provenance = {"python_version": sys.version, "platform": platform.platform(),
                  "dependency_versions": {x: importlib.metadata.version(x) for x in ["requests", "openpyxl"]},
                  "config_sha256": sha256(CONFIG), "script_sha256": {p.name: sha256(p) for p in (ROOT / "scripts").glob("*.py")}}
    report = {"validated_at_utc": utc_now(), "validation_passed": not errors, "errors": errors, "checks": checks,
              "raw_file_count": len(raw), "raw_bytes": sum(a["bytes"] for a in raw), "processed_file_count": len(outputs),
              "processed_bytes": sum(o["bytes"] for o in outputs), "environment": provenance,
              "sql_grammar_validation": sql_validation,
              "database_execution": {"executed": False, "database_url_configured": bool(os.getenv("DATABASE_URL")),
                  "psql_available": bool(shutil.which("psql")), "postgres_available": bool(shutil.which("postgres")),
                  "status": "Import SQL generated; no database load executed by this artifact validator. See database_execution.json for any separate execution evidence."},
              "internet_probe": read_json(META / "connectivity.json"), "ml_models_trained": False}
    write_json(REPORTS / "validation_run.json", report)
    print(f"Validated {len(raw)} raw files and {len(outputs)} processed files; {len(errors)} errors.")
    if errors:
        raise SystemExit("\n".join(errors))


if __name__ == "__main__":
    main()
