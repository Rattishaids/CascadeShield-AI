"""Audit Git release bytes or verify an extracted ZIP using only the Python standard library."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = "release-manifest.json"
FORBIDDEN_PARTS = {".git", ".runtime", "node_modules", "target", "dist", "__pycache__",
                   ".pytest_cache", ".cache", ".venv", ".venv-ml", ".venv-ml-gpu"}
SECRET_PATTERNS = {
    "private-key": re.compile(r"(?m)^-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
    "github-token": re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{70,})\b"),
    "aws-access-key": re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    "personal-windows-directory": re.compile(r"(?i)[A-Z]:[\\/]+Users[\\/]+[^\\/\s\"]+"),
}
REQUIRED = ("README.md", ".env.example", "compose.yaml", "DATA_LICENSES.md",
            "LICENSES/ODbL-1.0.txt", "scripts/setup.ps1", "scripts/check_prerequisites.ps1",
            "scripts/start_simulator.ps1", "scripts/stop_simulator.ps1", "scripts/load_demo.ps1",
            "simulator/backend/pom.xml", "simulator/frontend/package-lock.json",
            "simulator/backend/src/main/resources/db/migration/V1__simulator.sql",
            "simulator/backend/src/main/resources/db/migration/V2__operational_ai_boundary.sql",
            "simulator/backend/src/main/resources/db/migration/V3__benchmark_jobs.sql",
            "data/processed/chennai_osm/road_graph.json", "data/processed/chennai_osm/roads.geojson")


def staged_bytes() -> dict[str, bytes]:
    raw = subprocess.check_output(["git", "ls-files", "--stage", "-z"], cwd=ROOT)
    records = []
    for item in raw.split(b"\0"):
        if not item:
            continue
        meta, name = item.split(b"\t", 1)
        mode, digest, stage = meta.split()
        if stage != b"0" or mode not in (b"100644", b"100755"):
            raise ValueError("Only resolved regular files are supported")
        path = name.decode("utf-8")
        if path != MANIFEST:
            records.append((path, digest))
    blob_stream = io.BytesIO(subprocess.check_output(
        ["git", "cat-file", "--batch"], cwd=ROOT,
        input=b"".join(digest+b"\n" for _, digest in records)))
    result = {}
    for name, _ in records:
        header = blob_stream.readline().split()
        if len(header) != 3 or header[1] != b"blob":
            raise ValueError("Invalid Git blob response")
        result[name] = blob_stream.read(int(header[2]))
        if blob_stream.read(1) != b"\n":
            raise ValueError("Invalid Git blob separator")
    return result


def audit(files: dict[str, bytes]) -> dict:
    findings = []
    credential_fixtures = []
    for name, content in files.items():
        path = Path(name)
        if path.is_absolute() or ".." in path.parts or any(p in FORBIDDEN_PARTS for p in path.parts):
            findings.append({"path": name, "kind": "forbidden-path"})
        if (path.name.startswith(".env") and path.name != ".env.example") or path.name in ("kaggle.json", "id_rsa", "id_ed25519"):
            findings.append({"path": name, "kind": "local-credentials-file"})
        if name.startswith(("data/raw/", "reports/benchmark_raw/", "reports/milestone4_policy_raw/")):
            findings.append({"path": name, "kind": "excluded-large-research-artifact"})
        if len(content) >= 100 * 1024 * 1024:
            findings.append({"path": name, "kind": "github-file-limit"})
        if content.startswith(b"version https://git-lfs.github.com/spec/v1"):
            findings.append({"path": name, "kind": "lfs-pointer"})
        if path.suffix.lower() in (".pt", ".png", ".pdf", ".ico"):
            continue
        text = content.decode("utf-8-sig", errors="replace")
        for kind, pattern in SECRET_PATTERNS.items():
            if pattern.search(text):
                findings.append({"path": name, "kind": kind})
        for match in re.finditer(r"(?:postgres(?:ql)?|jdbc:postgresql)://[^\s\"']+", text):
            url = match.group(0)
            if "@" in url:
                # Existing isolated-test fixtures contain a public, fixed demo pair;
                # never treat that pair as evidence that real credentials were scanned away.
                if "cascadeshield:cascadeshield@" in url:
                    credential_fixtures.append({"path": name, "kind": "public-local-test-default"})
                elif not any(marker in url for marker in ("${", "<", "{", "YOUR_")):
                    findings.append({"path": name, "kind": "credential-bearing-url-review-required"})
    for name in REQUIRED:
        if name not in files:
            findings.append({"path": name, "kind": "missing-runtime-file"})
    graph_name = "data/processed/chennai_osm/road_graph.json"
    if graph_name in files and hashlib.sha256(files[graph_name]).hexdigest() != "c943bac278192042b22342d8e1be898cc68512fb936e314633645bc3e0304e60":
        findings.append({"path": graph_name, "kind": "unexpected-geographic-graph"})
    return {"passed": not findings, "fileCount": len(files), "totalBytes": sum(map(len, files.values())),
            "largestFiles": [{"path": p, "bytes": len(v)} for p,v in sorted(files.items(), key=lambda r:len(r[1]), reverse=True)[:12]],
            "findings": findings, "publicCredentialFixtures": credential_fixtures,
            "scope": "Pattern-based secret/private-path/size audit; not a guarantee of absence of every possible secret."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write-manifest", action="store_true", help="Audit the exact staged Git blobs and write their canonical-byte inventory")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    if args.write_manifest:
        files = staged_bytes()
        result = audit(files)
        if result["passed"]:
            manifest = {"schemaVersion": "cascadeshield.release-manifest/1.0", "source": "EXACT_STAGED_GIT_BLOBS",
                        "selfExcluded": MANIFEST,
                        "files": {name: {"bytes": len(content), "sha256": hashlib.sha256(content).hexdigest()}
                                  for name, content in sorted(files.items())}}
            (ROOT/MANIFEST).write_text(json.dumps(manifest, indent=2)+"\n", encoding="utf-8")
    else:
        manifest = json.loads((ROOT/MANIFEST).read_text(encoding="utf-8"))
        files = {}
        mismatches = []
        for name, row in manifest["files"].items():
            path = (ROOT/name).resolve()
            if not path.is_relative_to(ROOT) or not path.is_file():
                mismatches.append(name)
                continue
            content = path.read_bytes()
            files[name] = content
            if len(content) != row["bytes"] or hashlib.sha256(content).hexdigest() != row["sha256"]:
                mismatches.append(name)
        result = audit(files)
        result["manifestMismatches"] = mismatches
        result["passed"] = result["passed"] and not mismatches
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(result, indent=2)+"\n", encoding="utf-8")
    print(json.dumps(result))
    raise SystemExit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
