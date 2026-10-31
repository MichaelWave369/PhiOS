#!/usr/bin/env python3
"""Review-only ThinkTank Web source/build/browser acceptance. Never installs PhiOS apps."""
from __future__ import annotations

import argparse
import hashlib
import html.parser
import json
import pathlib
import re
import shutil
import subprocess
import tempfile
import threading
import urllib.parse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

from scripts.sync_public_ecosystem_catalog import DEST
from scripts.verify_ecosystem_app_candidates import CANDIDATES, inspect_candidates

SCHEMA = "phios.thinktank_web_hosted_pilot.v0.1"
MAX_FILES = 512
MAX_BYTES = 64 * 1024 * 1024
EXPECTED_UI = "Φ THINK TANK"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class AssetLinks(html.parser.HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.paths: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = dict(attrs)
        if tag in {"script", "img"} and a.get("src"):
            self.paths.append(a["src"] or "")
        if tag == "link" and a.get("href") and a.get("rel") in {
            "stylesheet", "modulepreload", "icon"
        }:
            self.paths.append(a["href"] or "")


def verify_dist(dist: pathlib.Path) -> dict:
    """Check regular on-disk asset closure and root URL mapping; no install authority."""
    dist = dist.resolve(strict=True)
    if not dist.is_dir() or not (dist / "index.html").is_file():
        raise ValueError("static dist/index.html missing")
    files = sorted(p for p in dist.rglob("*") if p.is_file() or p.is_symlink())
    if not 2 <= len(files) <= MAX_FILES:
        raise ValueError("static artifact count outside bounds")
    sizes = 0
    rows = []
    for file in files:
        if file.is_symlink() or not file.is_file():
            raise ValueError("symlink or nonregular output refused")
        raw = file.read_bytes()
        sizes += len(raw)
        if sizes > MAX_BYTES:
            raise ValueError("static artifact set too large")
        rows.append({"path": file.relative_to(dist).as_posix(), "bytes": len(raw),
                     "sha256": sha256(raw)})
    html = (dist / "index.html").read_text(encoding="utf-8")
    links = AssetLinks()
    links.feed(html)
    if not any(link.startswith("/assets/") and link.endswith(".js")
               for link in links.paths):
        raise ValueError("expected built module script absent")
    for link in links.paths:
        parsed = urllib.parse.urlsplit(link)
        if parsed.scheme or parsed.netloc or not parsed.path.startswith("/"):
            raise ValueError("external or non-root asset reference refused")
        relative = urllib.parse.unquote(parsed.path).lstrip("/")
        if not relative or any(part in {"..", ".", ""} for part in relative.split("/")):
            raise ValueError("unsafe static asset path refused")
        target = dist / relative
        if target.is_symlink() or not target.is_file() or not target.resolve().is_relative_to(dist):
            raise ValueError(f"missing or escaping static asset: {relative}")
    encoded = json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()
    return {"file_count": len(rows), "total_bytes": sizes,
            "artifact_set_sha256": sha256(encoded), "entry_assets": links.paths}


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *_args: object) -> None:
        return


def browser_smoke(dist: pathlib.Path, browser: str) -> None:
    """Run the built JS inside headless Chrome against a disposable loopback server."""
    executable = shutil.which(browser)
    if not executable:
        raise RuntimeError("headless Chrome executable unavailable; no browser PASS")
    server = ThreadingHTTPServer(
        ("127.0.0.1", 0), partial(QuietHandler, directory=str(dist))
    )
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        with tempfile.TemporaryDirectory(prefix="thinktank-chrome-") as profile:
            url = f"http://127.0.0.1:{server.server_port}/"
            proc = subprocess.run(
                [executable, "--headless=new", "--disable-gpu", "--no-sandbox",
                 "--disable-dev-shm-usage", "--disable-background-networking",
                 "--disable-extensions", "--no-first-run", "--no-default-browser-check",
                 "--disable-component-update", "--disable-sync",
                 "--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE localhost, EXCLUDE 127.0.0.1",
                 f"--user-data-dir={profile}", "--virtual-time-budget=7000",
                 "--dump-dom", url],
                capture_output=True, text=True, timeout=45, check=False,
            )
            if proc.returncode != 0:
                raise RuntimeError(f"headless Chrome exited {proc.returncode}")
            if 'class="room-shell"' not in proc.stdout or EXPECTED_UI not in proc.stdout:
                raise RuntimeError("React ThinkTank room did not render in headless Chrome")
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=4)


