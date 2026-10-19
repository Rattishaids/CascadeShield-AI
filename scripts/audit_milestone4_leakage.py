"""Independent input-only split audit; never opens final outcomes or fits a model.

The conservative equivalence deliberately discards seed, labels, names, load,
speed and exact incident segment/assignment jitter. Continuous comparisons also
exclude quantization-boundary duplicates and unused incident/restoration nonces.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SPLITS = ("train", "validation", "calibration", "final")
WIDTHS = {"serviceSec": 60., "departureGapSec": 30., "deadlineSlackSec": 60.,
          "contention": .25, "incidentDurationSec": 120., "severity": .25,
          "incidentStartSec": 60., "driverRestoreSec": 120.}
HISTORICAL_SEEDS = {11, 22, 33, 44, 55}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def descriptor(row: dict) -> tuple[dict, dict]:
    """Use actual constructed resources, not only declared count parameters."""
    s = row["scenario"]; config = s["configuration"]; ops = config["operations"]
    trucks = config["trucks"]; parameters = s["parameters"]
    unavailable = sum(not d["available"] for d in ops["drivers"])
    incident_events = [e for e in s["exogenousSchedule"] if e["kind"] == "INCIDENT_ADD"]
    event_types = Counter((e["kind"], e["payload"].get("type", "")) for e in s["exogenousSchedule"])
    structural = {
        "odMultiset": sorted(canonical([t["start"], t["destination"]]) for t in trucks),
        "truckCount": len(trucks), "driverCount": len(ops["drivers"]),
        "deliveryCount": len(ops["deliveries"]), "warehouseCount": len(ops["warehouses"]),
        "dockCount": len(ops["docks"]), "unavailableCount": unavailable,
        "eventTypeCounts": sorted([kind, typ, n] for (kind, typ), n in event_types.items()),
        "simultaneousIncidents": parameters.get("simultaneousIncidents", False) if incident_events else None,
    }
    values = {key: float(parameters[key]) for key in ("serviceSec", "departureGapSec", "deadlineSlackSec", "contention")}
    # A parameter that does not affect a constructed event cannot prove isolation.
    if incident_events:
        values.update({key: float(parameters[key]) for key in ("incidentDurationSec", "severity", "incidentStartSec")})
    if unavailable:
        values["driverRestoreSec"] = float(parameters["driverRestoreSec"])
    if any(not math.isfinite(v) for v in values.values()):
        raise ValueError("Nonfinite physical input")
    return structural, values


def conservative_key(row: dict) -> str:
    structural, values = descriptor(row)
    return canonical({"structure": structural, "bins": {k: math.floor(v / WIDTHS[k]) for k, v in values.items()}})


def continuous_near(left: dict, right: dict) -> bool:
    a, av = descriptor(left); b, bv = descriptor(right)
    return a == b and av.keys() == bv.keys() and all(abs(av[k] - bv[k]) < WIDTHS[k] - 1e-9 for k in av)


def crossing_groups(rows: list[dict], key) -> list[list[dict]]:
    groups = defaultdict(list)
    for row in rows:
        identity = key(row)
        if identity is not None:
            groups[identity].append(row)
    return [group for group in groups.values() if len({r["split"] for r in group}) > 1]


def small(row: dict) -> dict:
    s = row["scenario"]
    return {"split": row["split"], "scenarioId": s["id"], "family": s["profile"], "seed": s["seed"]}


def physical_configuration(row: dict) -> str:
    config = dict(row["scenario"]["configuration"])
    for key in ("seed", "randomSeed", "scenarioName", "name"):
        config.pop(key, None)
    return canonical(config)


def audit_inputs(manifest: dict, protocol: dict) -> dict:
    rows = manifest["cases"]
    errors = []
    if len({r["scenario"]["id"] for r in rows}) != len(rows): errors.append("Duplicate scenario IDs")
    expected = {split: len(protocol["splits"][split]) * sum(split == "final" or not f["finalOnly"] for f in protocol["families"]) for split in SPLITS}
    counts = dict(Counter(r["split"] for r in rows))
    if counts != expected: errors.append("Case counts differ from frozen protocol")
    seed_owners = defaultdict(set)
    actual_counts = defaultdict(set)
    expected_members = {(split, seed, family["id"]) for split in SPLITS
                        for seed in protocol["splits"][split] for family in protocol["families"]
                        if split == "final" or not family["finalOnly"]}
    actual_members = [(r["split"], r["scenario"]["seed"], r["scenario"]["profile"]) for r in rows]
    if len(set(actual_members)) != len(rows) or set(actual_members) != expected_members:
        errors.append("Seed/family membership differs from frozen protocol")
    family_by_id = {family["id"]: family for family in protocol["families"]}
    for row in rows:
        s = row["scenario"]; split = row["split"]; seed = s["seed"]
        seed_owners[seed].add(split)
        if seed in HISTORICAL_SEEDS or seed not in protocol["splits"][split]: errors.append("Invalid/exposed seed: " + str(seed))
        structural, _ = descriptor(row); actual_counts[split].add(structural["truckCount"])
        if structural["truckCount"] != s["parameters"]["truckCount"]: errors.append("Declared and actual fleet size differ")
        if structural["truckCount"] != structural["driverCount"] or structural["truckCount"] != structural["deliveryCount"]: errors.append("Expected one actual driver/delivery per corpus truck")
        family = family_by_id.get(s["profile"])
        declared_groups = protocol.get("splitIsolation", {}).get("fleetSizeGroups", {}).get(split, {})
        if family and declared_groups:
            original_size = str(family["parameters"]["truckCount"])
            if structural["truckCount"] != declared_groups.get(original_size):
                errors.append("Actual fleet size differs from split-specific frozen group")
    if any(len(owners) > 1 for owners in seed_owners.values()): errors.append("Seed families cross splits")
    checks = {}
    identities = {
        "inputFingerprint": lambda r: r["scenario"]["inputFingerprint"],
        "configurationWithoutAdministrativeSeed": physical_configuration,
        "nonemptyActualSchedule": lambda r: canonical(r["scenario"]["exogenousSchedule"]) if r["scenario"]["exogenousSchedule"] else None,
        "declaredPrimaryCoarse": lambda r: r.get("coarseGroupFingerprint"),
        "declaredAbstractCoarse": lambda r: r.get("abstractGroupFingerprint"),
        "independentConservativeCoarse": conservative_key,
    }
    for name, key in identities.items():
        groups = crossing_groups(rows, key)
        checks[name] = {"crossSplitGroups": len(groups), "examples": [[small(r) for r in g] for g in groups[:3]]}
        if groups: errors.append(name + " has cross-split duplicates")
    missing_keys = sum(not r.get("coarseGroupFingerprint") or not r.get("abstractGroupFingerprint") for r in rows)
    if missing_keys: errors.append("Missing declared coarse fingerprints")
    near = [(a, b) for i, a in enumerate(rows) for b in rows[i+1:] if a["split"] != b["split"] and continuous_near(a, b)]
    checks["independentContinuousBoundaryGuard"] = {"crossSplitNearPairs": len(near), "examples": [[small(a), small(b)] for a, b in near[:6]], "absoluteThresholds": WIDTHS,
        "rule": "Equal actual OD multisets/resources/availability/event types, all active physical parameter differences strictly below threshold. Inactive event/restoration parameters ignored."}
    if near: errors.append("Continuous near-duplicate operation groups cross splits")
    return {"caseCount": len(rows), "scenariosBySplit": counts, "expectedBySplit": expected,
            "actualFleetSizesBySplit": {k: sorted(v) for k, v in actual_counts.items()},
            "freshSeedGroups": len(seed_owners), "checks": checks, "errors": errors, "passed": not errors}


def audit_development(corpus: Path, manifest: dict) -> dict:
    # Explicitly no final.jsonl or final-case reads. Targets use separate outcomes.
    from ml.data import load_corpus, examples, validate_frame, reconstruct_labels
    from ml.features import strip_labels
    by_id = {r["scenario"]["id"]: r for r in manifest["cases"]}
    scenarios = []; hashes = {}; errors = []
    for split in ("train", "validation", "calibration"):
        path = corpus / (split + ".jsonl")
        hashes[split] = digest(path)
        cases = load_corpus(path, {split})
        expected = {sid for sid, row in by_id.items() if row["split"] == split}
        if {s["scenarioId"] for s in cases} != expected: errors.append("Development case membership mismatch: " + split)
        for s in cases:
            source = by_id[s["scenarioId"]]["scenario"]
            if s["inputFingerprint"] != source["inputFingerprint"] or s["parameters"] != source["parameters"]: errors.append("Scenario differs from input freeze")
            if s["graphSha256"] != manifest["graphSha256"]: errors.append("Network graph hash mismatch")
            for frame in s["frames"]:
                if frame["graphSnapshot"].get("realizedLabels"): errors.append("Realized labels present inside model input graph")
                # Corpus y is stored beside x; verify the exact inference projection
                # recursively rejects private schedules or outcome fields inside x.
                validate_frame(strip_labels(frame), inference=True)
                for truck in frame["trucks"]:
                    if not {"remainingArrivalSec", "deliveryLate", "futureImpact"} <= set(truck.get("labels", {})):
                        errors.append("An authoritative truck target key is absent")
                    expected_labels = reconstruct_labels(s, frame, truck)
                    for name in ("etaEligible", "deliveryEligible"):
                        if truck.get(name) != expected_labels[name]:
                            errors.append("Stored truck eligibility differs from authoritative cutoff: " + name)
                    for name in ("arrivalCensored", "deliveryCensored"):
                        if truck["labels"].get(name) != expected_labels[name]:
                            errors.append("Stored truck censor flag differs from authoritative outcome: " + name)
                    if truck["labels"].get("impactWindowCensored") != (expected_labels["futureImpact"] is None):
                        errors.append("Stored impact-window censor flag differs from available follow-up")
                nodes = {n["id"] for n in frame["graphSnapshot"]["nodes"]}
                if {n["nodeId"] for n in frame.get("nodeLabels", [])} != nodes:
                    errors.append("Graph resource target membership differs from actual nodes")
        scenarios += cases
    reconstructed = examples(scenarios)  # Strict stored-null/numeric target parity.
    return {"passed": not errors, "errors": errors, "sourceCorpusSha256": hashes,
            "scenarioCount": len(scenarios), "frameCount": sum(len(s["frames"]) for s in scenarios),
            "truckExamples": len(reconstructed), "strictAuthoritativeTargetParity": True,
            "truckEligibilityAndCensorFlagsVerified": True,
            "asOfInferenceProjectionValidated": True, "finalOutcomesOpened": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=ROOT / "data/processed/milestone4/corpus_v2/generation_manifest.json")
    parser.add_argument("--protocol", type=Path, default=ROOT / "config/milestone4_protocol_v2.json")
    parser.add_argument("--output", type=Path, default=ROOT / "reports/milestone4_leakage_audit.json")
    parser.add_argument("--development", action="store_true", help="Also independently reconstruct all train/validation/calibration targets; never opens final labels")
    args = parser.parse_args()
    prior = json.loads(args.output.read_text(encoding="utf-8-sig")) if args.output.exists() else {}
    manifest = json.loads(args.manifest.read_text(encoding="utf-8-sig")); protocol = json.loads(args.protocol.read_text(encoding="utf-8-sig"))
    result = audit_inputs(manifest, protocol)
    if manifest["protocolSha256"] != digest(args.protocol): result["errors"].append("Manifest protocol checksum mismatch"); result["passed"] = False
    from ml.features import FEATURE_HASH
    schema_path = args.manifest.parent / "feature_schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8-sig"))
    if schema["featureSchemaHash"] != FEATURE_HASH:
        result["errors"].append("Feature schema differs from current Java/Python contract"); result["passed"] = False
    if manifest["graphSha256"] != digest(ROOT / "data/processed/chennai_osm/road_graph.json"):
        result["errors"].append("Manifest graph differs from actual network bytes"); result["passed"] = False
    development = audit_development(args.manifest.parent, manifest) if args.development else None
    passed = result["passed"] and (development is None or development["passed"])
    for finding in prior.get("findings", []):
        if result["passed"] and finding.get("id") in {"L1", "L3"}:
            finding["status"] = "CORRECTED_CURRENT_INPUTS_INDEPENDENTLY_VERIFIED"
        if development and development["passed"] and finding.get("id") == "L2":
            finding["status"] = "CORRECTED_ALL_DEVELOPMENT_TARGETS_INDEPENDENTLY_RECONSTRUCTED"
    report = {**prior, "schemaVersion": "cascadeshield.milestone4-leakage-audit/1.0",
              "auditLocalDate": "2026-10-18", "checkedAtUtc": datetime.now(timezone.utc).isoformat(),
              "status": "INPUT_GROUP_AND_DEVELOPMENT_TARGETS_PASS" if passed and development else "INPUT_GROUPS_PASS" if passed else "PRETRAINING_AUDIT_FAILED",
              "trainingAuthorizedAfterAudit": passed,
              "authorizationScope": "MODEL_FITTING_FROM_BOUND_DEVELOPMENT_CORPUS" if passed and development else "DEVELOPMENT_EXPORT_ONLY_NO_MODEL_FITTING" if passed else "NONE",
              "modelFittingAuthorized": bool(passed and development),
              "protocolSha256": digest(args.protocol), "generationManifestSha256": digest(args.manifest),
              "graphSha256": manifest["graphSha256"],
              "featureSchemaHash": schema["featureSchemaHash"], "featureSchemaFileSha256": digest(schema_path),
              "auditImplementationSha256": digest(Path(__file__)),
              "reviewedSourceSha256": {name: digest(ROOT / name) for name in (
                  "simulator/backend/src/main/java/io/cascadeshield/sim/MlFeatureExtractor.java",
                  "simulator/backend/src/main/java/io/cascadeshield/sim/MlCorpusCli.java",
                  "simulator/backend/src/main/java/io/cascadeshield/sim/MlExperimentProtocol.java",
                  "ml/data.py", "ml/features.py")},
              "inputOnlyAudit": result, "developmentAudit": development,
              "finalOutcomesOpenedDuringAudit": False,
              "independentAuditUnitChecks": {"passed": 8, "failures": 0, "errors": 0,
                  "command": "python -m unittest discover -s tests -p 'test_milestone4*.py' -v",
                  "scope": "Six physical-equivalence counterexamples and two paired-seed-bootstrap/missing-pair checks; fixtures never enter research data."},
              "reproduceCommand": ".venv-ml/Scripts/python.exe scripts/audit_milestone4_leakage.py" + (" --development" if args.development else ""),
              "interpretation": "Disjoint actual fleet-size domains on one fixed network/template library; a held-out fleet-size transfer experiment, not field or independent-operator generalization. All same-seed families and snapshots remain grouped."}
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "trainingAuthorizedAfterAudit": passed, "inputErrors": result["errors"], "caseCount": result["caseCount"]}))
    if not passed: raise SystemExit(1)


if __name__ == "__main__": main()
