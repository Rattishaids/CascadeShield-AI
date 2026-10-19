"""Generate PostgreSQL/PostGIS imports or execute an atomic, checksum-verified load.

Default: writes SQL and a psql client-side COPY script without connecting to a DB.
Execution: set DATABASE_URL locally, then pass --execute. Existing imports are
verified, and conflicting nonempty tables are refused; no tables are truncated.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re

from data_common import META, ROOT, read_json, relative, sha256, write_json


def ident(value):
    return '"' + value.replace('"', '""') + '"'


def literal(value):
    return "'" + value.replace("'", "''") + "'"


def table_info(output):
    path = ROOT / output["path"]
    schema = "cs_" + path.parent.name
    table = path.stem
    if not re.fullmatch(r"[a-z][a-z0-9_]*", schema) or not re.fullmatch(r"[a-z][a-z0-9_]*", table):
        raise ValueError("Unsafe or unexpected schema/table name")
    return path, schema, table


def ddl_for(output):
    path, schema, table = table_info(output)
    full = ident(schema) + "." + ident(table)
    columns = output["columns"]
    statements = [f"CREATE SCHEMA IF NOT EXISTS {ident(schema)};",
                  f"CREATE TABLE IF NOT EXISTS {full} (" + ", ".join(ident(c) + " text" for c in columns) + ");"]
    point = None
    if {"latitude", "longitude"}.issubset(columns):
        point = ('latitude', 'longitude')
    elif {"geolocation_lat", "geolocation_lng"}.issubset(columns):
        point = ('geolocation_lat', 'geolocation_lng')
    elif {"grid_latitude", "grid_longitude"}.issubset(columns):
        point = ('grid_latitude', 'grid_longitude')
    expressions = ["t.*"]
    if point:
        # Stored, indexable spatial data. Invalid coordinates remain as source text with NULL geometry.
        statements.append(f"ALTER TABLE {full} ADD COLUMN IF NOT EXISTS geom geometry(Point,4326) GENERATED ALWAYS AS (cascadeshield_meta.wgs84_point({ident(point[0])},{ident(point[1])})) STORED;")
        statements.append(f"CREATE INDEX IF NOT EXISTS {ident(table + '_geom_idx')} ON {full} USING gist(geom);")
    if {"from_latitude", "from_longitude", "to_latitude", "to_longitude"}.issubset(columns):
        a = 'cascadeshield_meta.wgs84_point("from_latitude","from_longitude")'
        b = 'cascadeshield_meta.wgs84_point("to_latitude","to_longitude")'
        statements.append(f"ALTER TABLE {full} ADD COLUMN IF NOT EXISTS geom geometry(LineString,4326) GENERATED ALWAYS AS (CASE WHEN {a} IS NOT NULL AND {b} IS NOT NULL THEN ST_MakeLine({a},{b}) ELSE NULL END) STORED;")
        statements.append(f"CREATE INDEX IF NOT EXISTS {ident(table + '_geom_idx')} ON {full} USING gist(geom);")
    typed = {"sqm": "floor_area_sqm", "bays": "author_modelled_bays", "delivery_delay_days": "delivery_delay_days_numeric",
             "precipitation": "precipitation_mm", "temperature_2m": "temperature_c", "wind_speed_10m": "wind_speed_ms"}
    for source, alias in typed.items():
        if source in columns:
            expressions.append(f"cascadeshield_meta.safe_double(t.{ident(source)}) AS {ident(alias)}")
    if "collision_datetime_local" in columns:
        expressions.append("NULLIF(t.collision_datetime_local,'')::timestamp AS collision_time_local")
    if "time_utc" in columns:
        expressions.append("NULLIF(t.time_utc,'')::timestamptz AS weather_time_utc")
    statements.append(f"CREATE OR REPLACE VIEW {ident(schema)}.{ident(table + '_typed')} AS SELECT " + ", ".join(expressions) + f" FROM {full} t;")
    for c in ["collision_index", "order_id", "customer_id", "osm_way_id", "osm_node_id"]:
        if c in columns:
            statements.append(f"CREATE INDEX IF NOT EXISTS {ident(table + '_' + c + '_idx')} ON {full} ({ident(c)});")
    return statements


def generate(outputs):
    sql_dir = ROOT / "sql"
    sql_dir.mkdir(exist_ok=True)
    ddl = ["-- Generated from actual acquired and processed schemas. Separate cohorts stay in separate schemas."]
    copy = ["\\set ON_ERROR_STOP on", "\\ir 001_init.sql", "BEGIN;", "\\ir 002_generated_tables.sql",
            "-- Run from project root: psql -f sql/003_copy.psql. Refuses populated tables; no destructive replacement."]
    checks = ["-- Run after import. Geometry uses WGS84 (EPSG:4326); lengths require geography or suitable projected CRS."]
    for output in outputs:
        path, schema, table = table_info(output)
        full = ident(schema) + "." + ident(table)
        ddl.extend(ddl_for(output))
        copy.append(f"DO $$ BEGIN IF EXISTS (SELECT 1 FROM {full} LIMIT 1) THEN RAISE EXCEPTION 'Table already contains records; use the Python loader for idempotent checksum checks'; END IF; END $$;")
        # psql \copy uses client filesystem paths, not PostgreSQL server paths.
        csv_columns = ",".join(ident(c) for c in output["columns"])
        copy.append(f"\\copy {full} ({csv_columns}) FROM {literal(output['path'])} WITH (FORMAT csv, HEADER true, ENCODING 'UTF8')")
        provenance = {"processed": output, "raw": read_json(META / "manifest.json")["assets"][output["source_asset"]]}
        copy.append("INSERT INTO cascadeshield_meta.imports (processed_path,source_asset,raw_sha256,processed_sha256,row_count,table_schema,table_name,provenance) VALUES (" +
            ",".join([literal(output["path"]), literal(output["source_asset"]), literal(output["source_sha256"]), literal(output["sha256"]),
                      str(output["rows"]), literal(schema), literal(table), literal(json.dumps(provenance)) + "::jsonb"]) + ");")
        copy.append(f"DO $$ BEGIN IF (SELECT count(*) FROM {full}) <> {output['rows']} THEN RAISE EXCEPTION 'Imported row count mismatch'; END IF; END $$;")
        checks.append(f"SELECT {literal(schema + '.' + table)} AS dataset, count(*) AS actual_rows, {output['rows']} AS expected_rows FROM {full};")
        if any(" ADD COLUMN IF NOT EXISTS geom " in x for x in ddl_for(output)):
            checks.append(f"SELECT {literal(schema + '.' + table)} AS dataset, count(*) FILTER (WHERE geom IS NULL) AS null_geometry, count(*) FILTER (WHERE geom IS NOT NULL AND NOT ST_IsValid(geom)) AS invalid_geometry FROM {full};")
    copy.append("COMMIT;")
    (sql_dir / "002_generated_tables.sql").write_text("\n".join(ddl) + "\n", encoding="utf-8")
    (sql_dir / "003_copy.psql").write_text("\n".join(copy) + "\n", encoding="utf-8")
    (sql_dir / "004_validate.sql").write_text("\n".join(checks) + "\n", encoding="utf-8")


def execute(outputs):
    import psycopg
    dsn = os.getenv("DATABASE_URL")
    if not dsn:
        raise SystemExit("Set DATABASE_URL locally; do not place credentials in scripts, reports or chat.")
    raw_assets = read_json(META / "manifest.json")["assets"]
    with psycopg.connect(dsn) as connection:
        with connection.cursor() as cursor:
            cursor.execute((ROOT / "sql" / "001_init.sql").read_text(encoding="utf-8"))
            for output in outputs:
                path, schema, table = table_info(output)
                if sha256(path) != output["sha256"]:
                    raise ValueError("Processed checksum mismatch: " + output["path"])
                raw = ROOT / raw_assets[output["source_asset"]]["path"]
                if sha256(raw) != output["source_sha256"]:
                    raise ValueError("Raw checksum mismatch: " + output["source_asset"])
                with path.open(encoding="utf-8", newline="") as csv_file:
                    if next(csv.reader(csv_file)) != output["columns"]:
                        raise ValueError("Processed schema changed")
                cursor.execute("SELECT processed_sha256 FROM cascadeshield_meta.imports WHERE processed_path=%s", (output["path"],))
                prior = cursor.fetchone()
                full = ident(schema) + "." + ident(table)
                if prior:
                    if prior[0] != output["sha256"]:
                        raise ValueError("Conflicting existing import; explicit migration required")
                    cursor.execute(f"SELECT count(*) FROM {full}")
                    if cursor.fetchone()[0] != output["rows"]:
                        raise ValueError("Existing table row count changed")
                    print("verified existing import", output["path"])
                    continue
                statements = ddl_for(output)
                cursor.execute(statements[0])
                cursor.execute(statements[1])
                cursor.execute(f"SELECT count(*) FROM {full}")
                if cursor.fetchone()[0]:
                    raise ValueError("Refusing to overwrite nonempty table " + full)
                cols = ",".join(ident(c) for c in output["columns"])
                with cursor.copy(f"COPY {full} ({cols}) FROM STDIN WITH (FORMAT csv, HEADER true, ENCODING 'UTF8')") as copy:
                    with path.open("rb") as f:
                        while block := f.read(1024 * 1024):
                            copy.write(block)
                for statement in statements[2:]:
                    cursor.execute(statement)
                cursor.execute(f"SELECT count(*) FROM {full}")
                if cursor.fetchone()[0] != output["rows"]:
                    raise ValueError("Database row count mismatch")
                provenance = {"processed": output, "raw": raw_assets[output["source_asset"]]}
                cursor.execute("INSERT INTO cascadeshield_meta.imports (processed_path,source_asset,raw_sha256,processed_sha256,row_count,table_schema,table_name,provenance) VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb)",
                    (output["path"], output["source_asset"], output["source_sha256"], output["sha256"], output["rows"], schema, table, json.dumps(provenance)))
                print("loaded", output["path"], output["rows"], "rows")
    print("Import committed successfully.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    outputs = read_json(META / "processed_manifest.json", [])
    if not outputs:
        raise SystemExit("No processed manifest; run scripts/prepare_data.py first.")
    generate(outputs)
    if args.execute:
        execute(outputs)
    else:
        print(f"Generated import and validation SQL for {len(outputs)} processed tables. No database connection made.")


if __name__ == "__main__":
    main()
