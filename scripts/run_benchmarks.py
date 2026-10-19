"""Execute the declared paired simulation protocol through persistent backend jobs.

Resumes already submitted jobs using its acquisition journal. Never modifies the
live simulator or historical cohorts. Raw successful job exports are preserved.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time
import urllib.request

from benchmark_statistics import METRICS, summarize

ROOT = Path(__file__).resolve().parents[1]


def request(base, path, body=None, raw=False):
    data = None if body is None else json.dumps(body, allow_nan=False).encode()
    req = urllib.request.Request(base + path, data=data, headers={"Content-Type": "application/json"} if data else {})
    with urllib.request.urlopen(req, timeout=120) as response:
        content = response.read()
    return content if raw else json.loads(content)


def write_json(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(content, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8080/api")
    parser.add_argument("--protocol", type=Path, default=ROOT / "config/benchmark_protocol.json")
    parser.add_argument("--output", type=Path, default=ROOT / "reports")
    parser.add_argument("--poll-seconds", type=float, default=3)
    parser.add_argument("--retry-failed", action="store_true", help="Archive and retry each saved failed job once, with exactly the same declared request")
    args = parser.parse_args()
    protocol_bytes = args.protocol.read_bytes()
    protocol = json.loads(protocol_bytes)
    digest = hashlib.sha256(protocol_bytes).hexdigest()
    journal_path = args.output / "benchmark_execution_journal.json"
    if journal_path.exists():
        journal = json.loads(journal_path.read_text(encoding="utf-8"))
        if journal["protocolSha256"] != digest:
            raise RuntimeError("Protocol changed: choose a new output directory to preserve prior experiment evidence")
    else:
        journal = {"startedAtUtc": datetime.now(timezone.utc).isoformat(), "protocolSha256": digest, "jobs": {}}
        write_json(journal_path, journal)
    catalog = request(args.base_url, "/benchmarks/catalog")
    live_before = request(args.base_url, "/state")
    all_jobs, rows = [], []
    raw_dir = args.output / "benchmark_raw"
    raw_dir.mkdir(exist_ok=True)
    for case in protocol["cases"]:
        for mode in protocol["comparisons"]:
            key = case["profile"] + ":" + mode
            body = {"parameters": {**protocol["commonParameters"], **case["parameters"], "profile": case["profile"], "seeds": protocol["seeds"]},
                    "policies": protocol["policyIds"], "comparisonMode": mode,
                    "ablations": protocol["fullComparisonAblations"] if mode == "FULL" else ["FULL"]}
            if key not in journal["jobs"]:
                job = request(args.base_url, "/benchmarks/runs", body)
                journal["jobs"][key] = {"id": job["id"], "request": body}
                write_json(journal_path, journal)
            entry = journal["jobs"][key]
            print(f"RUN {key} job={entry['id']}", flush=True)
            last_progress = None
            retried = False
            while True:
                job = request(args.base_url, "/benchmarks/runs/" + entry["id"])
                progress = (job["status"], job["completedRuns"], job["totalRuns"])
                if progress != last_progress:
                    print(f"  {progress[0]} {progress[1]}/{progress[2]}", flush=True)
                    last_progress = progress
                if job["status"] == "FAILED":
                    failed_path = raw_dir / (entry["id"] + "_failed.json")
                    if not failed_path.exists():
                        write_json(failed_path, job)
                    if args.retry_failed and not retried:
                        entry.setdefault("failedAttempts", []).append({"id": entry["id"], "completedRuns": job["completedRuns"],
                            "error": job["error"], "rawJson": failed_path.relative_to(ROOT).as_posix(),
                            "rawSha256": hashlib.sha256(failed_path.read_bytes()).hexdigest()})
                        replacement = request(args.base_url, "/benchmarks/runs", body)
                        entry["id"] = replacement["id"]
                        write_json(journal_path, journal)
                        print(f"  RETRY same declared inputs job={entry['id']}; failed attempt retained", flush=True)
                        retried = True
                        last_progress = None
                        continue
                    raise RuntimeError(f"Declared case unavailable: {key}: {job['error']}. No substitute outcomes written.")
                if job["status"] == "COMPLETED":
                    break
                time.sleep(args.poll_seconds)
            raw_path = raw_dir / (entry["id"] + ".json")
            if not raw_path.exists():
                raw_path.write_bytes(request(args.base_url, f"/benchmarks/runs/{entry['id']}/export?format=json", raw=True))
                (raw_dir / (entry["id"] + ".csv")).write_bytes(request(args.base_url, f"/benchmarks/runs/{entry['id']}/export?format=csv", raw=True))
            actual = json.loads(raw_path.read_text(encoding="utf-8"))
            if actual["request"] != body:
                raise RuntimeError("Persisted request differs from declared paired protocol")
            if actual["graphSha256"] != catalog["graphSha256"]:
                raise RuntimeError("Saved benchmark uses a different immutable road graph")
            result = actual["result"]
            scenarios = {s["id"]: s for s in result["scenarios"]}
            expected_policies = set(body["policies"]) | {"B4_" + name for name in body["ablations"] if name != "FULL"}
            expected_pairs = {(seed, policy) for seed in protocol["seeds"] for policy in expected_policies}
            actual_pairs = [(run["seed"], run["policyId"]) for run in result["runs"]]
            if len(scenarios) != len(protocol["seeds"]) or set(actual_pairs) != expected_pairs or len(actual_pairs) != len(expected_pairs):
                raise RuntimeError("Completed job lacks the exact declared seed/policy outcomes")
            for run in result["runs"]:
                scenario = scenarios[run["scenarioId"]]
                if run["inputFingerprint"] != scenario["inputFingerprint"]:
                    raise RuntimeError("Policy input fingerprint changed")
                rows.append({"jobId": entry["id"], "scenarioId": run["scenarioId"], "profile": scenario["profile"], "seed": run["seed"],
                    "futureMlPartition": "reserved_assessment" if run["seed"] in protocol["futureMlPartition"]["reservedAssessmentSeeds"] else "development",
                    "policyId": run["policyId"], "comparisonMode": mode, "inputFingerprint": run["inputFingerprint"],
                    **run["metrics"], "constraintRejections": run["finalSummary"].get("constraintRejections", 0),
                    "decisionLimitReached": run["finalSummary"].get("decisionLimitReached", False)})
            all_jobs.append({"id": entry["id"], "case": key, "rawJson": raw_path.relative_to(ROOT).as_posix(),
                "rawSha256": hashlib.sha256(raw_path.read_bytes()).hexdigest(), "runCount": len(result["runs"]),
                "scenarios": result["scenarios"]})
    # FULL versus EQUAL_ACTIONS use the same inputs as well as paired policies.
    fingerprints = {}
    for row in rows:
        key = (row["profile"], row["seed"])
        if key in fingerprints and fingerprints[key] != row["inputFingerprint"]:
            raise RuntimeError("Comparison mode changed the scenario rather than its allowed actions")
        fingerprints[key] = row["inputFingerprint"]
    stats = summarize(rows, bootstrap_samples=protocol["analysis"]["bootstrapSamples"], bootstrap_seed=protocol["analysis"]["bootstrapSeed"])
    live_after = request(args.base_url, "/state")
    retained = ("runId", "scenarioId", "initialOperations", "commandHistory", "replaying")
    if any(live_before[k] != live_after[k] for k in retained) or [t["initialAssignment"] for t in live_before["trucks"]] != [t["initialAssignment"] for t in live_after["trucks"]]:
        raise RuntimeError("Benchmark altered live assignments or commands")
    if live_before["status"] in ("PAUSED", "DRAFT", "COMPLETED") and live_before != live_after:
        raise RuntimeError("Stationary live state changed during isolated benchmark execution")
    output = {"schemaVersion": "cascadeshield.benchmark-results/1.0", "completedAtUtc": datetime.now(timezone.utc).isoformat(),
              "provenance": "SIMULATED_RESEARCH_EXPERIMENT", "protocolSha256": digest, "protocol": protocol,
              "catalog": catalog, "jobs": all_jobs, "rowCount": len(rows), "scenarioCount": len(fingerprints),
              "failedAttempts": [attempt for entry in journal["jobs"].values() for attempt in entry.get("failedAttempts", [])],
              "liveStatePreserved": True, "rows": rows, "statistics": stats, "trainedModel": False, "autonomousLlm": False}
    write_json(args.output / "BENCHMARK_RESULTS.json", output)
    with (args.output / "BENCHMARK_RESULTS.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)
    journal["completedAtUtc"] = output["completedAtUtc"]
    journal["rowCount"] = len(rows)
    write_json(journal_path, journal)
    print(f"COMPLETE {len(rows)} executed policy rows, {len(fingerprints)} paired scenarios; live state preserved", flush=True)


if __name__ == "__main__": main()
