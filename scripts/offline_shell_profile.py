#!/usr/bin/env python3
"""v0.63 experimental offline profile; only derived disposable Trellis staging."""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import shutil
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import trellis_stage_bridge as bridge

APPS = ("vessie-web", "thinktank-web")
SW_FILENAME = "phios-offline-sw.js"
BOOT_FILENAME = "phios-offline-bootstrap.js"
SW_TEMPLATE = r"""
"use strict";
const PROFILE = "phios-v063-readonly-v1";
const FILES = __FILES__;
const CACHE = PROFILE + "-" + "__DIGEST__";
const scoped = path => new URL(path, self.registration.scope).href;
const approved = new Map(FILES.map(item => [scoped(item.path), item.sha256]));
const hex = bytes => [...new Uint8Array(bytes)].map(x=>x.toString(16).padStart(2,"0")).join("");
self.addEventListener("install",event => {
  event.waitUntil((async()=>{
    const cache = await caches.open(CACHE);
    for(const [url,sha] of approved) {
      const response = await fetch(url,{cache:"no-store",credentials:"omit"});
      if(!response.ok || response.type!=="basic") throw Error("OFFLINE_CACHE_FETCH_FAILED");
      const bytes = await response.arrayBuffer();
      const actual = hex(await crypto.subtle.digest("SHA-256",bytes));
      if(actual!==sha) throw Error("OFFLINE_CACHE_DIGEST_DRIFT");
      await cache.put(url,new Response(bytes,{status:200,headers:response.headers}));
    }
    await self.skipWaiting();
  })());
});
self.addEventListener("activate",event => {
  event.waitUntil((async()=>{
    const names = await caches.keys();
    for(const name of names) {
      if(name.startsWith(PROFILE+"-") && name!==CACHE) await caches.delete(name);
    }
    await self.clients.claim();
  })());
});
self.addEventListener("fetch",event => {
  const request = event.request;
  // Closed-world policy: no network fallback. GETs outside the frozen
  // first-party shell are refused, including local model/provider bridges.
  if(request.method!=="GET") {
    event.respondWith(Response.error());
    return;
  }
  const url = new URL(request.url);
  const shell = new URL(self.registration.scope);
  const path = url.pathname===shell.pathname ? scoped("index.html") : url.href;
  if(url.origin!==shell.origin || !approved.has(path) || url.search!=="") {
    event.respondWith(Response.error());
    return;
  }
  event.respondWith(caches.open(CACHE).then(async cache =>
    (await cache.match(path)) || Response.error()));
});
""".strip() + "\n"
BOOT = """// PhiOS derived v0.63 offline shell; not a system permission grant.
if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("./phios-offline-sw.js",{scope:"./"})
    .catch(error=>{window.__PHIOS_OFFLINE_SW_ERROR__=String(error);});
}
"""


def demand(ok: bool, code: str) -> None:
    if not ok:
        raise ValueError("PHIOS_OFFLINE_" + code)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def precache_manifest(root: Path) -> list[dict]:
    files = bridge.regular_files(root)
    demand(1 < len(files) <= 128, "FILE_SET_INVALID")
    names = {p.as_posix() for p in files}
    demand("index.html" in names and BOOT_FILENAME in names and
           SW_FILENAME not in names, "CACHE_SET_INVALID")
    return [{"path": p.as_posix(), "sha256": sha((root / p).read_bytes())}
            for p in files]


