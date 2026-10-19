"""Relay only official Maven Central artifacts through a fixed local verified cache.

Some Docker Desktop installations cannot access outbound HTTPS although their
Windows host can. This opt-in build helper forwards only /maven2 artifact paths
to https://repo.maven.apache.org; it is not a general HTTP proxy.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / ".cache/maven-central"
UPSTREAM = "https://repo.maven.apache.org"
MAX_ARTIFACT_BYTES = 128 * 1024 * 1024
PATH_COMPONENT = re.compile(r"[A-Za-z0-9_.+-]+\Z")
_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


def artifact_path(request_path: str) -> Path:
    """Reject proxy-style URLs, queries, traversal, encoding tricks and directories."""
    parsed = urllib.parse.urlsplit(request_path)
    if (parsed.scheme or parsed.netloc or parsed.query or parsed.fragment
            or parsed.path != request_path or not request_path.startswith("/maven2/")):
        raise ValueError("Only plain /maven2 artifact paths are supported")
    relative = request_path[len("/maven2/"):]
    parts = relative.split("/")
    if (len(request_path) > 2048 or not parts or any(part in {"", ".", ".."}
            or not PATH_COMPONENT.fullmatch(part) for part in parts)):
        raise ValueError("Invalid Maven artifact path")
    root = CACHE.resolve()
    target = root.joinpath(*parts).resolve()
    if not target.is_relative_to(root):
        raise ValueError("Artifact path escaped the fixed cache")
    return target


def sha256(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


class CentralRedirectsOnly(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        destination = urllib.parse.urlsplit(newurl)
        if (destination.scheme != "https" or destination.hostname != "repo.maven.apache.org"
                or destination.username or destination.password or destination.port not in {None, 443}):
            raise urllib.error.URLError("Redirect outside official HTTPS Maven Central refused")
        artifact_path(destination.path)
        if destination.query or destination.fragment:
            raise urllib.error.URLError("Unexpected Maven Central redirect query refused")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def cached_artifact(request_path: str) -> tuple[Path, dict]:
    target = artifact_path(request_path)
    sidecar = target.with_name(target.name + ".relay.json")
    with _locks_guard:
        lock = _locks.setdefault(request_path, threading.Lock())
    with lock:
        if target.exists() or sidecar.exists():
            if not target.is_file() or not sidecar.is_file():
                raise ValueError("Incomplete cache entry; refusing silent overwrite")
            metadata = json.loads(sidecar.read_text(encoding="utf-8"))
            if (metadata["url"] != UPSTREAM + request_path or metadata["bytes"] != target.stat().st_size
                    or metadata["sha256"] != sha256(target)):
                raise ValueError("Local cache checksum/provenance mismatch; refusing corrupted artifact")
            return target, metadata
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(target.name + "." + uuid.uuid4().hex + ".part")
        request = urllib.request.Request(UPSTREAM + request_path,
            headers={"User-Agent": "CascadeShieldAI-MavenCentralRelay/0.1", "Accept-Encoding": "identity"})
        opener = urllib.request.build_opener(CentralRedirectsOnly())
        try:
            for attempt in range(3):
                size, checksum = 0, hashlib.sha256()
                try:
                    with opener.open(request, timeout=90) as response, temporary.open("xb") as output:
                        if response.status != 200:
                            raise ValueError("Unexpected upstream artifact status")
                        for block in iter(lambda: response.read(1024 * 1024), b""):
                            size += len(block)
                            if size > MAX_ARTIFACT_BYTES:
                                raise ValueError("Artifact exceeds bounded 128 MiB download limit")
                            checksum.update(block)
                            output.write(block)
                        content_type = response.headers.get("Content-Type", "application/octet-stream")
                        expected_size = response.headers.get("Content-Length")
                        if expected_size and int(expected_size) != size:
                            raise http.client.IncompleteRead(b"", int(expected_size) - size)
                    break
                except (urllib.error.URLError, TimeoutError, http.client.HTTPException) as error:
                    if isinstance(error, urllib.error.HTTPError) and error.code not in {429, 500, 502, 503, 504}:
                        raise
                    delay = float(1 << attempt)
                    if isinstance(error, urllib.error.HTTPError):
                        retry_after = error.headers.get("Retry-After", "")
                        if retry_after.isdigit():
                            delay = max(delay, float(retry_after))
                            if delay > 30:
                                raise  # Never retry earlier than a longer upstream cooldown.
                    if attempt == 2:
                        raise
                    temporary.unlink(missing_ok=True)
                    time.sleep(delay)
            metadata = {"url": UPSTREAM + request_path, "bytes": size, "sha256": checksum.hexdigest(),
                        "acquiredAtUtc": datetime.now(timezone.utc).isoformat(), "contentType": content_type}
            # Successful cache entries are immutable; existing files are never silently replaced.
            if target.exists() or sidecar.exists():
                raise ValueError("Cache entry appeared during download; refusing overwrite")
            temporary.rename(target)
            with sidecar.open("x", encoding="utf-8") as output:
                json.dump(metadata, output, indent=2)
                output.write("\n")
            return target, metadata
        finally:
            if temporary.exists():
                temporary.unlink()


class CentralHandler(BaseHTTPRequestHandler):
    server_version = "CascadeShieldMavenRelay/0.1"

    def do_GET(self):
        self.serve_artifact(include_body=True)

    def do_HEAD(self):
        self.serve_artifact(include_body=False)

    def serve_artifact(self, include_body: bool) -> None:
        try:
            path, metadata = cached_artifact(self.path)
        except urllib.error.HTTPError as error:
            self.send_error(error.code if error.code in {404, 429, 503} else 502)
            return
        except ValueError as error:
            self.send_error(400, str(error))
            return
        except (OSError, urllib.error.URLError, http.client.HTTPException, KeyError):
            self.send_error(502, "Official Maven Central retrieval or cache verification failed")
            return
        self.send_response(200)
        self.send_header("Content-Length", str(metadata["bytes"]))
        self.send_header("Content-Type", metadata["contentType"])
        self.send_header("X-Artifact-SHA256", metadata["sha256"])
        self.end_headers()
        if include_body:
            try:
                with path.open("rb") as handle:
                    for block in iter(lambda: handle.read(1024 * 1024), b""):
                        self.wfile.write(block)
            except (BrokenPipeError, ConnectionResetError):
                pass

    def log_message(self, *_):
        # Maven already reports transfer failures; routine dependency requests stay quiet.
        pass


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bind", default="127.0.0.1", help="Use 0.0.0.0 explicitly for Docker Desktop access")
    parser.add_argument("--port", type=int, default=18089)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("Port must be 1–65535")
    CACHE.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer((args.bind, args.port), CentralHandler)
    print(f"Official Maven Central relay: http://{args.bind}:{args.port}/maven2", flush=True)
    print(f"Fixed verified cache: {CACHE}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
