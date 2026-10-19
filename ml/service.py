"""Bounded local JSON HTTP boundary; prediction has no simulator or database write access."""
from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .inference import ModelBundle


def serve(directory: Path, host: str = "127.0.0.1", port: int = 8090):
    bundle = ModelBundle(directory)

    class Handler(BaseHTTPRequestHandler):
        def reply(self, status, value):
            body = json.dumps(value, allow_nan=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers(); self.wfile.write(body)

        def do_GET(self):
            if self.path == "/health":
                self.reply(200, {"status": "UP", "modelsLoaded": len(bundle.models), **bundle.catalog()})
            elif self.path == "/models":
                self.reply(200, bundle.catalog())
            else:
                self.reply(404, {"error": "Unknown endpoint"})

        def do_POST(self):
            if self.path != "/predict":
                self.reply(404, {"error": "Unknown endpoint"}); return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 8*1024*1024:
                    self.reply(413, {"error": "A JSON body of at most 8 MiB is required"}); return
                if self.headers.get_content_type() != "application/json":
                    self.reply(415, {"error": "application/json is required"}); return
                request = json.loads(self.rfile.read(length))
                self.reply(200, bundle.predict(request))
            except (ValueError, KeyError, TypeError) as exc:
                self.reply(400, {"error": str(exc), "fallbackRequired": True})
            except Exception as exc:
                self.reply(503, {"error": type(exc).__name__, "fallbackRequired": True})

    print(f"Read-only ML inference on http://{host}:{port}; models={list(bundle.models)}", flush=True)
    ThreadingHTTPServer((host, port), Handler).serve_forever()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models", type=Path, default=Path("models/milestone4/v1"))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8090)
    args = parser.parse_args()
    serve(args.models, args.host, args.port)


if __name__ == "__main__":
    main()
