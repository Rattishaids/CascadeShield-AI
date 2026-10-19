"""Render acquisition/quality inventories from measured artifacts, never guessed records."""
from __future__ import annotations

from collections import Counter
from pathlib import Path

from data_common import META, REPORTS, ROOT, read_json, relative, utc_now


def safe(value):
    return str(value).replace("|", "\\|").replace("\n", " ")


def main():
    inventory = read_json(META / "source_inventory.json", [])
    manifest = read_json(META / "manifest.json", {"assets": {}, "attempts": []})
    quality = read_json(REPORTS / "data_quality.json", {"raw_profiles": {}, "processed_outputs": []})
    REPORTS.mkdir(exist_ok=True)
    assets = manifest["assets"]
    rows = ["# Dataset inventory", "", "Generated from downloaded evidence and file scans at " + utc_now() + ".",
        "", "All nine requested sources were checked. GB 2024 is a bounded context pilot. Brazil, Portugal and NYC are independent cohorts. No combined operational dataset or experimental result is asserted.",
        "", "| Source | Region | Actual acquisition | License / reuse | Scope and relevance |", "|---|---|---|---|---|"]
    for source in inventory:
        acquired = [v for v in assets.values() if v["source_id"] == source["id"] and v["path"].startswith("data/raw/")]
        status = f"{len(acquired)} raw files; {sum(v['bytes'] for v in acquired):,} bytes" if acquired else source.get("download_status", "API/interface; see scope")
        if source["id"] == "overpass":
            status = "Interface for the OSM extract; same underlying dataset"
        rows.append("| " + " | ".join(safe(x) for x in [f"[{source['id']}]({source['url']})", source["region"], status, source["license"], source["role"]]) + " |")
    for source in inventory:
        rows += ["", "## " + source["id"], "", "Source: " + source["url"], "", "License evidence: " + source["license_url"]]
        for key in ["landing_page_status", "selected_period", "catalog_metadata", "citation_metadata", "temporal_note", "scope_note", "requested_snapshot_utc", "bbox_south_west_north_east", "request_parameters", "api_contract", "limitations", "reuse_gate", "missing_requirements", "next_step"]:
            if key in source:
                rows += ["", "**" + key.replace("_", " ") + ":** " + str(source[key])]
        associated = [v for v in quality["raw_profiles"].values() if
            (source["id"] == "olist" and v.get("zip_member", "").startswith("olist_"))]
        profile_names = {"dft": ["dft_collision_2024", "dft_vehicle_2024", "dft_casualty_2024"],
                         "cambridge": ["cambridge_sites"], "porto": ["porto:train.csv"],
                         "weather": ["weather_birmingham_2024"]}.get(source["id"], [])
        associated.extend(quality["raw_profiles"][n] for n in profile_names if n in quality["raw_profiles"])
        ranges = [p["observed_date_ranges"] for p in associated if p.get("observed_date_ranges")]
        if ranges:
            rows += ["", "**Observed record date ranges:** " + str(ranges)]
    rows += ["", "## Scope limits", "", "Only complete 2024 annual DfT tables were selected. The multi-gigabyte 1979-latest archive and overlapping annual/multi-year extracts are not downloaded. The checked source page preserves their links and advertised sizes. The configured per-file limit is 1.5 GiB, total raw limit 3.5 GiB, with a 2 GiB free-space reserve.",
        "", "OSM coverage is a Birmingham road-geometry pilot (south/west/north/east: 52.42, -1.99, 52.55, -1.78), as of 2024-01-01T00:00:00Z, not the global map or a validated HGV routing graph. Weather is one requested Birmingham location for 2024, not every collision/site location. Cambridge is a static inventory published in 2023; per-site effective dates are unavailable. No Cambridge sites are asserted to be active in 2024.",
        "", "Kaggle source versions may change. Exact acquired bytes are identified by SHA256 and the HTTP ETag/Last-Modified when supplied. Catalog lastUpdated is dataset metadata, not a record observation date. NYC repository downloads are pinned to the recorded commit."]
    (REPORTS / "DATASET_INVENTORY.md").write_text("\n".join(rows) + "\n", encoding="utf-8")

    rows = ["# Download status", "", "## Successfully downloaded original data files", "", "| Asset | Local original bytes | Bytes | SHA256 |", "|---|---|---:|---|"]
    for key, value in assets.items():
        if value["path"].startswith("data/raw/"):
            rows.append(f"| {key} | `{value['path']}` | {value['bytes']:,} | `{value['sha256']}` |")
    rows += ["", "## Failed or restricted requests", "", "These are recorded attempts, not inferred missing data. A later successful retry does not erase a failed request."]
    failed = [x for x in manifest["attempts"] if x["status"] == "failed_or_restricted"]
    if failed:
        rows += ["", "| Source / asset | Request | Recorded failure | Subsequently acquired / resolution |", "|---|---|---|---|"]
        for x in failed:
            rows.append("| " + " | ".join(safe(v) for v in [x["source_id"] + " / " + x["key"], x.get("requested_url") or "discovery", x.get("detail"), x.get("resolution", str(x["key"] in assets))]) + " |")
    else:
        rows += ["", "No failed HTTP or format-validation requests recorded."]
    rows += ["", "## Unavailable or withheld research data", "",
        "- Traccar: no authorized server, account, devices or fleet-data permission supplied. No public fleet dataset was identified; demo records were not acquired.",
        "- NYC: linked Chicago Booth balanced-panel host was checked separately. Repository samples/mapping do not constitute the complete 2013 balanced panel. Repository dataset reuse license is unresolved; only raw inspection/validation is permitted by this pipeline.",
        "- Porto: live Kaggle catalog license is Unknown. If the archive is available it is quarantined, validated and excluded from processed research data and database imports.",
        "- Historical DfT archive and global OSM dump: deliberately outside the bounded acquisition scope described in the inventory.",
        "", "For a Kaggle authentication restriction, configure ~/.kaggle/kaggle.json (or KAGGLE_USERNAME/KAGGLE_KEY or KAGGLE_API_TOKEN) locally and rerun the affected source. Never send credentials in chat. Public successful downloads need no authentication."]
    (REPORTS / "DOWNLOAD_STATUS.md").write_text("\n".join(rows) + "\n", encoding="utf-8")

    rows = ["# Actual dataset columns", "", "Column names below are read from acquired files, including ZIP members. Source identifiers remain strings. Processed-column origins and transformations are in data/metadata/processed_manifest.json."]
    for key, profile in quality["raw_profiles"].items():
        rows += ["", "## " + key, "", f"Actual rows/elements: {profile['rows']:,}"]
        for name, cols in profile.items():
            if "columns" in name:
                rows += ["", "**" + name + ":** " + ", ".join("`" + (c or "<empty header>") + "`" for c in cols)]
        if profile.get("hourly_units"):
            rows += ["", "Units: " + str(profile["hourly_units"])]
    rows += ["", "## Traccar API contract (no records acquired)", "", "The downloaded OpenAPI specification describes positions and route reports. Its schema is documentation, not evidence that any fleet records are available. Inspect data/metadata/evidence/traccar_openapi.yaml for the exact contract. No columns for an unavailable fleet dataset are invented."]
    (REPORTS / "ACTUAL_COLUMNS.md").write_text("\n".join(rows) + "\n", encoding="utf-8")

    rows = ["# Data quality report", "", "Validation covers all acquired rows, not a sample. Whole-file checksums are verified before ETL. ZIP archives passed CRC validation during download. Details for every column are in data_quality.json.", "",
        "| Dataset / ZIP member | Rows | Exact duplicate rows beyond first | Duplicate declared keys | Missing key rows | Nonzero rule violations |", "|---|---:|---:|---:|---:|---|"]
    for key, profile in quality["raw_profiles"].items():
        rows.append("| " + " | ".join(safe(v) for v in [key, f"{profile['rows']:,}", profile.get("duplicate_rows", "n/a"), profile.get("duplicate_keys", "n/a"), profile.get("missing_keys", "n/a"), profile.get("rule_violations", {})]) + " |")
    rows += ["", "## Missingness, dates and source limitations"]
    for key, profile in quality["raw_profiles"].items():
        blanks = {c: n for c, n in profile.get("blank_counts", {}).items() if n}
        rows += ["", "### " + key, "", "Nonzero blank counts: " + str(blanks), "", "Observed dates: " + str(profile.get("observed_date_ranges", "No observed record timestamp supplied"))]
        if profile.get("category_counts"):
            rows += ["", "Observed categories: " + str(profile["category_counts"])]
        if "matches_publisher_row_count" in profile:
            rows += ["", "Matches publisher count: " + str(profile["matches_publisher_row_count"])]
        if "matches_expected_hours" in profile:
            rows += ["", f"Expected hours: {profile['expected_hours']}; matches: {profile['matches_expected_hours']}."]
        if profile.get("reuse_gate"):
            rows += ["", profile["reuse_gate"]]
    rows += ["", "## Relationship checks", "", "```json", __import__("json").dumps(quality.get("relationship_checks", {}), indent=2), "```",
        "", "## Interpretation", "",
        "- DfT coded missing/unknown/not-applicable values are preserved. Blank counts alone are not full semantic missingness. Exact raw code counts and the downloaded official codebook are provided; code meanings vary by field.",
        "- Exact duplicate source rows are retained, including Cambridge sites and Olist geolocation rows. No facility IDs, geocodes or unique ZIP-prefix centroids were invented.",
        "- Invalid or geographically unexpected source coordinates remain in source files and processed text. PostGIS geometry is NULL when coordinates are globally invalid; geographic study-area filters require an explicit protocol.",
        "- Olist outcomes use actual-minus-estimated delivery calendar dates for delivered orders with both dates. Actual delivery dates and derived outcomes must not become prediction-time features.",
        "- Taxicab trips are passenger-mobility proxies. Porto and NYC are not evidence of freight cascades, and their reuse permissions remain unresolved.",
        "- Cambridge bays and ERA5 weather are source-provider modelled quantities, clearly labelled. They are not generated by this project, measured loading-bay capacities or raw station observations.",
        "- No evaluation has been run and no ML models were trained. The acquired sources cannot establish intervention effectiveness or observed logistics cascading disruption ground truth."]
    order_range = quality["raw_profiles"].get("olist:olist_orders_dataset.csv", {}).get("observed_date_ranges", {}).get("order_purchase_timestamp", {})
    shipping_range = quality["raw_profiles"].get("olist:olist_order_items_dataset.csv", {}).get("observed_date_ranges", {}).get("shipping_limit_date", {})
    if order_range and shipping_range:
        rows += ["", "**Olist temporal review:** Purchase timestamps span " + order_range["min"] + " to " + order_range["max"] + "; source shipping_limit_date extends to " + shipping_range["max"] + ". A shipping deadline is a different time concept from purchase/event time. Review these values before choosing a cohort; they were preserved rather than forced into the purchase-year range."]
    domain = read_json(REPORTS / "domain_quality.json", {})
    if domain:
        rows += ["", "## Additional source-specific audits", "", "See domain_quality.json for exact DfT semantic code labels/counts, OSM snapshot/tag coverage and observed Olist outcome counts.",
            "", "Olist observed outcome counts: " + str(domain.get("olist_outcomes", {})),
            "", "Additional Olist chronology/value violations: " + str(domain.get("olist_additional_checks", {}).get("rule_violations", {})),
            "", "OSM elements edited after requested historical snapshot: " + str(domain.get("osm_historical_snapshot", {}).get("elements_with_last_edit_after_snapshot", "not acquired")),
            "", domain.get("dft_codebook_classification_note", "")]
    (REPORTS / "DATA_QUALITY.md").write_text("\n".join(rows) + "\n", encoding="utf-8")
    print("Rendered dataset inventory, download status, actual columns and data quality reports.")


if __name__ == "__main__":
    main()
