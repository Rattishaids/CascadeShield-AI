"""Verify the actual database without mutating research datasets or imported records."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone

import psycopg
from psycopg import sql

from data_common import META, ROOT, read_json, write_json


def verify() -> dict:
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        raise SystemExit("Set DATABASE_URL locally before verifying the database.")
    expected = read_json(META / "processed_manifest.json")
    report = {
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "executed": True,
        "research_data_mutated": False,
        "tables": [],
    }
    with psycopg.connect(dsn) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT version(), postgis_full_version(), current_database()")
        report["postgresql"], report["postgis"], report["database"] = cursor.fetchone()
        cursor.execute("SELECT source_asset FROM cascadeshield_meta.imports")
        imported_assets = {row[0] for row in cursor.fetchall()}
        restricted = {name for name in imported_assets if name.lower().startswith(("porto_", "nyc_"))}
        if restricted:
            raise ValueError("Quarantined sources imported: " + ", ".join(sorted(restricted)))
        report["quarantined_imports"] = sorted(restricted)
        expected_assets = {output["source_asset"] for output in expected}
        if imported_assets != expected_assets:
            raise ValueError("Unexpected/missing research import sources: " + ", ".join(sorted(imported_assets ^ expected_assets)))
        for output in expected:
            path = ROOT / output["path"]
            schema, table = "cs_" + path.parent.name, path.stem
            table_identifier = sql.Identifier(schema, table)
            cursor.execute(sql.SQL("SELECT count(*) FROM {}").format(table_identifier))
            actual_rows = cursor.fetchone()[0]
            cursor.execute(
                "SELECT processed_sha256,raw_sha256,row_count FROM cascadeshield_meta.imports WHERE processed_path=%s",
                (output["path"],),
            )
            provenance = cursor.fetchone()
            if provenance != (output["sha256"], output["source_sha256"], output["rows"]):
                raise ValueError("Import provenance mismatch: " + output["path"])
            if actual_rows != output["rows"]:
                raise ValueError("Row count mismatch: " + output["path"])
            # COUNT(alias) forces evaluation of typed expressions across every row;
            # COUNT(*) alone lets PostgreSQL optimize away casts in the view.
            cursor.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_schema=%s AND table_name=%s ORDER BY ordinal_position",
                (schema, table + "_typed"),
            )
            typed_columns = [row[0] for row in cursor.fetchall() if row[0] not in output["columns"]]
            typed_counts = [sql.SQL("count(*)")]
            typed_counts.extend(sql.SQL("count({})").format(sql.Identifier(column)) for column in typed_columns)
            cursor.execute(sql.SQL("SELECT {} FROM {}").format(
                sql.SQL(", ").join(typed_counts), sql.Identifier(schema, table + "_typed")
            ))
            typed_result = cursor.fetchone()
            if typed_result[0] != actual_rows:
                raise ValueError("Typed view mismatch: " + output["path"])
            result = {
                "table": schema + "." + table,
                "expected_rows": output["rows"],
                "actual_rows": actual_rows,
                "provenance_matches": True,
                "typed_view_checked": True,
                "typed_nonnull_counts": dict(zip(typed_columns, typed_result[1:])),
            }
            cursor.execute(
                "SELECT EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema=%s AND table_name=%s AND column_name='geom')",
                (schema, table),
            )
            if cursor.fetchone()[0]:
                cursor.execute(sql.SQL(
                    "SELECT count(*) FILTER (WHERE geom IS NULL), "
                    "count(*) FILTER (WHERE geom IS NOT NULL AND NOT ST_IsValid(geom)), "
                    "count(*) FILTER (WHERE geom IS NOT NULL AND ST_SRID(geom) <> 4326) FROM {}"
                ).format(table_identifier))
                nulls, invalid, wrong_srid = cursor.fetchone()
                result.update(null_geometry=nulls, invalid_geometry=invalid, wrong_srid=wrong_srid)
                if invalid or wrong_srid:
                    raise ValueError("Invalid geometry/SRID: " + output["path"])
            report["tables"].append(result)
        report["table_count"] = len(report["tables"])
        report["total_imported_rows"] = sum(item["actual_rows"] for item in report["tables"])
        report["passed"] = True
    return report


if __name__ == "__main__":
    result = verify()
    write_json(ROOT / "reports" / "simulator_database_execution.json", result)
    print(json.dumps(result, indent=2))
