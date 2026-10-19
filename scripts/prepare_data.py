"""Validate every acquired data row and prepare separate, traceable CSV cohorts.

No imputation, synthetic records, destructive cleaning, cross-source joins, or ML.
Missing and invalid source values remain visible in raw data and quality reports.
"""
from __future__ import annotations

import csv
import argparse
import hashlib
import io
import json
import math
import sqlite3
import zipfile
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from data_common import CONFIG, META, PROCESSED, RAW, REPORTS, ROOT, csv_writer, read_json, relative, sha256, utc_now, write_json

csv.field_size_limit(16 * 1024 * 1024)


def finite_number(value):
    try:
        n = float(value)
        return n if math.isfinite(n) else None
    except (ValueError, TypeError):
        return None


def valid_coords(lat, lon):
    a, b = finite_number(lat), finite_number(lon)
    return a is not None and b is not None and -90 <= a <= 90 and -180 <= b <= 180


def local_collision_time(row):
    try:
        return datetime.strptime(row["date"] + " " + row["time"], "%d/%m/%Y %H:%M").isoformat()
    except ValueError:
        return ""


class Profile:
    """Full-file blank, schema, duplicate, key, type and rule validation."""
    def __init__(self, columns, conn, key_columns=()):
        if len(set(columns)) != len(columns):
            raise ValueError("Duplicate source column names; DictReader cannot preserve their semantics")
        self.columns, self.conn, self.key_columns = columns, conn, list(key_columns)
        self.rows = 0
        self.blank, self.literal_null, self.non_numeric = Counter(), Counter(), Counter()
        self.numeric, self.negative_codes = Counter(), Counter()
        self.numeric_min, self.numeric_max, self.examples = {}, {}, {c: [] for c in columns}
        self.rules = Counter()
        self.date_ranges = {}
        self.duplicate_rows = self.duplicate_keys = self.missing_keys = 0
        conn.executescript("DROP TABLE IF EXISTS row_hashes; DROP TABLE IF EXISTS source_keys; CREATE TABLE row_hashes (h BLOB PRIMARY KEY) WITHOUT ROWID; CREATE TABLE source_keys (k TEXT PRIMARY KEY) WITHOUT ROWID;")

    def add(self, row):
        self.rows += 1
        if None in row or any(row.get(c) is None for c in self.columns):
            self.rules["malformed_csv_row"] += 1
        values = [row.get(c) for c in self.columns]
        digest = hashlib.blake2b(json.dumps(values, ensure_ascii=False).encode(), digest_size=16).digest()
        changed = self.conn.total_changes
        self.conn.execute("INSERT OR IGNORE INTO row_hashes VALUES (?)", (digest,))
        self.duplicate_rows += int(changed == self.conn.total_changes)
        if self.key_columns:
            keys = [row.get(c) for c in self.key_columns]
            if any(x in (None, "") for x in keys):
                self.missing_keys += 1
            else:
                changed = self.conn.total_changes
                self.conn.execute("INSERT OR IGNORE INTO source_keys VALUES (?)", (json.dumps(keys),))
                self.duplicate_keys += int(changed == self.conn.total_changes)
        for c, value in zip(self.columns, values):
            if value is None or not value.strip():
                self.blank[c] += 1
                continue
            if value.lower() in {"null", "none", "nan", "na", "n/a"}:
                self.literal_null[c] += 1
            if len(self.examples[c]) < 3 and value not in self.examples[c]:
                self.examples[c].append(value[:100])
            n = finite_number(value)
            if n is None:
                self.non_numeric[c] += 1
            else:
                self.numeric[c] += 1
                self.numeric_min[c] = min(self.numeric_min.get(c, n), n)
                self.numeric_max[c] = max(self.numeric_max.get(c, n), n)
            if value in {"-1", "-2", "-3", "99", "999"}:
                self.negative_codes[c + "=" + value] += 1
        if self.rows % 100000 == 0:
            print(f"profiled {self.rows:,} rows", flush=True)

    def date(self, field, value, fmt=None):
        if value in (None, ""):
            return None
        try:
            d = datetime.strptime(value, fmt) if fmt else datetime.fromisoformat(value)
        except (ValueError, TypeError):
            self.rules["invalid_datetime:" + field] += 1
            return None
        v = d.isoformat()
        bounds = self.date_ranges.setdefault(field, {"min": v, "max": v})
        bounds["min"], bounds["max"] = min(bounds["min"], v), max(bounds["max"], v)
        return d

    def result(self):
        self.conn.commit()
        return {"rows": self.rows, "columns": self.columns, "key_columns": self.key_columns,
                "duplicate_rows": self.duplicate_rows, "duplicate_keys": self.duplicate_keys,
                "missing_keys": self.missing_keys, "blank_counts": {c: self.blank[c] for c in self.columns},
                "literal_null_like_counts": dict(self.literal_null),
                "raw_code_counts_not_automatically_null": dict(self.negative_codes),
                "column_profiles": {c: {"numeric_values": self.numeric[c], "non_numeric_values": self.non_numeric[c],
                    "numeric_min": self.numeric_min.get(c), "numeric_max": self.numeric_max.get(c), "examples": self.examples[c]} for c in self.columns},
                "observed_date_ranges": self.date_ranges, "rule_violations": dict(self.rules),
                "empty_header_names": sum(not c for c in self.columns)}


