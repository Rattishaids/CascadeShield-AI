"""Add source-specific audits using the acquired official DfT codebook and OSM snapshot."""
from __future__ import annotations

import csv
import re
from collections import Counter
from datetime import datetime
from prepare_data import finite_number, source_csv

from data_common import CONFIG, META, PROCESSED, RAW, REPORTS, ROOT, read_json, utc_now, write_json


def main():
    config = read_json(CONFIG)
    manifest = read_json(META / "manifest.json")["assets"]
    codebook = read_json(META / "dft_codebook.json", {})
    lookup = {}
    for row in codebook.get("2024_code_list", [])[1:]:
        if len(row) < 4 or row[2] is None or row[3] is None:
            continue
        table, field, code, label = row[:4]
        if isinstance(code, float) and code.is_integer():
            code = int(code)
        text = str(label)
        kind = None
        if re.search(r"no data|missing|unknown|not known|not traced|untraced|not reported|not recorded|out of range", text, re.I):
            kind = "missing_unknown_or_unreported"
        elif re.search(r"not applicable", text, re.I):
            kind = "not_applicable"
        if kind:
            lookup[(table, field, str(code))] = {"label": text, "classification": kind}
    audits = {"generated_at_utc": utc_now(), "dft_codebook_semantic_codes": {}, "osm_historical_snapshot": {}, "olist_outcomes": {}}
    for table in ["collision", "vehicle", "casualty"]:
        key = f"dft_{table}_{config['dft_year']}"
        if key not in manifest:
            continue
        counts = Counter()
        with (ROOT / manifest[key]["path"]).open(encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                for field, value in row.items():
                    if (table, field, value) in lookup:
                        counts[(field, value)] += 1
        audits["dft_codebook_semantic_codes"][table] = [{"field": f, "code": c, "count": n, **lookup[(table, f, c)]} for (f, c), n in sorted(counts.items())]
    audits["dft_codebook_classification_note"] = "Counts use the downloaded 2024_code_list labels. The classification is a transparent label-pattern audit, not an exhaustive clinical/semantic interpretation. Source codes remain unchanged; not-applicable is separated from missing/unknown. Read exact labels before analysis."
    if "osm_birmingham_2024" in manifest:
        obj = read_json(ROOT / manifest["osm_birmingham_2024"]["path"])
        requested = datetime.fromisoformat(config["osm_snapshot_utc"].replace("Z", "+00:00"))
        after = missing = 0
        tag_present, highways = Counter(), Counter()
        version_min, version_max = None, None
        for element in obj["elements"]:
            timestamp = element.get("timestamp")
            if timestamp:
                date = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                after += date > requested
                version_min = min(version_min, timestamp) if version_min else timestamp
                version_max = max(version_max, timestamp) if version_max else timestamp
            else:
                missing += 1
            if element["type"] == "way":
                tag_present.update(element.get("tags", {}).keys())
                highways[element.get("tags", {}).get("highway", "<absent>")] += 1
        audits["osm_historical_snapshot"] = {"requested_snapshot_utc": config["osm_snapshot_utc"],
            "elements_with_last_edit_after_snapshot": after, "elements_without_timestamp": missing,
            "element_last_edit_min": version_min, "element_last_edit_max": version_max,
            "highway_class_counts": dict(highways), "ways_with_tag_counts": dict(tag_present),
            "turn_restriction_relations_requested": False,
            "note": "Last-edit timestamps are not traffic/closure measurements. Absence of an HGV/access/height/weight/maxspeed tag is not evidence of unrestricted freight access or a known speed."}
    outcomes = PROCESSED / "brazil_olist" / "delivery_outcomes.csv"
    if outcomes.exists():
        counts = Counter()
        with outcomes.open(encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                counts["order_rows"] += 1
                counts["status:" + row["order_status"]] += 1
                if row["delivery_delay_days"] != "":
                    counts["observed_delivered_outcomes"] += 1
                    counts["late_by_calendar_date"] += row["late_by_calendar_date"] == "1"
                else:
                    counts["outcome_missing_or_not_delivered"] += 1
        audits["olist_outcomes"] = dict(counts)
        audits["olist_outcome_note"] = "Counts summarize observed source orders only. Late means actual delivery calendar date is after the estimated date, and only status delivered is included. This is a data audit, not a model experiment."
    if "olist_archive" in manifest:
        path = ROOT / manifest["olist_archive"]["path"]
        violations, ranges = Counter(), {}
        with source_csv(path, "olist_orders_dataset.csv") as reader:
            for row in reader:
                parsed = {}
                for c in ["order_purchase_timestamp", "order_approved_at", "order_delivered_carrier_date", "order_delivered_customer_date", "order_estimated_delivery_date"]:
                    if not row[c]:
                        continue
                    try:
                        date = datetime.fromisoformat(row[c])
                    except ValueError:
                        violations["invalid_datetime:" + c] += 1
                        continue
                    parsed[c] = date
                    stamp = date.isoformat()
                    bounds = ranges.setdefault(c, {"min": stamp, "max": stamp})
                    bounds["min"], bounds["max"] = min(bounds["min"], stamp), max(bounds["max"], stamp)
                purchase = parsed.get("order_purchase_timestamp")
                for c in ["order_approved_at", "order_delivered_carrier_date", "order_delivered_customer_date"]:
                    if purchase and c in parsed and parsed[c] < purchase:
                        violations[c + "_before_purchase"] += 1
        with source_csv(path, "olist_order_items_dataset.csv") as reader:
            for row in reader:
                for c in ["price", "freight_value"]:
                    value = finite_number(row[c])
                    if value is None or value < 0:
                        violations["invalid_or_negative:" + c] += 1
        audits["olist_additional_checks"] = {"rule_violations": dict(violations), "observed_order_timestamp_ranges": ranges,
            "note": "All acquired order timestamps, including order_approved_at, validated as local/unspecified wall time. Item price/freight values checked for finite nonnegative numeric values. Source records preserved, including sequence anomalies."}
    write_json(REPORTS / "domain_quality.json", audits)
    print("Wrote source-specific semantic missing-code, OSM snapshot/tag and delivery-outcome audits.")


if __name__ == "__main__":
    main()