def prepare(stage: Path, home: Path, output: Path, app: str) -> dict:
    demand(app in APPS, "UNREVIEWED_APP")
    # Original, independently checked Trellis package must be intact *first*.
    result = bridge.verify_staged(stage, home)
    demand(result["candidate"] == app and result["all_installed_bytes_rehashed"] is True,
           "PARENT_NOT_VERIFIED")
    stage = stage.resolve(strict=True)
    parent = json.loads((stage / "bridge-receipt.json").read_text())
    demand(parent["candidate"] == app, "PARENT_APP_DRIFT")
    output = output.absolute()
    demand(not output.exists() and not output.is_symlink(), "DESTINATION_EXISTS")
    demand(stage not in output.parents and stage != output, "DESTINATION_IN_SOURCE")
    demand(not any(p.is_symlink() for p in output.parents), "DESTINATION_PARENT_SYMLINK")
    payload = output / "payload"
    try:
        shutil.copytree(stage / "payload", payload, symlinks=False)
        copied = bridge.regular_files(payload)
        source_files = bridge.regular_files(stage / "payload")
        demand(copied == source_files and
               bridge.dir_digest(payload, copied)[0] == parent["payload_sha256"],
               "PARENT_COPY_DRIFT")
        index = payload / "index.html"
        before = index.read_text(encoding="utf-8")
        demand("phios-offline-bootstrap" not in before and
               "</body>" in before.lower(), "HTML_DRIFT")
        new = re.sub(r"</body>", '<script src="./' + BOOT_FILENAME +
                     '"></script></body>', before, count=1, flags=re.I)
        index.write_text(new, encoding="utf-8")
        (payload / BOOT_FILENAME).write_text(BOOT, encoding="utf-8")
        listing = precache_manifest(payload)
        fingerprint = sha(json.dumps(listing, sort_keys=True, separators=(",", ":")).encode())
        sw = (SW_TEMPLATE.replace("__FILES__", json.dumps(listing, sort_keys=True))
                         .replace("__DIGEST__", fingerprint))
        (payload / SW_FILENAME).write_text(sw, encoding="utf-8")
        files = bridge.regular_files(payload)
        digest, file_receipts = bridge.dir_digest(payload, files)
        package = "phios-" + app + "-offline"
        spec_name = package + ".trellis.yaml"
        spec = bridge.spec_yaml(package, digest,
                                sorted({path.parts[0] for path in files}),
                                bridge.candidates()[app]["web"]["url"])
        (output / spec_name).write_text(spec, encoding="utf-8")
        report = {
            "schema": "phios.trellis_offline_shell_profile.v0.1",
            "app": app, "package": package, "version": bridge.VERSION,
            "source_sha": parent["source_sha"],
            "parent_payload_sha256": parent["payload_sha256"],
            "payload_sha256": digest, "files": file_receipts,
            "cache_manifest_sha256": fingerprint,
            "precache_count": len(listing), "spec": spec_name,
            "spec_sha256": sha(spec.encode()), "derived_artifact": True,
            "phios_installed": False, "phios_launch_authorized": False,
            "license_cleared": False, "external_done": False}
        (output / "offline-profile-receipt.json").write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n")
        return report
    except BaseException:
        shutil.rmtree(output, ignore_errors=True)
        raise


def verify(stage: Path, home: Path, app: str) -> dict:
    demand(app in APPS, "UNREVIEWED_APP")
    stage = stage.resolve(strict=True)
    home = home.resolve(strict=True)
    receipt = json.loads((stage / "offline-profile-receipt.json").read_text())
    package = "phios-" + app + "-offline"
    demand(receipt["schema"] == "phios.trellis_offline_shell_profile.v0.1" and
           receipt["app"] == app and receipt["package"] == package and
           receipt["phios_installed"] is False and
           receipt["phios_launch_authorized"] is False and
           receipt["external_done"] is False and receipt["derived_artifact"] is True,
           "PROFILE_RECEIPT_AUTHORITY")
    spec = stage / receipt["spec"]
    demand(spec.name == package + ".trellis.yaml" and not spec.is_symlink()
           and sha(spec.read_bytes()) == receipt["spec_sha256"], "SPEC_DRIFT")
    src = stage / "payload"
    installed = home / "cellar" / package / bridge.VERSION
    source_files = bridge.regular_files(src)
    installed_files = bridge.regular_files(installed)
    staged_digest, details = bridge.dir_digest(src, source_files)
    installed_digest, actual = bridge.dir_digest(installed, installed_files)
    demand(staged_digest == installed_digest == receipt["payload_sha256"] and
           source_files == installed_files and details == actual == receipt["files"],
           "INSTALLED_BYTES_DRIFT")
    trellis_receipt = json.loads((home / "receipts" / (package + ".json")).read_text())
    demand(trellis_receipt["name"] == package and
           trellis_receipt["version"] == bridge.VERSION and
           trellis_receipt["source"]["checksum_expected_sha256"] == staged_digest and
           trellis_receipt["source"]["checksum_actual_sha256"] == staged_digest and
           trellis_receipt["platform_evaluated"]["matched"] is True and
           set(trellis_receipt["installed_files"]) ==
           {str(installed / f) for f in installed_files},
           "TRELLIS_RECEIPT_DRIFT")
    lock = json.loads((home / "locks/default.lock.json").read_text())
    demand(lock["profile"] == "default" and any(
        x["name"] == package and x["version"] == bridge.VERSION
        for x in lock["packages"]), "TRELLIS_LOCK_DRIFT")
    return {"schema": "phios.offline_shell_verified.v0.1", "app": app,
            "sha256": installed_digest, "files": len(installed_files),
            "all_installed_bytes_rehashed": True, "trellis_receipt_checked": True,
            "phios_installed": False, "phios_launch_authorized": False,
            "offline_browser_verified": False, "external_done": False}


def main() -> None:
    parser = argparse.ArgumentParser()
    subs = parser.add_subparsers(dest="command", required=True)
    for name in ("prepare", "verify"):
        p = subs.add_parser(name)
        p.add_argument("--app", required=True, choices=APPS)
        p.add_argument("--stage", type=Path, required=True)
        p.add_argument("--home", type=Path, required=True)
        if name == "prepare":
            p.add_argument("--output", type=Path, required=True)
    a = parser.parse_args()
    report = (prepare(a.stage, a.home, a.output, a.app)
              if a.command == "prepare" else verify(a.stage, a.home, a.app))
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