@contextmanager
def source_csv(path, member=None):
    if member:
        with zipfile.ZipFile(path) as z, z.open(member) as binary, io.TextIOWrapper(binary, encoding="utf-8-sig", newline="") as f:
            yield csv.DictReader(f)
    else:
        with path.open(encoding="utf-8-sig", newline="") as f:
            yield csv.DictReader(f)


class Preparation:
    def __init__(self, only=None):
        self.manifest = read_json(META / "manifest.json", {"assets": {}})
        self.config = read_json(CONFIG)
        self.only = only
        existing = read_json(REPORTS / "data_quality.json", {}) if only else {}
        self.profiles = existing.get("raw_profiles", {})
        self.outputs = existing.get("processed_outputs", [])
        self.relationships = existing.get("relationship_checks", {})
        META.mkdir(parents=True, exist_ok=True)
        self.scratch = META / "quality_scratch.sqlite"
        self.conn = sqlite3.connect(self.scratch)
        self.conn.execute("PRAGMA journal_mode=OFF")
        self.conn.execute("PRAGMA synchronous=OFF")

    def asset(self, key):
        record = self.manifest["assets"].get(key)
        if not record:
            return None
        path = ROOT / record["path"]
        if not path.exists() or sha256(path) != record["sha256"]:
            raise ValueError(f"Raw integrity check failed: {key}; refusing ETL")
        return path

    def record_output(self, path, asset, rows, notes, column_origins=None):
        with path.open(encoding="utf-8", newline="") as f:
            columns = next(csv.reader(f))
        self.outputs = [o for o in self.outputs if o["path"] != relative(path)]
        self.outputs.append({"path": relative(path), "source_asset": asset,
            "source_sha256": self.manifest["assets"][asset]["sha256"], "rows": rows,
            "columns": columns, "sha256": sha256(path), "bytes": path.stat().st_size,
            "transformation": notes, "column_origins": column_origins or {c: "source" for c in columns}})

    def guide(self):
        path = self.asset("dft_data_guide")
        if not path:
            return
        import openpyxl
        workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
        sheets = {}
        for sheet in workbook:
            rows = [[v for v in row] for row in sheet.iter_rows(values_only=True)]
            sheets[sheet.title] = rows
        workbook.close()
        write_json(META / "dft_codebook.json", sheets)

    def dft(self):
        year = self.config["dft_year"]
        collision_ids, vehicle_ids = set(), set()
        vehicle_count, casualty_count = Counter(), Counter()
        expected_counts = {}
        for table in ["collision", "vehicle", "casualty"]:
            key = f"dft_{table}_{year}"
            path = self.asset(key)
            if not path:
                continue
            with source_csv(path) as reader:
                columns = reader.fieldnames
                pk = {"collision": ["collision_index"], "vehicle": ["collision_index", "vehicle_reference"],
                      "casualty": ["collision_index", "casualty_reference"]}[table]
                profile = Profile(columns, self.conn, pk)
                derived = ["source_record_number"] + (["collision_datetime_local"] if table == "collision" else [])
                output = PROCESSED / f"gb_{year}" / (table + ".csv")
                f, writer = csv_writer(output, columns + derived)
                with f:
                    for n, row in enumerate(reader, 1):
                        profile.add(row)
                        if row.get("collision_year") != str(year):
                            profile.rules["outside_selected_year"] += 1
                        id_ = row["collision_index"]
                        if table == "collision":
                            collision_ids.add(id_)
                            expected_counts[id_] = (int(row["number_of_vehicles"]), int(row["number_of_casualties"]))
                            profile.date("date", row["date"], "%d/%m/%Y")
                            timestamp = local_collision_time(row)
                            if not timestamp:
                                profile.rules["missing_or_invalid_collision_datetime"] += 1
                            row["collision_datetime_local"] = timestamp
                            if not valid_coords(row["latitude"], row["longitude"]):
                                profile.rules["missing_or_invalid_coordinates"] += 1
                            if valid_coords(row["latitude"], row["longitude"]):
                                a, b = float(row["latitude"]), float(row["longitude"])
                                if not (49 <= a <= 61 and -9 <= b <= 3):
                                    profile.rules["outside_generous_GB_coordinate_bounds"] += 1
                        else:
                            if collision_ids and id_ not in collision_ids:
                                profile.rules["orphan_collision_reference"] += 1
                            if table == "vehicle":
                                vehicle_ids.add((id_, row["vehicle_reference"]))
                                vehicle_count[id_] += 1
                            else:
                                casualty_count[id_] += 1
                                if vehicle_ids and (id_, row["vehicle_reference"]) not in vehicle_ids:
                                    profile.rules["orphan_vehicle_reference"] += 1
                        row["source_record_number"] = n
                        writer.writerow(row)
                self.profiles[key] = profile.result()
                self.record_output(output, key, profile.rows,
                    "All source rows and codes retained. Added one-based CSV data-row number; collision timestamp parsed as Europe/London local wall time without inventing a UTC offset. No imputation or deduplication.",
                    {c: "derived" if c in derived else "source" for c in columns + derived})
        self.relationships["dft"] = {
            "collision_rows_with_vehicle_count_mismatch": sum(vehicle_count[k] != v[0] for k, v in expected_counts.items()) if vehicle_ids else None,
            "collision_rows_with_casualty_count_mismatch": sum(casualty_count[k] != v[1] for k, v in expected_counts.items()) if casualty_count else None,
            "note": "Counts checked across acquired annual tables. Timestamp-to-UTC conversion needs explicit handling of DST ambiguity; no weather join was performed."}

    def cambridge(self):
        path = self.asset("cambridge_sites")
        if not path:
            return
        output = PROCESSED / "england_wales_static" / "logistics_sites.csv"
        with source_csv(path) as reader:
            columns = reader.fieldnames
            required = {"category", "latitude", "longitude", "sqm", "bays"}
            if not required.issubset(columns):
                raise ValueError(f"Cambridge schema changed: {columns}")
            profile = Profile(columns, self.conn)
            categories = Counter()
            f, writer = csv_writer(output, ["source_record_number"] + columns)
            with f:
                for n, row in enumerate(reader, 1):
                    profile.add(row)
                    categories[row["category"]] += 1
                    if row["category"] not in {"warehouse", "factory", "retail"}:
                        profile.rules["unexpected_category"] += 1
                    if not valid_coords(row["latitude"], row["longitude"]):
                        profile.rules["missing_or_invalid_coordinates"] += 1
                    elif not (49 <= float(row["latitude"]) <= 56 and -7 <= float(row["longitude"]) <= 3):
                        profile.rules["outside_generous_England_Wales_bounds"] += 1
                    for c in ["sqm", "bays"]:
                        value = finite_number(row[c])
                        if value is None or value < 0 or (c == "sqm" and value == 0):
                            profile.rules["missing_or_invalid:" + c] += 1
                    writer.writerow({"source_record_number": n, **row})
            result = profile.result()
            result["category_counts"] = dict(categories)
            result["publisher_expected_rows"] = 47683
            result["matches_publisher_row_count"] = profile.rows == 47683
            self.profiles["cambridge_sites"] = result
            self.record_output(output, "cambridge_sites", profile.rows,
                "All rows retained. Added one-based source record number, not a real facility identifier. bays is the source authors' modelled estimate; no observed capacity or facility observation date is asserted.",
                {c: "derived" if c == "source_record_number" else "source" for c in ["source_record_number"] + columns})

    def olist(self):
        path = self.asset("olist_archive")
        if not path:
            return
        keys = {"olist_customers_dataset.csv": ["customer_id"], "olist_orders_dataset.csv": ["order_id"],
                "olist_order_items_dataset.csv": ["order_id", "order_item_id"],
                "olist_order_payments_dataset.csv": ["order_id", "payment_sequential"],
                "olist_products_dataset.csv": ["product_id"], "olist_sellers_dataset.csv": ["seller_id"],
                "product_category_name_translation.csv": ["product_category_name"]}
        id_sets = {c: set() for c in ["order_id", "customer_id", "product_id", "seller_id"]}
        references = Counter()
        with zipfile.ZipFile(path) as z:
            members = [n for n in z.namelist() if n.lower().endswith(".csv")]
        # Process dimensions before their foreign keys. No geolocation centroid is invented.
        order = {"olist_customers_dataset.csv": 0, "olist_products_dataset.csv": 1,
                 "olist_sellers_dataset.csv": 2, "olist_orders_dataset.csv": 3}
        members.sort(key=lambda n: order.get(Path(n).name, 10))
        for member in members:
            name = Path(member).name
            with source_csv(path, member) as reader:
                columns = reader.fieldnames
                profile = Profile(columns, self.conn, keys.get(name, []))
                output = PROCESSED / "brazil_olist" / name
                f, writer = csv_writer(output, columns)
                metric_file = None
                if name == "olist_orders_dataset.csv":
                    metric_file, metric_writer = csv_writer(PROCESSED / "brazil_olist" / "delivery_outcomes.csv",
                        ["order_id", "order_status", "delivered_date_local", "estimated_delivery_date_local", "delivery_delay_days", "late_by_calendar_date"])
                try:
                    with f:
                        for row in reader:
                            profile.add(row)
                            dates = {}
                            for c in columns:
                                if c.endswith("_timestamp") or c.endswith("_date") or c in {"shipping_limit_date", "order_approved_at"}:
                                    dates[c] = profile.date(c, row[c])
                            if name in {"olist_orders_dataset.csv", "olist_customers_dataset.csv", "olist_products_dataset.csv", "olist_sellers_dataset.csv"}:
                                primary = keys[name][0]
                                id_sets[primary].add(row[primary])
                            for c in id_sets:
                                if c in row and not (name in keys and keys[name] == [c]):
                                    if row[c] not in id_sets[c]:
                                        references[name + ":" + c] += 1
                            if name == "olist_geolocation_dataset.csv":
                                if not valid_coords(row["geolocation_lat"], row["geolocation_lng"]):
                                    profile.rules["invalid_coordinates"] += 1
                                elif not (-34 <= float(row["geolocation_lat"]) <= 6 and -74 <= float(row["geolocation_lng"]) <= -28):
                                    profile.rules["outside_generous_Brazil_bounds"] += 1
                            if name == "olist_orders_dataset.csv":
                                purchase = dates.get("order_purchase_timestamp")
                                delivered = dates.get("order_delivered_customer_date")
                                estimated = dates.get("order_estimated_delivery_date")
                                if purchase and delivered and delivered < purchase:
                                    profile.rules["delivery_before_purchase"] += 1
                                delay, late = "", ""
                                if row["order_status"] == "delivered" and delivered and estimated:
                                    delay = (delivered.date() - estimated.date()).days
                                    late = int(delay > 0)
                                metric_writer.writerow({"order_id": row["order_id"], "order_status": row["order_status"],
                                    "delivered_date_local": row["order_delivered_customer_date"],
                                    "estimated_delivery_date_local": row["order_estimated_delivery_date"],
                                    "delivery_delay_days": delay, "late_by_calendar_date": late})
                            writer.writerow(row)
                finally:
                    if metric_file:
                        metric_file.close()
                result = profile.result()
                result["zip_member"] = member
                self.profiles["olist:" + name] = result
                self.record_output(output, "olist_archive", profile.rows,
                    "All source rows and columns copied from ZIP member " + member + "; UTF-8 CSV serialization only; no imputation, aggregation or deduplication. Timezones are not declared by these rows.")
                if metric_file:
                    self.record_output(PROCESSED / "brazil_olist" / "delivery_outcomes.csv", "olist_archive", profile.rows,
                        "One row per original order. Actual delivery minus estimated delivery by calendar date, in days, only for status delivered with both dates present. Same-day delivery is not flagged late. Missing outcomes remain blank. These are outcomes, never prediction-time features.",
                        {"order_id": "source", "order_status": "source", "delivered_date_local": "source rename", "estimated_delivery_date_local": "source rename", "delivery_delay_days": "derived", "late_by_calendar_date": "derived"})
        self.relationships["olist_orphan_references"] = dict(references)

    def porto(self):
        path = self.asset("porto_archive")
        if not path:
            return
        # License is Unknown: validate raw records, but do not create a research-use derivative.
        with zipfile.ZipFile(path) as z:
            members = [n for n in z.namelist() if n.lower().endswith(".csv")]
        for member in members:
            with source_csv(path, member) as reader:
                columns = reader.fieldnames
                profile = Profile(columns, self.conn, ["TRIP_ID"] if "TRIP_ID" in columns else [])
                for row in reader:
                    profile.add(row)
                    if "TIMESTAMP" in row:
                        value = finite_number(row["TIMESTAMP"])
                        if value is None:
                            profile.rules["invalid_unix_timestamp"] += 1
                        else:
                            try:
                                profile.date("TIMESTAMP_UTC", datetime.fromtimestamp(value, timezone.utc).isoformat())
                            except (ValueError, OSError, OverflowError):
                                profile.rules["invalid_unix_timestamp"] += 1
                    if "POLYLINE" in row:
                        try:
                            points = json.loads(row["POLYLINE"])
                            if not isinstance(points, list):
                                raise ValueError("not a list")
                            if not points:
                                profile.rules["empty_polyline"] += 1
                            if any(not isinstance(p, list) or len(p) != 2 or not valid_coords(p[1], p[0]) for p in points):
                                profile.rules["invalid_polyline_coordinate"] += 1
                        except (ValueError, TypeError):
                            profile.rules["invalid_polyline_json"] += 1
                    if row.get("MISSING_DATA", "").lower() == "true":
                        profile.rules["source_missing_data_flag_true"] += 1
                result = profile.result()
                result.update({"zip_member": member, "reuse_gate": "Quarantined: license Unknown; no processed research derivative created."})
                self.profiles["porto:" + member] = result

    def nyc(self):
        for key, asset in self.manifest["assets"].items():
            if asset["source_id"] != "nyc" or asset["format"] != "csv":
                continue
            path = self.asset(key)
            with source_csv(path) as reader:
                profile = Profile(reader.fieldnames, self.conn)
                for row in reader:
                    profile.add(row)
                result = profile.result()
                result["reuse_gate"] = "Quarantined: no explicit dataset license identified; no processed research derivative created."
                self.profiles[key] = result

    def osm(self):
        path = self.asset("osm_birmingham_2024")
        if not path:
            return
        obj = read_json(path)
        if obj.get("remark"):
            raise ValueError("Partial Overpass response is not accepted")
        nodes = {x["id"]: x for x in obj["elements"] if x["type"] == "node"}
        ways = [x for x in obj["elements"] if x["type"] == "way"]
        duplicates = len(obj["elements"]) - len({(x["type"], x["id"]) for x in obj["elements"]})
        problems = Counter()
        paths = {n: PROCESSED / "birmingham_2024" / ("osm_" + n + ".csv") for n in ["nodes", "ways", "segments"]}
        nf, nw = csv_writer(paths["nodes"], ["osm_node_id", "latitude", "longitude", "osm_version", "osm_timestamp"])
        wf, ww = csv_writer(paths["ways"], ["osm_way_id", "node_ids_json", "tags_json", "osm_version", "osm_timestamp"])
        sf, sw = csv_writer(paths["segments"], ["osm_way_id", "segment_index", "from_node_id", "to_node_id", "from_latitude", "from_longitude", "to_latitude", "to_longitude", "tags_json"])
        count = 0
        with nf, wf, sf:
            for id_, n in nodes.items():
                if not valid_coords(n.get("lat"), n.get("lon")):
                    problems["invalid_node_coordinates"] += 1
                nw.writerow({"osm_node_id": id_, "latitude": n.get("lat"), "longitude": n.get("lon"), "osm_version": n.get("version"), "osm_timestamp": n.get("timestamp")})
            for w in ways:
                tags = json.dumps(w.get("tags", {}), ensure_ascii=False, separators=(",", ":"))
                ww.writerow({"osm_way_id": w["id"], "node_ids_json": json.dumps(w["nodes"]), "tags_json": tags,
                    "osm_version": w.get("version"), "osm_timestamp": w.get("timestamp")})
                for i, (a, b) in enumerate(zip(w["nodes"], w["nodes"][1:])):
                    if a not in nodes or b not in nodes:
                        problems["missing_segment_node_reference"] += 1
                        continue
                    na, nb = nodes[a], nodes[b]
                    sw.writerow({"osm_way_id": w["id"], "segment_index": i, "from_node_id": a, "to_node_id": b,
                        "from_latitude": na["lat"], "from_longitude": na["lon"], "to_latitude": nb["lat"], "to_longitude": nb["lon"], "tags_json": tags})
                    count += 1
        self.profiles["osm_birmingham_2024"] = {"rows": len(obj["elements"]), "columns": sorted({k for x in obj["elements"] for k in x}),
            "node_columns": sorted({k for n in nodes.values() for k in n}), "way_columns": sorted({k for w in ways for k in w}),
            "nodes": len(nodes), "ways": len(ways), "segments": count, "duplicate_element_ids": duplicates,
            "rule_violations": dict(problems), "response_osm3s": obj.get("osm3s"),
            "requested_snapshot_utc": self.config["osm_snapshot_utc"],
            "note": "Response timestamp_osm_base describes server database freshness, not the requested historical snapshot. Element timestamps are last-edit times."}
        for name, rows in [("nodes", len(nodes)), ("ways", len(ways)), ("segments", count)]:
            origins = {
                "nodes": {"osm_node_id": "source id renamed", "latitude": "source lat renamed", "longitude": "source lon renamed", "osm_version": "source version renamed", "osm_timestamp": "source timestamp renamed"},
                "ways": {"osm_way_id": "source id renamed", "node_ids_json": "source nodes array serialized", "tags_json": "source tags object serialized", "osm_version": "source version renamed", "osm_timestamp": "source timestamp renamed"},
                "segments": {"osm_way_id": "source way id renamed", "segment_index": "derived zero-based consecutive-node pair index", "from_node_id": "source way nodes[i]", "to_node_id": "source way nodes[i+1]", "from_latitude": "source node lat by node id", "from_longitude": "source node lon by node id", "to_latitude": "source node lat by node id", "to_longitude": "source node lon by node id", "tags_json": "source way tags object serialized"}}
            self.record_output(paths[name], "osm_birmingham_2024", rows,
                "Historical OSM geometry and exact source tags. Segments split ways at consecutive real OSM nodes. No travel times, missing speed limits, freight permissions, reverse edges or turn restrictions were fabricated.", origins[name])

    def weather(self):
        path = self.asset("weather_birmingham_2024")
        if not path:
            return
        obj = read_json(path)
        hourly = obj["hourly"]
        if any(len(v) != len(hourly["time"]) for v in hourly.values()):
            raise ValueError("Unequal weather array lengths")
        if obj.get("utc_offset_seconds") != 0:
            raise ValueError("Expected UTC weather response")
        columns = list(hourly)
        output = PROCESSED / "birmingham_2024" / "weather_hourly.csv"
        f, writer = csv_writer(output, ["time_utc", "grid_latitude", "grid_longitude"] + [c for c in columns if c != "time"])
        violations = Counter()
        blank = Counter()
        times = hourly["time"]
        expected_start = datetime.fromisoformat(self.config["weather"]["start_date"])
        expected_n = (datetime.fromisoformat(self.config["weather"]["end_date"]) - expected_start).days * 24 + 24
        with f:
            for i, time_ in enumerate(times):
                expected = (expected_start + timedelta(hours=i)).isoformat(timespec="minutes")
                if time_ != expected:
                    violations["timestamp_not_expected_hourly_sequence"] += 1
                for c in columns:
                    if hourly[c][i] is None:
                        blank[c] += 1
                if hourly.get("relative_humidity_2m", [None] * len(times))[i] is not None and not 0 <= hourly["relative_humidity_2m"][i] <= 100:
                    violations["humidity_out_of_range"] += 1
                for c in ["precipitation", "rain", "snowfall", "wind_speed_10m"]:
                    if hourly.get(c, [None] * len(times))[i] is not None and hourly[c][i] < 0:
                        violations["negative:" + c] += 1
                writer.writerow({"time_utc": time_ + ":00+00:00", "grid_latitude": obj["latitude"], "grid_longitude": obj["longitude"],
                    **{c: hourly[c][i] for c in columns if c != "time"}})
        self.profiles["weather_birmingham_2024"] = {"rows": len(times), "columns": list(obj), "hourly_columns": columns,
            "hourly_units": obj.get("hourly_units"), "blank_counts": {c: blank[c] for c in columns},
            "rule_violations": dict(violations), "expected_hours": expected_n, "matches_expected_hours": len(times) == expected_n,
            "observed_date_ranges": {"time_utc": {"min": times[0], "max": times[-1]}},
            "requested_coordinates": {k: self.config["weather"][k] for k in ["latitude", "longitude"]},
            "returned_grid_coordinates": {"latitude": obj["latitude"], "longitude": obj["longitude"]},
            "model": self.config["weather"]["models"], "time_basis": "UTC; reanalysis, not as-issued forecasts"}
        self.record_output(output, "weather_birmingham_2024", len(times),
            "Hourly arrays flattened without imputation. UTC offset comes from checked API metadata. Coordinates are the actual returned model grid cell; requested point retained in provenance. Units retained in quality report.",
            {"time_utc": "source hourly.time with verified UTC offset added", "grid_latitude": "source response latitude renamed", "grid_longitude": "source response longitude renamed", **{c: "source hourly." + c for c in columns if c != "time"}})

    def run(self):
        try:
            for name in self.only or ["guide", "dft", "cambridge", "olist", "porto", "nyc", "osm", "weather"]:
                print("validating/preparing", name, flush=True)
                getattr(self, name)()
            report = {"generated_at_utc": utc_now(), "validation_scope": "Every row of each CSV and CSV ZIP member listed in raw_profiles; whole-file SHA256; ZIP CRC checked during download; all listed OSM elements and hourly weather arrays.",
                "raw_profiles": self.profiles, "relationship_checks": self.relationships,
                "policy": "No imputation, synthetic rows, source overwrites or cross-country/time operational joins. Coded unknown values retained. Quarantined sources only profiled.",
                "processed_outputs": self.outputs}
            write_json(REPORTS / "data_quality.json", report)
            write_json(META / "processed_manifest.json", self.outputs)
            write_json(REPORTS / "actual_columns.json", {k: {field: v for field, v in value.items() if "columns" in field} for k, value in self.profiles.items()})
        finally:
            self.conn.close()
            if self.scratch.exists():
                self.scratch.unlink()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", nargs="+", choices=["guide", "dft", "cambridge", "olist", "porto", "nyc", "osm", "weather"])
    Preparation(parser.parse_args().only).run()
