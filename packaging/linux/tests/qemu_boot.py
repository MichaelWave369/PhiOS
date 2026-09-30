"""Boot a disposable, network-disconnected UEFI VM and preserve exact evidence."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import socket
import subprocess
import time
from pathlib import Path


def boot(iso: Path, source: str, output: Path, *, timeout: int = 600) -> None:
    if re.fullmatch(r"[0-9a-f]{40}", source) is None or not iso.is_file():
        raise ValueError("an existing ISO and exact source commit are required")
    output.mkdir(parents=True, exist_ok=True)
    code = Path("/usr/share/OVMF/OVMF_CODE_4M.fd")
    variables = Path("/usr/share/OVMF/OVMF_VARS_4M.fd")
    if not code.is_file() or not variables.is_file():
        raise ValueError("OVMF UEFI firmware is required")
    qemu = shutil.which("qemu-system-x86_64")
    if qemu is None:
        raise ValueError("qemu-system-x86_64 is required")
    variables_copy = output / "OVMF_VARS.fd"
    shutil.copyfile(variables, variables_copy)
    serial = output / "serial.log"
    qmp_path = output / "qmp.sock"
    command = [qemu, "-machine", "q35,accel=tcg", "-cpu", "max", "-m", "4096", "-smp", "2",
               "-drive", f"if=pflash,format=raw,readonly=on,file={code}",
               "-drive", f"if=pflash,format=raw,file={variables_copy}",
               "-cdrom", str(iso.resolve()), "-boot", "d", "-nic", "none", "-vga", "none",
               "-device", "virtio-vga", "-display", "none", "-monitor", "none",
               "-serial", f"file:{serial}", "-qmp", f"unix:{qmp_path},server=on,wait=off"]
    digest = hashlib.sha256()
    with iso.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    receipt = {"schema_version": "phios.live-boot-evidence.v1", "source_commit": source,
               "iso_sha256": digest.hexdigest(), "command": command,
               "boot_passed": False, "hardware_qualified": False, "release_ready": False}
    with (output / "qemu.log").open("w") as log:
        process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic() + timeout
            marker = f"PHIOS_BOOT_OK:{source}"
            while time.monotonic() < deadline:
                text = serial.read_text(errors="replace") if serial.exists() else ""
                if "PHIOS_BOOT_FAILED" in text:
                    raise RuntimeError("live-image qualification fixture failed")
                if marker in text:
                    break
                if process.poll() is not None:
                    raise RuntimeError(f"QEMU exited before qualification (exit {process.returncode})")
                time.sleep(1)
            else:
                raise RuntimeError("UEFI boot/session qualification timed out")
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                client.settimeout(15)
                client.connect(str(qmp_path))
                stream = client.makefile("rwb")
                json.loads(stream.readline())
                for request in [{"execute": "qmp_capabilities"},
                                {"execute": "screendump", "arguments": {
                                    "filename": str((output / "screen.ppm").resolve())}}]:
                    stream.write(json.dumps(request).encode() + b"\n")
                    stream.flush()
                    while True:
                        response = json.loads(stream.readline())
                        if "error" in response:
                            raise RuntimeError(f"QMP evidence capture failed: {response['error']}")
                        if "return" in response:
                            break
            receipt["boot_passed"] = True
            print(f"UEFI live boot and non-root session passed for ISO {receipt['iso_sha256']}")
        finally:
            process.terminate()
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
            (output / "boot-evidence.json").write_text(json.dumps(receipt, indent=2) + "\n")
            if not receipt["boot_passed"] and serial.exists():
                print("\n".join(serial.read_text(errors="replace").splitlines()[-160:]))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iso", required=True, type=Path)
    parser.add_argument("--source", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    boot(args.iso, args.source, args.output.resolve())
