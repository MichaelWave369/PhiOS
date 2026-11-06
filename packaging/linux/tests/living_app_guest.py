"""R5D installed-VM guest probe: execute an actual test app and persistent state.

This source is injected by the HOST ONLY during the disposable QEMU
qualification. It is not installed into a release image or offered to users.
Its loopback Python service is a narrow, test-owned process, not a signed
PhiOS App Platform application.
"""
import hashlib as r5d_hashlib
import json as r5d_json
import os as r5d_os
from pathlib import Path as R5DPath
import socket as r5d_socket
import subprocess as r5d_subprocess
import sys as r5d_sys
import time as r5d_time
import urllib.request as r5d_urlrequest

R5D_GUEST_APP = r'''
import json
import os
from pathlib import Path
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

data_path = Path(sys.argv[1])
source_commit = sys.argv[2]
port = int(sys.argv[3])
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        return

    def do_GET(self):
        if self.path == "/health":
            body = {"app": "phios-r5d-test-only", "source_commit": source_commit,
                    "process_uid": os.getuid(), "status": "running"}
        elif self.path == "/state":
            body = json.loads(data_path.read_text(encoding="utf-8"))
        else:
            self.send_error(404)
            return
        wire = json.dumps(body, sort_keys=True).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(wire)))
        self.end_headers()
        self.wfile.write(wire)

    def do_POST(self):
        if self.path != "/touch":
            self.send_error(404)
            return
        state = json.loads(data_path.read_text(encoding="utf-8"))
        state["counter"] += 1
        target = data_path.with_suffix(".new")
        if target.exists() or target.is_symlink():
            raise RuntimeError("R5D stale pending user-data write")
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(target, flags, 0o600)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(json.dumps(state, sort_keys=True) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(target, data_path)
            directory = os.open(
                data_path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
                | getattr(os, "O_NOFOLLOW", 0),
            )
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            if target.exists():
                target.unlink()
        wire = json.dumps(state, sort_keys=True).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Length", str(len(wire)))
        self.end_headers()
        self.wfile.write(wire)

ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever(poll_interval=0.2)
'''


def r5d_sync_directory(path):
    """Make a newly created test directory entry durable across abrupt VM halt."""
    fd = r5d_os.open(
        path, r5d_os.O_RDONLY | getattr(r5d_os, "O_DIRECTORY", 0)
        | getattr(r5d_os, "O_NOFOLLOW", 0),
    )
    try:
        r5d_os.fsync(fd)
    finally:
        r5d_os.close(fd)


def r5d_write_state_durable(state_file, state):
    """Atomic test-user-data write with synced file bytes AND parent directory."""
    pending = state_file.with_suffix(".new")
    if pending.exists() or pending.is_symlink():
        raise ValueError("R5D pending state is unexpected; refusing to overwrite")
    flags = (r5d_os.O_WRONLY | r5d_os.O_CREAT | r5d_os.O_EXCL
             | getattr(r5d_os, "O_NOFOLLOW", 0))
    fd = r5d_os.open(pending, flags, 0o600)
    try:
        with r5d_os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(r5d_json.dumps(state, sort_keys=True) + "\n")
            handle.flush()
            r5d_os.fsync(handle.fileno())
        r5d_os.replace(pending, state_file)
        r5d_sync_directory(state_file.parent)
    finally:
        if pending.exists():
            pending.unlink()


def r5d_normalize_boot_id(value):
    """Match installed_probe.py's UUID normalization in the same VM boot."""
    return value.strip().replace("-", "")


