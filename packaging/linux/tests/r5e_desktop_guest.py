# R5E installed-guest test-only desktop lifecycle. Not included in release ISO.

import hashlib
import json
import uuid
from pathlib import Path


import phios.apps.desktop_update as update_module
from phios.apps.browser_session import plan_browser_session
from phios.apps.desktop_catalog import snapshot_desktop_catalog
from phios.apps.desktop_launch import (
    DesktopAppInstaller,
    DesktopAppRegistrationRequest,
    DesktopLaunchGrant,
    plan_desktop_app,
)
from phios.apps.desktop_update import (
    DesktopRetentionMarker,
    DesktopRollbackPlan,
    DesktopRollbackReceipt,
    DesktopRollbackRequest,
    DesktopRollbackService,
    DesktopUpdatePlan,
    DesktopUpdateReceipt,
    DesktopUpdateRequest,
    DesktopUpdateService,
    plan_desktop_rollback,
    plan_desktop_update,
    review_desktop_rollback,
    review_desktop_update,
)
from phios.apps.manifest import AppManifest
from phios.apps.package_install import (
    AppInstallReceipt,
    BuildPackagePlan,
    PackageArtifact,
    snapshot_installed_tree,
)
from phios.apps.static_web import plan_static_web_adapter


def _manifest(version: str) -> AppManifest:
    return AppManifest.from_dict(
        {
            "schema_version": "phios.app_manifest.v0.1",
            "app_id": "phi.update-example",
            "name": "Update Example",
            "version": version,
            "description": f"Update fixture {version}",
            "source": {
                "repository_url": "https://github.com/example/update-example",
                "license_expression": "MIT",
                "redistribution": "permitted",
            },
            "entrypoint": {"runtime": "node", "target": "package.json"},
            "permissions": [],
        }
    )


