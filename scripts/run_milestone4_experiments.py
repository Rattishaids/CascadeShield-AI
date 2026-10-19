"""Cross-platform Docker launcher for isolated Java corpus and policy experiments."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
import uuid
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
def docker_base(heap: str) -> list[str]:
    return ["docker", "run", "--rm", "--memory", "2g", "--cpus", "4", "--mount", f"type=bind,source={ROOT},target=/workspace", "--mount", "type=volume,source=cascadeshield_maven_cache,target=/root/.m2", "-e", "MAVEN_MIRROR_URL=http://host.docker.internal:18090/maven2", "-e", "MAVEN_OPTS=-Xmx256m", "-e", f"ML_JAVA_HEAP={heap}", "-e", "SIMULATOR_GRAPH_PATH=/workspace/data/processed/chennai_osm/road_graph.json", "-w", "/workspace/simulator/backend", "maven:3.9-eclipse-temurin-21"]


def execute(command: list[str], mode: str) -> None:
    """Persist real command timing; interrupted RUNNING records remain inspectable."""
    directory = ROOT / "reports/milestone4_execution_log"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "_" + uuid.uuid4().hex[:12] + ".json")
    record = {"schemaVersion": "cascadeshield.milestone4-execution/1.0", "mode": mode,
              "startedAtUtc": datetime.now(timezone.utc).isoformat(), "status": "RUNNING",
              "command": command, "projectRoot": str(ROOT), "launcherPid": os.getpid(),
              "provenance": "EXECUTED_ENGINEERING_COMMAND"}
    if mode != "focused-java-tests":
        candidates = [*ROOT.glob("simulator/backend/src/main/java/**/*.java"),
                      *ROOT.glob("simulator/backend/target/classes/**/*.class"),
                      *ROOT.glob("config/milestone4_protocol*.json"),
                      ROOT / "scripts/run_milestone4_experiments.py",
                      ROOT / "scripts/run_milestone4_java.sh"]
        record["sourceAndExecutableSha256"] = {
            p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(candidates) if p.is_file()}

    def persist() -> None:
        pending = path.with_suffix(".pending")
        pending.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        pending.replace(path)

    persist()
    started = time.perf_counter()
    try:
        completed = subprocess.run(command, check=True)
        record.update(status="COMPLETED", returnCode=completed.returncode)
    except BaseException as error:
        record.update(status="INTERRUPTED" if isinstance(error, KeyboardInterrupt) else "FAILED",
                      returnCode=getattr(error, "returncode", None), errorType=type(error).__name__, error=str(error))
        raise
    finally:
        record.update(endedAtUtc=datetime.now(timezone.utc).isoformat(), elapsedWallSec=time.perf_counter()-started)
        persist()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["manifest", "development", "final-corpus", "policies", "diagnostics"])
    parser.add_argument("--compile", action="store_true", help="Run focused Java tests and refresh the existing dependency classpath")
    parser.add_argument("--protocol", default="config/milestone4_protocol_v2.json")
    parser.add_argument("--corpus", default="data/processed/milestone4/corpus_v2")
    parser.add_argument("--output", default="reports/milestone4_policy_raw")
    parser.add_argument("--model-manifest", default="models/milestone4/v1/manifest.json")
    parser.add_argument("--audit", default="reports/milestone4_leakage_audit.json")
    parser.add_argument("--java-max-heap", default="1024m", help="Bounded offline Java heap; default1GiB")
    parser.add_argument("--service-url", default="http://host.docker.internal:8090")
    args = parser.parse_args()
    base = docker_base(args.java_max_heap)
    if args.compile:
        execute(base + ["mvn", "-B", "-q", "-s", "mirror-settings.xml", "-DargLine=-Xmx512m", "-Dtest=MlCorpusTest,MlPolicyRunnerTest", "test"], "focused-java-tests")
        xml = ROOT / "simulator/backend/target/surefire-reports/TEST-io.cascadeshield.sim.MlCorpusTest.xml"
        properties = ET.parse(xml).getroot().find("properties")
        if properties is None:
            raise RuntimeError("Maven did not export runtime classpath")
        classpath = next(p.attrib["value"] for p in properties if p.attrib["name"] == "java.class.path")
        (ROOT / "simulator/backend/target/ml-classpath.txt").write_text(classpath, encoding="utf-8")
    if not (ROOT / "simulator/backend/target/ml-classpath.txt").is_file():
        raise SystemExit("Run once with --compile to resolve and verify the existing Java dependencies")

    def workspace(path: str) -> str:
        resolved = (ROOT / path).resolve()
        if resolved.is_relative_to(ROOT):
            return "/workspace/" + resolved.relative_to(ROOT).as_posix()
        raise ValueError(f"Path is outside the mounted project: {resolved}")

    graph = "/workspace/data/processed/chennai_osm/road_graph.json"
    if args.mode in ("manifest", "development", "final-corpus"):
        mode = {"manifest": "manifest", "development": "train,validation,calibration", "final-corpus": "final"}[args.mode]
        command = ["io.cascadeshield.sim.MlCorpusCli", graph, workspace(args.protocol), workspace(args.corpus), mode]
        if args.mode == "final-corpus":
            command.append(workspace(args.model_manifest))
        elif args.mode == "development":
            command.append(workspace(args.audit))
    else:
        mode = "diagnostics" if args.mode == "diagnostics" else "final"
        command = ["io.cascadeshield.sim.MlPolicyCli", graph, workspace(args.protocol), workspace(args.output), mode, args.service_url]
        if mode == "final":
            command += [workspace(args.model_manifest), workspace(args.corpus)]
    execute(base + ["sh", "/workspace/scripts/run_milestone4_java.sh"] + command, args.mode)


if __name__ == "__main__":
    main()
