"""R5D test-only loopback app server for disposable runner lifecycle rehearsal.

Not a general PhiOS launcher. Serves an installed *test payload* and a
separately owned user-data JSON file. Used only through tests with fixed inputs.
"""
from __future__ import annotations

import argparse
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--asset", type=Path, required=True)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--expected", choices=("version-one", "version-two"), required=True)
    args = parser.parse_args()
    asset = args.asset
    data_path = args.data
    expected = args.expected
    # The test script accepts only an existing, non-symlinked artifact and
    # a sibling-controlled data file. Never fetch or execute source from GitHub.
    if asset.is_symlink() or not asset.is_file() or not data_path.is_file() or data_path.is_symlink():
        raise ValueError("Test fixture asset/state must be existing regular files")
    asset_bytes = asset.read_bytes()
    if expected.encode("ascii") not in asset_bytes:
        raise ValueError("Test server version does not match installed asset")
    asset_digest = hashlib.sha256(asset_bytes).hexdigest()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args: object) -> None:
            return

        def _json(self, obj: dict[str, object], code: int = 200) -> None:
            wire = json.dumps(obj, sort_keys=True).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(wire)))
            self.end_headers()
            self.wfile.write(wire)

        def do_GET(self) -> None:
            if self.path == "/health":
                state = json.loads(data_path.read_text(encoding="utf-8"))
                self._json({"version": expected, "asset_sha256": asset_digest,
                            "pid": os.getpid(), "state_schema": state.get("schema")})
            elif self.path == "/data":
                self._json(json.loads(data_path.read_text(encoding="utf-8")))
            else:
                self.send_error(404)

        def do_POST(self) -> None:
            current = json.loads(data_path.read_text(encoding="utf-8"))
            if self.path == "/record" and expected == "version-one":
                if current.get("schema") != "r5d.fixture.user_state.v1":
                    self.send_error(409)
                    return
                current["counter"] += 1
            elif self.path == "/migrate" and expected == "version-two":
                if current.get("schema") != "r5d.fixture.user_state.v1":
                    self.send_error(409)
                    return
                current["schema"] = "r5d.fixture.user_state.v2"
                current["counter"] += 100
                current["migration"] = "simulated_v2_incompatible_state"
            else:
                self.send_error(405)
                return
            temp = data_path.with_suffix(".new")
            temp.write_text(json.dumps(current, sort_keys=True) + "\n", encoding="utf-8")
            temp.replace(data_path)
            self._json(current)

    ThreadingHTTPServer(("127.0.0.1", args.port), Handler).serve_forever(poll_interval=0.2)


if __name__ == "__main__":
    main()
