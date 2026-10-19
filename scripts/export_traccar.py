"""Download an explicitly authorized fleet route report; no demo/public data assumed.

Use only after supplying your own server, permitted devices, dates and data-use
license. Credentials are read from environment variables, never command arguments.
This optional exporter is not run during the public-source acquisition task.
"""
from __future__ import annotations

import argparse
import os
from datetime import datetime
from urllib.parse import urlsplit

from acquire_data import Acquisition
from data_common import CONFIG, META, RAW, read_json, utc_now, write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device-id", type=int, action="append", required=True)
    parser.add_argument("--from", dest="start", required=True, help="ISO8601 timestamp with timezone")
    parser.add_argument("--to", dest="end", required=True, help="ISO8601 timestamp with timezone")
    parser.add_argument("--data-license", required=True, help="Actual documented fleet-data license or authorization reference")
    args = parser.parse_args()
    base = os.getenv("TRACCAR_BASE_URL", "").rstrip("/")
    parsed = urlsplit(base)
    if not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise SystemExit("Set TRACCAR_BASE_URL to an authorized server base URL, without credentials/query/fragment.")
    if parsed.scheme != "https" and not (parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1", "::1"}):
        raise SystemExit("Use HTTPS for fleet credentials (HTTP allowed only for your local server).")
    if parsed.hostname.startswith("demo") and parsed.hostname.endswith("traccar.org"):
        raise SystemExit("Public demo records are excluded from the research-data acquisition pipeline.")
    start, end = datetime.fromisoformat(args.start.replace("Z", "+00:00")), datetime.fromisoformat(args.end.replace("Z", "+00:00"))
    if start.tzinfo is None or end.tzinfo is None or start >= end or any(d <= 0 for d in args.device_id):
        raise SystemExit("Provide positive permitted device IDs and increasing timezone-aware timestamps.")
    token = os.getenv("TRACCAR_API_TOKEN")
    auth = None
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    elif os.getenv("TRACCAR_USERNAME") and os.getenv("TRACCAR_PASSWORD"):
        auth = (os.environ["TRACCAR_USERNAME"], os.environ["TRACCAR_PASSWORD"])
    else:
        raise SystemExit("Configure TRACCAR_API_TOKEN or TRACCAR_USERNAME/TRACCAR_PASSWORD locally.")
    acquisition = Acquisition(read_json(CONFIG))
    acquisition.sources.update({x["id"]: x for x in read_json(META / "source_inventory.json", [])})
    acquisition.sources["traccar"]["license"] = args.data_license
    acquisition.sources["traccar"]["license_url"] = "User-supplied fleet authorization: " + args.data_license
    params = [("deviceId", str(x)) for x in args.device_id] + [("from", args.start), ("to", args.end)]
    endpoint = base + ("/reports/route" if base.endswith("/api") else "/api/reports/route")
    import hashlib
    key = "traccar_route_" + hashlib.sha256((endpoint + repr(params)).encode()).hexdigest()[:16]
    path = acquisition.download(key, "traccar", endpoint, RAW / "traccar" / (key + ".json"), "json",
                                params=params, auth=auth, headers=headers, cohort="authorized_fleet_separate")
    if not path:
        raise SystemExit("Fleet export unavailable; inspect recorded failure. No access restriction was bypassed.")
    records = read_json(path)
    if not isinstance(records, list) or any(not isinstance(r, dict) for r in records):
        raise SystemExit("Unexpected route-report schema; original retained, not approved for ETL.")
    violations = {"unrequested_device": 0, "missing_or_invalid_fix_time": 0, "fix_time_outside_requested_window": 0}
    for record in records:
        if record.get("deviceId") not in args.device_id:
            violations["unrequested_device"] += 1
        try:
            timestamp = datetime.fromisoformat(record["fixTime"].replace("Z", "+00:00"))
            if timestamp.tzinfo is None:
                raise ValueError("timezone missing")
            if not start <= timestamp <= end:
                violations["fix_time_outside_requested_window"] += 1
        except (KeyError, TypeError, ValueError):
            violations["missing_or_invalid_fix_time"] += 1
    write_json(META / (key + "_validation.json"), {"source_asset": key, "validated_at_utc": utc_now(),
        "rows": len(records), "actual_columns": sorted({k for r in records for k in r}), "rule_violations": violations,
        "note": "Separate authorized fleet cohort. Not automatically joined to any public research data; no ML. Confirm fleet location/time and complete ETL requirements before database loading."})
    if any(violations.values()):
        raise SystemExit("Raw export retained with validation issues; inspect report before further use.")
    print("Downloaded and validated", len(records), "authorized positions; no model training performed.")


if __name__ == "__main__":
    main()
