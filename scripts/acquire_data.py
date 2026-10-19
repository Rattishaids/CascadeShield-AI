"""Discover and acquire official public assets, with provenance and explicit failures.

No credential values or signed redirect query strings are saved. Re-running verifies
existing downloads rather than replacing originals. No alternate mirrors are used.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import time
import zipfile
from pathlib import Path
from urllib.parse import quote, urlencode, urljoin, urlsplit, urlunsplit

import requests

from data_common import CONFIG, META, RAW, REPORTS, ROOT, read_json, relative, sha256, utc_now, write_json


def public_url(url):
    p = urlsplit(url)
    # Redirects may contain temporary access tokens. The request URL is recorded separately.
    return urlunsplit((p.scheme, p.hostname or "", p.path, "", ""))


class Acquisition:
    def __init__(self, config):
        self.config = config
        self.session = requests.Session()
        self.session.headers["User-Agent"] = "CascadeShield-AI-research-data-acquisition/1.0"
        self.manifest = read_json(META / "manifest.json", {"assets": {}, "attempts": []})
        self.sources = {x["id"]: dict(x) for x in config["sources"]}
        for source in self.sources.values():
            source["checked_at_utc"] = utc_now()
        self.raw_bytes = sum(p.stat().st_size for p in RAW.rglob("*") if p.is_file()) if RAW.exists() else 0

    def save(self):
        write_json(META / "manifest.json", self.manifest)
        write_json(META / "source_inventory.json", list(self.sources.values()))

    def download(self, key, source, url, path, kind="document", params=None, data=None, auth=None, headers=None, cohort=None):
        if source not in self.sources:
            raise ValueError("Unknown source configuration: " + source)
        path.parent.mkdir(parents=True, exist_ok=True)
        requested_url = url + ("?" + urlencode(params) if params else "")
        previous = self.manifest["assets"].get(key)
        if path.exists():
            if previous and previous.get("sha256") == sha256(path):
                if previous.get("requested_url") != requested_url or previous.get("method", "GET") != ("POST" if data else "GET") or previous.get("request_body") != data:
                    self.failure(source, key, "request_changed_for_immutable_path; use a new versioned key/path", requested_url)
                    return None
                previous["license"] = self.sources[source]["license"]
                previous["license_evidence_url"] = self.sources[source]["license_url"]
                self.save()
                print("verified existing", key, flush=True)
                return path
            self.failure(source, key, "existing_file_checksum_missing_or_changed", requested_url)
            return None
        start = time.monotonic()
        try:
            with self.session.request("POST" if data else "GET", url, params=params, data=data, auth=auth,
                                      headers=headers, stream=True, timeout=(20, 180 if data else 60)) as response:
                response.raise_for_status()
                length = int(response.headers.get("Content-Length", 0))
                if length > self.config["max_file_bytes"]:
                    raise ValueError(f"file exceeds configured size limit: {length} bytes")
                if path.is_relative_to(RAW) and self.raw_bytes + length > self.config["max_total_raw_bytes"]:
                    raise ValueError("total raw data budget would be exceeded")
                part = path.with_name(path.name + ".part")
                written = 0
                last_progress = time.monotonic()
                with part.open("wb") as out:
                    for block in response.iter_content(1024 * 1024):
                        if not block:
                            continue
                        written += len(block)
                        if written > self.config["max_file_bytes"] or time.monotonic() - start > 900:
                            raise ValueError("download exceeded size or 15-minute time budget")
                        if path.is_relative_to(RAW) and self.raw_bytes + written > self.config["max_total_raw_bytes"]:
                            raise ValueError("total raw data budget exceeded")
                        if shutil.disk_usage(ROOT).free < self.config["minimum_free_bytes"]:
                            raise ValueError("minimum disk reserve reached")
                        out.write(block)
                        if time.monotonic() - last_progress > 10:
                            print(f"downloading {key}: {written:,} bytes", flush=True)
                            last_progress = time.monotonic()
                if not written:
                    raise ValueError("empty response")
                if length and not response.headers.get("Content-Encoding") and length != written:
                    raise ValueError(f"Content-Length mismatch {length} != {written}")
                self.validate_format(part, kind)
                part.replace(path)
                asset = {"key": key, "source_id": source, "cohort": cohort, "path": relative(path),
                         "requested_url": requested_url, "resolved_url_without_query": public_url(response.url),
                         "method": "POST" if data else "GET", "request_body": data,
                         "acquired_at_utc": utc_now(), "bytes": written, "sha256": sha256(path),
                         "format": kind, "http_status": response.status_code,
                         "source_filename": Path(urlsplit(url).path).name,
                         "response_headers": {k: v for k, v in response.headers.items() if k.lower() in
                             {"content-type", "content-length", "etag", "last-modified", "content-encoding"}},
                         "license": self.sources[source]["license"],
                         "license_evidence_url": self.sources[source]["license_url"]}
                self.manifest["assets"][key] = asset
                if kind in {"zip", "xlsx"}:
                    with zipfile.ZipFile(path) as archive:
                        asset["archive_members"] = [{"name": x.filename, "uncompressed_bytes": x.file_size,
                            "compressed_bytes": x.compress_size, "crc32": f"{x.CRC:08x}"} for x in archive.infolist()]
                self.manifest["attempts"].append({"key": key, "source_id": source, "status": "downloaded", "at_utc": utc_now()})
                if path.is_relative_to(RAW):
                    self.raw_bytes += written
                self.save()
                print(f"downloaded {key}: {written:,} bytes", flush=True)
                return path
        except (requests.RequestException, ValueError, OSError, zipfile.BadZipFile, json.JSONDecodeError) as exc:
            part = path.with_name(path.name + ".part")
            if part.exists():
                part.unlink()  # Only this task's incomplete file, never a raw original.
            status = getattr(getattr(exc, "response", None), "status_code", None)
            # Exception URL strings may include signed redirect tokens: retain only safe details.
            detail = f"HTTP {status}" if status else (str(exc)[:400] if not isinstance(exc, requests.RequestException) else type(exc).__name__)
            self.failure(source, key, detail, requested_url, status)
            return None

    @staticmethod
    def validate_format(path, kind):
        with path.open("rb") as stream:
            prefix = stream.read(512).lstrip().lower()
        if kind in {"csv", "zip", "xlsx", "json"} and (prefix.startswith(b"<!doctype html") or prefix.startswith(b"<html")):
            raise ValueError("HTML/challenge response received instead of data; no bypass attempted")
        if kind in {"zip", "xlsx"}:
            with zipfile.ZipFile(path) as z:
                bad = z.testzip()
                if bad:
                    raise ValueError(f"ZIP CRC failure: {bad}")
                if not z.namelist():
                    raise ValueError("empty ZIP")
        elif kind == "json":
            obj = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(obj, dict) and (obj.get("error") or obj.get("remark")):
                raise ValueError("API returned error or partial-query remark")
        elif kind == "csv":
            if b"," not in prefix:
                raise ValueError("CSV header delimiter missing")

    def failure(self, source, key, detail, url=None, http_status=None):
        self.manifest["attempts"].append({"key": key, "source_id": source, "status": "failed_or_restricted",
            "at_utc": utc_now(), "detail": detail, "requested_url": url, "http_status": http_status})
        self.save()
        print("unavailable", key, detail, flush=True)

    def evidence(self, source, url, name=None, kind="document"):
        name = name or source + ".html"
        return self.download("evidence_" + Path(name).stem, source, url, META / "evidence" / name, kind)

    def inspect_sources(self):
        connectivity = []
        for source in self.sources.values():
            p = self.evidence(source["id"], source["url"])
            source["landing_page_status"] = "retrieved" if p else "failed_or_restricted"
            connectivity.append({"source_id": source["id"], "url": source["url"], "success": bool(p)})
        write_json(META / "connectivity.json", {"checked_at_utc": utc_now(), "internet_available": any(x["success"] for x in connectivity), "probes": connectivity})
        self.save()

    def dft(self):
        page = META / "evidence" / "dft.html"
        if not page.exists():
            return
        text = page.read_text(encoding="utf-8")
        year = self.config["dft_year"]
        links = re.findall(r'href="([^\"]+)"[^>]*>([^<]+)', text)
        for label, singular in [("Collisions", "collision"), ("Vehicles", "vehicle"), ("Casualties", "casualty")]:
            found = [url for url, title in links if f"{label} - {year}" in title]
            if found:
                self.download(f"dft_{singular}_{year}", "dft", found[0], RAW / "dft" / f"{singular}_{year}.csv", "csv", cohort=f"gb_{year}")
            else:
                self.failure("dft", f"dft_{singular}_{year}", "year link not found on official source")
        guide = [url for url, title in links if "Open dataset data guide" in title]
        if guide:
            self.download("dft_data_guide", "dft", guide[0], RAW / "dft" / "data_guide.xlsx", "xlsx", cohort="documentation")
        self.sources["dft"]["selected_period"] = str(year)
        self.sources["dft"]["scope_note"] = "Complete selected annual tables. Full 1979-latest and overlapping multi-year extracts are inventoried on the source page but not downloaded; bounded disk budget."
        self.evidence("dft", self.sources["dft"]["license_url"], "dft_license.html")

    def cambridge(self):
        page = META / "evidence" / "cambridge.html"
        if not page.exists():
            return
        text = page.read_text(encoding="utf-8")
        links = re.findall(r'href="([^\"]*bitstreams/[^\"]+/download)"', text)
        if links:
            self.download("cambridge_sites", "cambridge", urljoin(self.sources["cambridge"]["url"], links[0]),
                          RAW / "cambridge" / "final_dataset.csv", "csv", cohort="england_wales_static")
        else:
            self.failure("cambridge", "cambridge_sites", "bitstream not found")
        # Apollo exposes the metadata date in HTML meta tags; retain its exact values.
        self.sources["cambridge"]["citation_metadata"] = re.findall(r'<meta[^>]+name="(citation_[^\"]+)"[^>]+content="([^\"]*)"', text)
        self.sources["cambridge"]["temporal_note"] = "Static published research inventory; per-site observation/effective dates are not supplied. Publication date is not a measurement date."

    @staticmethod
    def kaggle_credentials():
        token = os.getenv("KAGGLE_API_TOKEN")
        if token:
            return None, {"Authorization": "Bearer " + token}
        if os.getenv("KAGGLE_USERNAME") and os.getenv("KAGGLE_KEY"):
            return (os.environ["KAGGLE_USERNAME"], os.environ["KAGGLE_KEY"]), None
        cred = Path(os.getenv("KAGGLE_CONFIG_DIR", str(Path.home() / ".kaggle"))) / "kaggle.json"
        if cred.is_file():
            obj = json.loads(cred.read_text(encoding="utf-8"))
            return (obj["username"], obj["key"]), None
        return None, None

    def kaggle(self, source, ref, search):
        meta = self.download(source + "_catalog", source, "https://www.kaggle.com/api/v1/datasets/list",
                             META / "evidence" / (source + "_catalog.json"), "json", params={"search": search})
        item = next((x for x in read_json(meta, []) if x.get("ref") == ref), None) if meta else None
        if item:
            self.sources[source]["license"] = item.get("licenseName", "Unknown")
            self.sources[source]["catalog_metadata"] = {k: item.get(k) for k in ["ref", "title", "totalBytes", "lastUpdated", "licenseName"]}
        if source == "porto":
            self.sources[source]["reuse_gate"] = "QUARANTINED until an explicit data license/permission is verified; Kaggle Unknown is not a license."
        auth, headers = self.kaggle_credentials()
        result = self.download(source + "_archive", source, "https://www.kaggle.com/api/v1/datasets/download/" + ref,
                               RAW / source / "dataset.zip", "zip", auth=auth, headers=headers,
                               cohort="porto_taxi" if source == "porto" else "brazil_olist")
        self.sources[source]["download_status"] = "downloaded" if result else "unavailable_or_restricted"
        self.sources[source]["credential_configured"] = bool(auth or headers)
        if not result:
            self.sources[source]["next_step"] = "Configure Kaggle credentials locally and rerun --only " + source + "; accept any source access rules in your own account. Never put secrets in reports or chat."

    def nyc(self):
        repo = "https://api.github.com/repos/walterwzhang/NYC-Taxi-2013-Data"
        p = self.evidence("nyc", repo, "nyc_repository.json", "json")
        repository = read_json(p, {}) if p else {}
        commit_path = self.evidence("nyc", repo + "/commits/master", "nyc_commit.json", "json")
        commit = read_json(commit_path, {}).get("sha") if commit_path else "master"
        tree = self.evidence("nyc", repo + "/git/trees/" + commit + "?recursive=1", "nyc_tree.json", "json")
        tree_obj = read_json(tree, {}) if tree else {}
        self.sources["nyc"]["repository_license_metadata"] = repository.get("license")
        self.sources["nyc"]["repository_commit"] = commit
        self.sources["nyc"]["repository_assets"] = [{"path": t["path"], "bytes": t.get("size")} for t in tree_obj.get("tree", []) if t.get("type") == "blob"]
        self.evidence("nyc", "https://raw.githubusercontent.com/walterwzhang/NYC-Taxi-2013-Data/" + commit + "/README.md", "nyc_readme.md")
        # Public originals are retained for inspection, with an explicit reuse quarantine.
        for entry in tree_obj.get("tree", []):
            name = entry["path"]
            if name.startswith("Medallion-Samples/") and name.endswith(".csv"):
                self.download("nyc_" + Path(name).stem, "nyc",
                              "https://raw.githubusercontent.com/walterwzhang/NYC-Taxi-2013-Data/" + commit + "/" + quote(name),
                              RAW / "nyc" / Path(name).name, "csv", cohort="nyc_2013_quarantined")
        self.evidence("nyc", "https://public-data.chicagobooth.edu/oeystein-daljord/NYC-2013-Taxi-Data-Balanced/", "nyc_balanced_panel_host.html")
        self.sources["nyc"]["reuse_gate"] = "QUARANTINED: no explicit repository data reuse license identified. Public accessibility does not establish permission."
        self.sources["nyc"]["temporal_note"] = "Repository describes 2013; supplied mapping and sample ID CSVs may have no timestamps and are not the balanced-panel operational records."

    def osm(self):
        bbox = ",".join(map(str, self.config["osm_bbox_south_west_north_east"]))
        snapshot = self.config["osm_snapshot_utc"]
        query = f'[out:json][timeout:150][date:"{snapshot}"];way["highway"~"^(motorway|trunk|primary|secondary|tertiary|unclassified|residential|service|living_street|motorway_link|trunk_link|primary_link|secondary_link|tertiary_link)$"]({bbox});(._;>;);out meta;'
        qpath = ROOT / "config" / "osm_query.overpassql"
        qpath.write_text(query + "\n", encoding="utf-8")
        self.download("osm_birmingham_2024", "osm", self.config["overpass_endpoint"], RAW / "osm" / "birmingham_2024-01-01.json",
                      "json", data={"data": query}, cohort="birmingham_2024")
        for id_ in ["osm", "overpass"]:
            self.sources[id_]["actual_data_asset"] = "osm_birmingham_2024"
            self.sources[id_]["requested_snapshot_utc"] = snapshot
            self.sources[id_]["bbox_south_west_north_east"] = self.config["osm_bbox_south_west_north_east"]
            self.sources[id_]["limitations"] = "Road geometry only. HGV restrictions, turn restrictions, road speeds and completeness require validation. Ways intersecting bbox can extend beyond it."
        self.evidence("osm", "https://www.openstreetmap.org/copyright", "osm_license.html")

    def weather(self):
        self.download("weather_birmingham_2024", "weather", "https://archive-api.open-meteo.com/v1/archive",
                      RAW / "weather" / "birmingham_era5_2024.json", "json", params=self.config["weather"], cohort="birmingham_2024")
        self.evidence("weather", "https://open-meteo.com/en/docs/historical-weather-api", "weather_archive_docs.html")
        self.evidence("weather", "https://open-meteo.com/en/licence", "weather_license.html")
        self.evidence("weather", "https://open-meteo.com/en/terms", "weather_terms.html")
        self.sources["weather"]["request_parameters"] = self.config["weather"]
        self.sources["weather"]["limitations"] = "One requested point, not GB-wide weather. Reanalysis can contain information unavailable at prediction time; not a forecast feature without availability-time controls."

    def traccar(self):
        self.evidence("traccar", "https://www.traccar.org/api-reference/", "traccar_api.html")
        self.evidence("traccar", "https://raw.githubusercontent.com/traccar/traccar/master/openapi.yaml", "traccar_openapi.yaml")
        self.evidence("traccar", self.sources["traccar"]["license_url"], "traccar_software_license.txt")
        self.sources["traccar"]["download_status"] = "no_public_fleet_dataset"
        self.sources["traccar"]["missing_requirements"] = "Authorized server URL, account/token, permitted device IDs, time range and fleet-data consent/license. Demo records are excluded from research data."
        spec_path = META / "evidence" / "traccar_openapi.yaml"
        if spec_path.exists():
            spec = spec_path.read_text(encoding="utf-8")
            version = re.search(r"version: '([^']+)'", spec)
            self.sources["traccar"]["api_contract"] = {"server_url": "User-supplied authorized server; none supplied",
                "api_version_in_downloaded_contract": version.group(1) if version else None,
                "endpoints": ["GET /api/positions", "GET /api/reports/route?deviceId=...&from=...&to=..."],
                "authentication": ["HTTP Basic", "Bearer API key"],
                "route_report_schema": "array of Position objects; schema is not acquired fleet records",
                "speed_unit": "knots (per Position schema)",
                "data_size_and_period": "Unavailable until authorized server/devices/time window are provided"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", nargs="+", choices=["dft", "cambridge", "porto", "olist", "nyc", "osm", "weather", "traccar"])
    args = parser.parse_args()
    acquisition = Acquisition(read_json(CONFIG))
    # Preserve source discoveries across partial reruns.
    existing_sources = read_json(META / "source_inventory.json", [])
    if args.only and existing_sources:
        acquisition.sources.update({x["id"]: x for x in existing_sources})
    else:
        acquisition.inspect_sources()
    tasks = {"dft": acquisition.dft, "cambridge": acquisition.cambridge,
             "porto": lambda: acquisition.kaggle("porto", "crailtap/taxi-trajectory", "taxi-trajectory"),
             "olist": lambda: acquisition.kaggle("olist", "olistbr/brazilian-ecommerce", "brazilian-ecommerce"),
             "nyc": acquisition.nyc, "osm": acquisition.osm, "weather": acquisition.weather, "traccar": acquisition.traccar}
    for name in args.only or tasks:
        print("acquiring source", name, flush=True)
        try:
            tasks[name]()
        except (ValueError, OSError, KeyError) as exc:
            acquisition.failure(name, name + "_discovery", str(exc)[:400])
        acquisition.save()
    print("Acquisition finished. Inspect source_inventory.json and manifest.json for restrictions and failures.", flush=True)


if __name__ == "__main__":
    main()