def _install_version(
    tmp_path: Path,
    *,
    version: str,
    body: str,
    port: int,
) -> dict[str, object]:
    manifest = _manifest(version)
    install_root = tmp_path / "installed"
    install_path = install_root / manifest.app_id / manifest.version / "artifactprefix"
    payload = install_path / "payload"
    metadata = install_path / ".phios"
    dist = payload / "dist"
    assets = dist / "assets"
    assets.mkdir(parents=True)
    metadata.mkdir()
    (dist / "index.html").write_text(
        f"<html><body>{body}</body></html>",
        encoding="utf-8",
    )
    (assets / "app.js").write_text(
        f"console.log({body!r})",
        encoding="utf-8",
    )

    artifacts: list[PackageArtifact] = []
    for path in sorted(dist.rglob("*")):
        if path.is_file():
            artifacts.append(
                PackageArtifact(
                    path=path.relative_to(payload).as_posix(),
                    byte_count=path.stat().st_size,
                    sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                )
            )
    artifact_tuple = tuple(artifacts)
    artifact_digest = hashlib.sha256()
    for artifact in artifact_tuple:
        artifact_digest.update(artifact.canonical_line())

    package_plan = BuildPackagePlan(
        app_id=manifest.app_id,
        app_version=manifest.version,
        manifest_sha256=manifest.sha256(),
        registry_snapshot_sha256="1" * 64,
        repository_url=manifest.source.repository_url,
        commit_sha="a" * 40,
        build_plan_sha256="2" * 64,
        execution_receipt_sha256="3" * 64,
        offline_build_receipt_sha256="4" * 64,
        artifact_set_sha256=artifact_digest.hexdigest(),
        artifacts=artifact_tuple,
        install_relative_path=f"{manifest.app_id}/{manifest.version}/artifactprefix",
        launch_authority=False,
    )
    (metadata / "package-plan.json").write_text(
        json.dumps(package_plan.to_dict(), sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    (metadata / "manifest.json").write_text(
        json.dumps(manifest.to_dict(), sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )

    payload_sha, artifact_count, total_bytes = snapshot_installed_tree(payload)
    tree_sha, _, _ = snapshot_installed_tree(install_path)
    receipt = AppInstallReceipt(
        receipt_id=str(uuid.uuid4()),
        timestamp_utc="2026-09-19T16:40:00+00:00",
        app_id=manifest.app_id,
        app_version=manifest.version,
        package_plan_sha256=package_plan.sha256(),
        manifest_sha256=manifest.sha256(),
        registry_snapshot_sha256="1" * 64,
        build_plan_sha256="2" * 64,
        execution_receipt_sha256="3" * 64,
        offline_build_receipt_sha256="4" * 64,
        artifact_set_sha256=payload_sha,
        installed_payload_sha256=payload_sha,
        installed_tree_sha256=tree_sha,
        artifact_count=artifact_count,
        total_bytes=total_bytes,
        install_path=str(install_path.resolve()),
        launch_authority=False,
        status="installed",
    )
    static = plan_static_web_adapter(
        receipt.to_dict(),
        install_root=install_root,
        loopback_port=port,
        serve_seconds=120,
    )
    browser = plan_browser_session(
        static.to_dict(),
        browser_tool="chromium",
        session_seconds=30,
        readiness_timeout_ms=2500,
    )
    desktop = plan_desktop_app(
        browser.to_dict(),
        static.to_dict(),
        receipt.to_dict(),
        install_root=install_root,
    )
    return {
        "manifest": manifest,
        "install_root": install_root,
        "install_path": install_path,
        "receipt": receipt,
        "static": static,
        "browser": browser,
        "desktop": desktop,
    }


def _setup(tmp_path: Path) -> dict[str, object]:
    v1 = _install_version(
        tmp_path,
        version="1.0.0",
        body="version-one",
        port=9501,
    )
    v2 = _install_version(
        tmp_path,
        version="2.0.0",
        body="version-two",
        port=9502,
    )
    desktop_root = tmp_path / "desktop-apps"
    applications_root = tmp_path / "applications"
    request = DesktopAppRegistrationRequest.from_payloads(
        v1["desktop"].to_dict(),
        v1["browser"].to_dict(),
        v1["static"].to_dict(),
        v1["receipt"].to_dict(),
        approved_desktop_app_plan_sha256=v1["desktop"].sha256(),
        approved_desktop_permissions=v1["desktop"].requested_desktop_permissions,
    )
    installed = DesktopAppInstaller().install(
        request,
        install_root=v1["install_root"],
        desktop_root=desktop_root,
        applications_root=applications_root,
    )
    return {
        "v1": v1,
        "v2": v2,
        "desktop_root": desktop_root,
        "applications_root": applications_root,
        "installed": installed,
        "receipt_root": tmp_path / "transition-receipts",
    }


def _update_plan(state: dict[str, object]) -> DesktopUpdatePlan:
    v1 = state["v1"]
    v2 = state["v2"]
    return plan_desktop_update(
        Path(state["installed"].bundle_path),
        v2["browser"].to_dict(),
        v2["static"].to_dict(),
        v2["receipt"].to_dict(),
        install_root=v1["install_root"],
        desktop_root=state["desktop_root"],
        applications_root=state["applications_root"],
    )


def _update_request(
    state: dict[str, object],
    plan: DesktopUpdatePlan,
) -> DesktopUpdateRequest:
    v2 = state["v2"]
    return DesktopUpdateRequest.from_payloads(
        plan.to_dict(),
        v2["browser"].to_dict(),
        v2["static"].to_dict(),
        v2["receipt"].to_dict(),
        approved_update_plan_sha256=plan.sha256(),
        approved_active_grant_sha256=plan.active_grant_sha256,
        approved_candidate_desktop_plan_sha256=plan.candidate_desktop_plan_sha256,
        approved_update_permissions=plan.requested_update_permissions,
    )


def _execute_update(state: dict[str, object]):
    plan = _update_plan(state)
    request = _update_request(state, plan)
    result = DesktopUpdateService().execute(
        request,
        install_root=state["v1"]["install_root"],
        desktop_root=state["desktop_root"],
        applications_root=state["applications_root"],
        receipt_root=state["receipt_root"],
    )
    return plan, result



def _rollback_request(
    rollback: DesktopRollbackPlan,
    update_receipt: DesktopUpdateReceipt,
) -> DesktopRollbackRequest:
    return DesktopRollbackRequest.from_payloads(
        rollback.to_dict(),
        update_receipt.to_dict(),
        approved_rollback_plan_sha256=rollback.sha256(),
        approved_active_grant_sha256=rollback.active_grant_sha256,
        approved_target_grant_sha256=rollback.target_grant_sha256,
        approved_rollback_permissions=rollback.requested_rollback_permissions,
    )



# R5E is a disposable installed-guest desktop lifecycle test. Helpers above
# are copied from the existing v0.40 regression fixture at commit 293b841.
# None of their simulated package receipts represent authenticated releases.
import os as r5e_os
import sys as r5e_sys
import time as r5e_time
import socket as r5e_socket
import subprocess as r5e_subprocess
import urllib.request as r5e_url
from pathlib import Path as R5EPath

R5E_SERVER = r'''
import os, json, hashlib, sys
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
asset, data, version, port = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3], int(sys.argv[4])
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass
    def do_GET(self):
        if self.path != '/health':
            self.send_error(404)
            return
        wire = json.dumps({'uid': os.getuid(), 'version': version,
            'asset_sha256': hashlib.sha256(asset.read_bytes()).hexdigest(),
            'data': json.loads(data.read_text())}, sort_keys=True).encode()
        self.send_response(200)
        self.send_header('Content-Length', str(len(wire)))
        self.end_headers()
        self.wfile.write(wire)
ThreadingHTTPServer(('127.0.0.1', port), Handler).serve_forever(poll_interval=0.2)
'''

def r5e_live(root, asset, data, version):
    server = root / 'r5e-test-server.py'
    if server.is_symlink():
        raise ValueError('R5E unsafe test server')
    if not server.exists():
        server.write_text(R5E_SERVER, encoding='utf-8')
    elif server.read_text(encoding='utf-8') != R5E_SERVER:
        raise ValueError('R5E test server modified')
    with r5e_socket.socket() as reserved:
        reserved.bind(('127.0.0.1', 0))
        port = reserved.getsockname()[1]
    process = r5e_subprocess.Popen(
        [r5e_sys.executable, '-u', str(server), str(asset), str(data), version, str(port)],
        cwd=str(root), stdin=r5e_subprocess.DEVNULL, stdout=r5e_subprocess.DEVNULL,
        stderr=r5e_subprocess.DEVNULL)
    opener = r5e_url.build_opener(r5e_url.ProxyHandler({}))
    try:
        deadline = r5e_time.monotonic() + 12
        while True:
            if process.poll() is not None:
                raise RuntimeError('R5E test process exited')
            try:
                with opener.open('http://127.0.0.1:' + str(port) + '/health', timeout=1) as reply:
                    result = json.loads(reply.read())
                break
            except OSError:
                if r5e_time.monotonic() >= deadline:
                    raise RuntimeError('R5E test process did not become healthy')
                r5e_time.sleep(.1)
        if (result.get('uid') != 1000 or result.get('version') != version
                or result.get('asset_sha256') != hashlib.sha256(asset.read_bytes()).hexdigest()
                or result.get('data') != json.loads(data.read_text())):
            raise ValueError('R5E process, asset, or state mismatch')
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except r5e_subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)

def r5e_guest_check(source, phase):
    if r5e_os.getuid() != 1000 or phase not in (1, 2, 3):
        raise ValueError('R5E requires ordinary UID-1000 installed guest')
    root = R5EPath.home() / '.local' / 'state' / 'phios' / 'r5e-desktop-test'
    if root.is_symlink():
        raise ValueError('R5E unsafe fixture root')
    state_path, data = root / 'lifecycle.json', root / 'user-data.json'
    if phase == 1:
        if root.exists():
            raise ValueError('R5E fixture already exists on first boot')
        root.mkdir(parents=True, mode=0o700)
        # Existing R5D's durable state writer and dir-sync are injected by host
        # earlier in this same *test-only* guest serial program.
        r5d_sync_directory(root.parent)
        fixture = _setup(root)
        v1, v2 = fixture['v1'], fixture['v2']
        entry = Path(_update_plan(fixture).desktop_entry_path)
        before_entry_sha = hashlib.sha256(entry.read_bytes()).hexdigest()
        r5d_write_state_durable(data, {
            'schema': 'r5e.fixture.user.v1', 'source_commit': source, 'counter': 7})
        asset_v1 = Path(v1['install_path']) / 'payload/dist/index.html'
        asset_v2 = Path(v2['install_path']) / 'payload/dist/index.html'
        r5e_live(root, asset_v1, data, 'version-one')
        before_data_sha = hashlib.sha256(data.read_bytes()).hexdigest()
        _, updated = _execute_update(fixture)
        if updated.receipt.status != 'updated':
            raise RuntimeError('R5E in-guest update was not executed')
        r5e_live(root, asset_v2, data, 'version-two')
        r5d_write_state_durable(data, {
            'schema': 'r5e.fixture.user.v2-incompatible', 'source_commit': source,
            'counter': 107})
        if json.loads(data.read_text())['schema'] == 'r5e.fixture.user.v1':
            raise ValueError('R5E incompatible test migration not observed')
        rollback = plan_desktop_rollback(
            updated.receipt.to_dict(), install_root=v1['install_root'],
            desktop_root=fixture['desktop_root'],
            applications_root=fixture['applications_root'])
        result = DesktopRollbackService().execute(
            _rollback_request(rollback, updated.receipt),
            install_root=v1['install_root'], desktop_root=fixture['desktop_root'],
            applications_root=fixture['applications_root'],
            receipt_root=fixture['receipt_root'])
        if result.receipt.status != 'rolled_back':
            raise RuntimeError('R5E in-guest rollback was not executed')
        # This recovery is ONLY for an internally generated fixed JSON fixture.
        r5d_write_state_durable(data, {
            'schema': 'r5e.fixture.user.v1', 'source_commit': source, 'counter': 7})
        if (hashlib.sha256(data.read_bytes()).hexdigest() != before_data_sha
                or hashlib.sha256(entry.read_bytes()).hexdigest() != before_entry_sha):
            raise ValueError('R5E rollback did not restore exact test bytes')
        r5e_live(root, asset_v1, data, 'version-one')
        state = {
            'source_commit': source, 'entry_path': str(entry),
            'entry_sha256': before_entry_sha, 'data_sha256': before_data_sha,
            'asset_path': str(asset_v1),
            'asset_sha256': hashlib.sha256(asset_v1.read_bytes()).hexdigest(),
            'update_receipt_sha256': updated.receipt.sha256(),
            'rollback_receipt_sha256': result.receipt.sha256(),
            'stage': 'rolled_back_v1',
        }
        r5d_write_state_durable(state_path, state)
        r5e_os.sync()
    else:
        if not root.is_dir() or state_path.is_symlink() or data.is_symlink():
            raise ValueError('R5E persisted test state missing or unsafe')
        state = json.loads(state_path.read_text())
        if (state.get('stage') != 'rolled_back_v1' or state.get('source_commit') != source):
            raise ValueError('R5E previous-boot lifecycle state invalid')
        entry, asset_v1 = R5EPath(state['entry_path']), R5EPath(state['asset_path'])
        if (entry.is_symlink() or asset_v1.is_symlink()
                or hashlib.sha256(entry.read_bytes()).hexdigest() != state['entry_sha256']
                or hashlib.sha256(asset_v1.read_bytes()).hexdigest() != state['asset_sha256']
                or hashlib.sha256(data.read_bytes()).hexdigest() != state['data_sha256']):
            raise ValueError('R5E installed guest lost rollback/data continuity')
        r5e_live(root, asset_v1, data, 'version-one')
    report = {
        'schema': 'phios.r5e_installed_desktop_observation.v0.1',
        'scope': 'disposable_installed_qemu_guest_test_only',
        'source_commit': source, 'phase': phase,
        'boot_id': R5EPath('/proc/sys/kernel/random/boot_id').read_text().strip().replace('-', ''),
        'uid': 1000, 'active_version': '1.0.0',
        'fixture_app_process_healthy': True,
        'desktop_registration_executed_in_guest': True,
        'desktop_update_and_rollback_executed_in_guest': True,
        'data_sha256': state['data_sha256'],
        'update_receipt_sha256': state['update_receipt_sha256'],
        'rollback_receipt_sha256': state['rollback_receipt_sha256'],
        'real_app_install_service_executed': False,
        'publisher_identity_verified': False,
        'production_install_authority': False,
        'physical_hardware_qualified': False,
        'production_release_authorized': False,
    }
    print('PHIOS_R5E_GUEST_OK:' + json.dumps(report, sort_keys=True), flush=True)
    return report
