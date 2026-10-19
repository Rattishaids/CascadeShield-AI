"""Run offline policy experiments with an immutable executable/source freeze.

Use ``policies --freeze-only`` before final label generation. Subsequent runs
refuse source, class, data, model-selection or wrapper drift; interrupted rows
are reused only under exactly the same freeze. No live application API is used.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import urllib.request

from run_milestone4_experiments import ROOT, docker_base, execute


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def project_path(value: str) -> Path:
    path = (ROOT / value).resolve()
    if not path.is_relative_to(ROOT.resolve()):
        raise ValueError(f"Path must stay inside the mounted project: {path}")
    return path


def mounted(path: Path) -> str:
    return "/workspace/" + path.relative_to(ROOT).as_posix()


def verify_bundle(manifest_path: Path) -> dict:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("frozen") is not True or not manifest.get("validatedModelIds") or not manifest.get("artifactSha256"):
        raise ValueError("A real frozen model bundle with validated models/artifacts is required")
    for name, expected in manifest["implementationSha256"].items():
        path = project_path(name)
        if not path.is_file() or digest(path) != expected:
            raise ValueError("Model-bound implementation changed: " + name)
    for name, expected in manifest["artifactSha256"].items():
        path = (manifest_path.parent / name).resolve()
        if not path.is_relative_to(manifest_path.parent.resolve()) or not path.is_file() or digest(path) != expected:
            raise ValueError("Model artifact changed: " + name)
    return manifest


def freeze_payload(mode: str, protocol: Path, corpus: Path, selection: Path) -> dict:
    files = [*ROOT.glob("simulator/backend/src/main/java/**/*.java"),
             *ROOT.glob("simulator/backend/target/classes/**/*.class"),
             *ROOT.glob("ml/*.py"), ROOT / "scripts/run_milestone4_experiments.py",
             ROOT / "scripts/run_milestone4_java.sh", Path(__file__),
             ROOT / "simulator/backend/pom.xml", ROOT / "simulator/backend/target/ml-classpath.txt"]
    if not list(ROOT.glob("simulator/backend/target/classes/**/MlPolicyCli.class")):
        raise ValueError("Compile and test the actual Java source tree before freezing policy execution")
    result = {"schemaVersion": "cascadeshield.milestone4-policy-implementation-freeze/1.0",
              "mode": mode, "protocolSha256": digest(protocol),
              "graphSha256": digest(ROOT / "data/processed/chennai_osm/road_graph.json"),
              "generationManifestSha256": digest(corpus / "generation_manifest.json"),
              "sourceFeatureSchemaSha256": digest(corpus / "feature_schema.json"),
              "sourceCorpusSha256": {s: digest(corpus / (s + ".jsonl")) for s in ("train", "validation", "calibration")},
              "sourceAndExecutableSha256": {p.relative_to(ROOT).as_posix(): digest(p) for p in sorted(set(files))},
              "provenance": "EXECUTED_SIMULATION_IMPLEMENTATION_FREEZE",
              "rule": "All resumed rows must share these exact protocol, model, source and compiled bytes. No post-assessment changes or silent row replacement."}
    if mode == "policies":
        bundle = verify_bundle(selection)
        if bundle["protocolSha256"] != result["protocolSha256"] or bundle["sourceCorpusSha256"] != result["sourceCorpusSha256"]:
            raise ValueError("Frozen model selection does not bind this exact protocol/development corpus")
        result["selectionManifestSha256"] = digest(selection)
        result["validatedModelIds"] = bundle["validatedModelIds"]
    return result


def immutable_freeze(path: Path, payload: dict) -> None:
    if path.exists():
        if json.loads(path.read_text(encoding="utf-8")) != payload:
            raise ValueError(f"Execution implementation drift; preserve existing evidence and choose a new experiment version: {path}")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x", encoding="utf-8") as stream:
            stream.write(json.dumps(payload, sort_keys=True, indent=2) + "\n")


def verify_service(health_url: str, selection: Path) -> dict:
    with urllib.request.urlopen(health_url.rstrip("/") + "/health", timeout=10) as response:
        health = json.load(response)
    expected = json.loads(selection.read_text(encoding="utf-8"))
    if health.get("status") != "UP" or health.get("selectionManifestSha256") != digest(selection):
        raise ValueError("Inference service is unavailable or serves a different frozen model selection")
    if {model["id"] for model in health.get("models", [])} != set(expected["validatedModelIds"]):
        raise ValueError("Inference service does not expose all and only the frozen validated models")
    if health.get("graphSha256") != expected["graphSha256"] or health.get("featureSchemaHash") != expected["featureSchemaHash"]:
        raise ValueError("Inference service graph/feature schema differs from the frozen model bundle")
    return health


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("diagnostics", "policies"))
    parser.add_argument("--protocol", default="config/milestone4_protocol_v2.json")
    parser.add_argument("--corpus", default="data/processed/milestone4/corpus_v2")
    parser.add_argument("--output", default="reports/milestone4_policy_raw")
    parser.add_argument("--model-manifest", default="models/milestone4/v1/manifest.json")
    parser.add_argument("--service-url", default="http://host.docker.internal:8090")
    parser.add_argument("--service-health-url", default="http://127.0.0.1:8090", help="Host-side read-only registry verification before policy execution")
    parser.add_argument("--java-max-heap", default="1024m")
    parser.add_argument("--freeze-only", action="store_true", help="Bind executable/source hashes without generating or reading final outcomes")
    args = parser.parse_args()
    protocol, corpus, output, selection = (project_path(p) for p in (args.protocol, args.corpus, args.output, args.model_manifest))
    freeze = output / (args.mode + "_implementation_freeze.json")
    immutable_freeze(freeze, freeze_payload(args.mode, protocol, corpus, selection))
    print(json.dumps({"implementationFreeze": str(freeze), "sha256": digest(freeze), "freezeOnly": args.freeze_only}), flush=True)
    if args.freeze_only:
        return
    if args.mode == "policies":
        health = verify_service(args.service_health_url, selection)
        immutable_freeze(output / "policy_service_registry_preflight.json", health)
    workspace_id = hashlib.sha256(str(ROOT.resolve()).lower().encode()).hexdigest()[:16]
    active = subprocess.run(["docker", "ps", "--filter", "label=cascadeshield.m4.workspace=" + workspace_id,
                             "--format", "{{.Names}}"], capture_output=True, text=True, check=True).stdout.strip()
    if active:
        raise RuntimeError("An offline Milestone4 experiment is still active; inspect it before resuming: " + active)
    base = docker_base(args.java_max_heap)
    import uuid
    container = "cascadeshield-m4-" + args.mode + "-" + uuid.uuid4().hex[:12]
    base[3:3] = ["--name", container, "--label", "cascadeshield.m4.workspace=" + workspace_id]
    command = ["io.cascadeshield.sim.MlPolicyCli", "/workspace/data/processed/chennai_osm/road_graph.json",
               mounted(protocol), mounted(output), "final" if args.mode == "policies" else "diagnostics", args.service_url]
    if args.mode == "policies":
        command += [mounted(selection), mounted(corpus)]
    execute(base + ["sh", "/workspace/scripts/run_milestone4_java.sh"] + command, "frozen-" + args.mode)


if __name__ == "__main__":
    main()