def qualify(source: pathlib.Path, dist: pathlib.Path, lock: pathlib.Path,
            browser: str, receipt_file: pathlib.Path) -> dict:
    candidates = json.loads(CANDIDATES.read_text(encoding="utf-8"))
    catalog = json.loads(DEST.read_text(encoding="utf-8"))
    inspections = inspect_candidates(candidates, catalog)
    candidate = next(x for x in candidates["candidates"] if x["app_key"] == "thinktank-web")
    reviewed = next(x for x in inspections if x["key"] == "thinktank-web")
    actual_sha = subprocess.check_output(
        ["git", "-C", str(source), "rev-parse", "HEAD"], text=True, timeout=10
    ).strip()
    if actual_sha != candidate["source_sha"]:
        raise ValueError("ThinkTank source commit changed from reviewed pin")
    upstream_lock_tracked = subprocess.run(
        ["git", "-C", str(source), "ls-files", "--error-unmatch", "package-lock.json"],
        capture_output=True, text=True, timeout=10, check=False
    ).returncode == 0
    if upstream_lock_tracked or not lock.is_file():
        raise ValueError("pilot requires untracked generated npm lock; upstream pin changed")
    if not re.fullmatch(r"[0-9a-f]{40}", actual_sha):
        raise ValueError("invalid source commit")
    bundle = verify_dist(dist)
    browser_smoke(dist, browser)
    receipt = {
        "schema_version": SCHEMA,
        "app_id": "phios.thinktank-web",
        "source_repo": candidate["manifest"]["source"]["repository_url"],
        "source_sha": actual_sha,
        "candidate_manifest_sha256": reviewed["manifest_sha256"],
        "dependency_lock_provenance": "GENERATED_DURING_HOSTED_CI_NOT_COMMITTED_UPSTREAM",
        "observed_generated_package_lock_sha256": sha256(lock.read_bytes()),
        "dependency_reproducibility_verified": False,
        "offline_dependency_closure_verified": False,
        "asset_redistribution_reviewed": False,
        "source_review_status": candidate["review"]["state"],
        "static_bundle": bundle,
        "browser_render_result": "PASS_HOSTED_LOOPBACK_CHROMIUM",
        "browser_network_isolation_verified": False,
        "provider_bridge_started": False,
        "phios_registry_enrolled": False,
        "phios_app_installed": False,
        "phios_desktop_launch_granted": False,
        "phios_vm_boot_verified": False,
        "phios_rollback_verified": False,
        "production_qualified": False,
        "next_gate": "COMMIT_REVIEWED_NPM_LOCK_AND_GOVERNED_INSTALL_VM_ACCEPTANCE",
    }
    receipt_file.parent.mkdir(parents=True, exist_ok=True)
    receipt_file.write_text(json.dumps(receipt, sort_keys=True, indent=2) + "\n",
                            encoding="utf-8")
    print("THINKTANK_WEB_HOSTED_RENDER_PASS_NO_INSTALL_AUTHORITY")
    print(json.dumps({k: receipt[k] for k in
                      ("source_sha", "browser_render_result", "phios_app_installed",
                       "next_gate")}, sort_keys=True))
    return receipt


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--source", type=pathlib.Path, required=True)
    p.add_argument("--dist", type=pathlib.Path, required=True)
    p.add_argument("--generated-lock", type=pathlib.Path, required=True)
    p.add_argument("--browser", default="google-chrome")
    p.add_argument("--receipt", type=pathlib.Path, required=True)
    args = p.parse_args()
    qualify(args.source, args.dist, args.generated_lock, args.browser, args.receipt)


if __name__ == "__main__":
    main()