def r5d_guest_live_check(source, phase):
    """Verify process health + state from preceding boot, then mutate test data."""
    if phase not in (1, 2, 3):
        raise ValueError("R5D guest probe supports installed boot phases 1-3")
    if r5d_os.getuid() != 1000:
        raise ValueError("R5D guest probe requires installed test user UID 1000")
    root = R5DPath.home() / ".local" / "state" / "phios" / "r5d-living-test"
    if root.is_symlink():
        raise ValueError("R5D state root symlink refused")
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    # The harness hard-kills QEMU after phase one. Persist the new directory
    # entry itself, not only files inside the directory.
    r5d_sync_directory(root.parent)
    state_file = root / "app-user-state.json"
    app_file = root / "test-only-loopback-app.py"
    if state_file.is_symlink() or app_file.is_symlink():
        raise ValueError("R5D fixture file symlink refused")
    if phase == 1:
        if state_file.exists():
            raise ValueError("R5D phase-one fresh state unexpectedly exists")
        r5d_write_state_durable(state_file, {
            "schema": "phios.r5d_guest_user_data.v1",
            "source_commit": source,
            "counter": 0,
            "owner_uid": 1000,
        })
    elif not state_file.is_file():
        raise ValueError("R5D persisted data missing after installed VM reboot")
    state = r5d_json.loads(state_file.read_text(encoding="utf-8"))
    if (
        state.get("schema") != "phios.r5d_guest_user_data.v1"
        or state.get("source_commit") != source
        or type(state.get("counter")) is not int
        or state["counter"] != phase - 1
        or state.get("owner_uid") != 1000
    ):
        raise ValueError("R5D previous-boot user data did not persist correctly")
    app_file.write_text(R5D_GUEST_APP, encoding="utf-8")
    app_file.chmod(0o600)

    with r5d_socket.socket() as reserved:
        reserved.bind(("127.0.0.1", 0))
        port = reserved.getsockname()[1]
    proc = r5d_subprocess.Popen(
        [r5d_sys.executable, "-u", str(app_file), str(state_file), source, str(port)],
        cwd=str(root), stdin=r5d_subprocess.DEVNULL,
        stdout=r5d_subprocess.DEVNULL, stderr=r5d_subprocess.DEVNULL,
    )
    opener = r5d_urlrequest.build_opener(r5d_urlrequest.ProxyHandler({}))
    base = "http://127.0.0.1:" + str(port)
    try:
        deadline = r5d_time.monotonic() + 12
        while True:
            if proc.poll() is not None:
                raise RuntimeError("R5D installed VM app process exited before health check")
            try:
                with opener.open(base + "/health", timeout=1) as response:
                    health = r5d_json.loads(response.read())
                break
            except OSError:
                if r5d_time.monotonic() >= deadline:
                    raise RuntimeError("R5D installed app did not answer HTTP health probe")
                r5d_time.sleep(0.1)
        if health != {
            "app": "phios-r5d-test-only", "source_commit": source,
            "process_uid": 1000, "status": "running",
        }:
            raise ValueError("R5D installed guest process identity or health mismatch")
        with opener.open(base + "/state", timeout=2) as response:
            observed = r5d_json.loads(response.read())
        if observed != state:
            raise ValueError("R5D app process could not read previous-boot persisted state")
        if phase in (1, 2):
            request = r5d_urlrequest.Request(base + "/touch", data=b"", method="POST")
            with opener.open(request, timeout=2) as response:
                changed = r5d_json.loads(response.read())
            if changed["counter"] != phase:
                raise ValueError("R5D app process did not persist expected user write")
        else:
            changed = state
        persisted = r5d_json.loads(state_file.read_text(encoding="utf-8"))
        if persisted != changed:
            raise ValueError("R5D user-data file disagrees with live app response")
        boot_id = r5d_normalize_boot_id(
            R5DPath("/proc/sys/kernel/random/boot_id").read_text()
        )
        report = {
            "schema": "phios.r5d_guest_observation.v0.1",
            "scope": "disposable_installed_qemu_guest_test_only",
            "source_commit": source,
            "phase": phase,
            "boot_id": boot_id,
            "test_app_process_http_healthy": True,
            "test_app_user_data_persisted_across_boot": phase > 1,
            "expected_persisted_counter": phase if phase < 3 else 2,
            "data_sha256": r5d_hashlib.sha256(state_file.read_bytes()).hexdigest(),
            "publisher_identity_verified": False,
            "signed_app_artifact_installed": False,
            "app_platform_update_and_rollback_executed_inside_guest": False,
            "user_data_general_rollback_verified": False,
            "production_install_authority": False,
        }
        print("PHIOS_R5D_GUEST_APP_OK:" + r5d_json.dumps(report, sort_keys=True), flush=True)
        return report
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except r5d_subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
