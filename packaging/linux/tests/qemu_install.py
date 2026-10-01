"""Qualify installation only on a fresh, locally created 32 GiB virtual disk."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import shutil
import socket
import subprocess
import time
from pathlib import Path
from typing import Any

from qemu_boot import capture_display, enter_live_login, qmp_request

PASSWORD = "phios-qa-only-2026"  # Same public ephemeral test credential as live fixture.


def send_text(qmp: Path, value: str) -> None:
    for key in [*value, "ret"]:
        code = "minus" if key == "-" else key
        qmp_request(qmp, {"execute": "send-key", "arguments": {
            "keys": [{"type": "qcode", "data": code}], "hold-time": 80}})
        time.sleep(0.12)


def stop(process: subprocess.Popen[Any], *, abrupt: bool = False) -> None:
    if abrupt:
        process.kill()
    else:
        process.terminate()
    try:
        process.wait(timeout=15)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def qualify(iso: Path, source: str, output: Path) -> None:
    if not re.fullmatch(r"[0-9a-f]{40}", source) or not iso.is_file() or output.exists():
        raise ValueError("exact source/ISO and a new owned evidence destination are required")
    output.mkdir(mode=0o700, parents=True)
    code = Path("/usr/share/OVMF/OVMF_CODE_4M.fd")
    variables = output / "OVMF_VARS.fd"
    shutil.copyfile("/usr/share/OVMF/OVMF_VARS_4M.fd", variables)
    disk = output / "target.qcow2"
    # There is no caller-supplied device/disk option. Never attach a host block
    # device, existing image, network, shared folder or other user's data.
    subprocess.run(["qemu-img", "create", "-f", "qcow2", str(disk), "32G"], check=True)
    accelerated = os.access("/dev/kvm", os.R_OK | os.W_OK)
    accelerator = "kvm" if accelerated else "tcg"
    common = ["qemu-system-x86_64", "-machine", f"q35,accel={accelerator}", "-cpu",
              "host" if accelerated else "max", "-m", "4096", "-smp", "2",
              "-drive", f"if=pflash,format=raw,readonly=on,file={code}",
              "-drive", f"if=pflash,format=raw,file={variables}",
              "-drive", f"file={disk},if=none,id=target,format=qcow2",
              "-device", "virtio-blk-pci,drive=target,serial=PHIOS_CI_BLANK,bootindex=2",
              "-nic", "none", "-vga", "none", "-device", "virtio-vga",
              "-display", "none", "-monitor", "none"]
    digest = hashlib.sha256()
    with iso.open("rb") as handle:
        for block in iter(lambda: handle.read(1024**2), b""):
            digest.update(block)
    receipt: dict[str, Any] = {"schema_version": "phios.installed-boot-evidence.v1", "source_commit": source,
          "iso_sha256": digest.hexdigest(), "accelerator": accelerator, "disk_serial": "PHIOS_CI_BLANK",
          "disk_bytes": 32 * 1024**3, "commands": [], "installed": False, "no_iso_boot_passed": False,
          "abrupt_virtual_restart_passed": False, "boot_ids": [], "ci_serial_console_injected": True,
          "hardware_qualified": False, "release_ready": False}
    try:
        # Installer first boot: the CI-only live fixture drives both cancellation
        # and exact typed confirmation through the unmodified production CLI.
        qmp = output / "live-qmp.sock"
        serial = output / "install-live-serial.log"
        # OVMF must receive one consistent boot-order mechanism. Mixing a
        # device bootindex with -boot d excluded the CD and selected the empty
        # target. Give the installation CD explicit priority over that target.
        command = common + ["-drive", f"file={iso.resolve()},if=none,id=installation,format=raw,media=cdrom,readonly=on",
                            "-device", "ide-cd,drive=installation,bootindex=1", "-serial", f"file:{serial}",
                            "-qmp", f"unix:{qmp},server=on,wait=off"]
        receipt["commands"].append(command)
        with (output / "install-live-qemu.log").open("w") as log:
            process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
            try:
                deadline = time.monotonic() + (1800 if accelerated else 3000)
                login_sent = False
                while time.monotonic() < deadline:
                    text = serial.read_text(errors="replace") if serial.exists() else ""
                    if "PHIOS_BOOT_FAILED" in text or process.poll() is not None:
                        raise RuntimeError("live installer qualification failed")
                    if "UEFI Interactive Shell" in text:
                        raise RuntimeError("firmware did not boot the installation ISO")
                    if "PHIOS_LOGIN_REQUIRED:" in text and not login_sent:
                        enter_live_login(qmp)
                        login_sent = True
                    if f"PHIOS_INSTALLED_DISK_OK:{source}" in text:
                        assert "PHIOS_INSTALL_CANCEL_OK" in text and "PHIOS_INSTALLED_SEED_OK:" in text
                        receipt["installed"] = True
                        break
                    time.sleep(1)
                else:
                    raise RuntimeError("installation qualification timed out")
            finally:
                if process.poll() is None:
                    try:
                        capture_display(qmp, output, name="screen-install-live")
                    except (OSError, ValueError, RuntimeError) as exc:
                        receipt["display_capture_error"] = str(exc)
                stop(process)
                if not receipt["installed"] and serial.exists():
                    print("\n".join(serial.read_text(errors="replace").splitlines()[-160:]))
        # Boot the new disk twice with no ISO attached, normal password/PAM
        # logins and actual greetd keyboard input. Between boots kill QEMU so
        # acknowledged data must survive loss of the guest's memory.
        for phase in [1, 2]:
            qmp = output / f"installed-{phase}-qmp.sock"
            serial_socket = output / f"installed-{phase}-serial.sock"
            command = common + ["-serial", f"unix:{serial_socket},server=on,wait=off",
                                "-qmp", f"unix:{qmp},server=on,wait=off"]
            receipt["commands"].append(command)
            with (output / f"installed-{phase}-qemu.log").open("w") as log:
                process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
                try:
                    deadline = time.monotonic() + 900
                    while not serial_socket.exists() and time.monotonic() < deadline:
                        if process.poll() is not None:
                            raise RuntimeError("installed VM exited before serial transport")
                        time.sleep(0.1)
                    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as channel:
                        channel.settimeout(1)
                        channel.connect(str(serial_socket))
                        text = ""
                        with (output / f"installed-{phase}-serial.log").open("wb") as transcript:
                            def wait_for(pattern: str) -> re.Match[str]:
                                nonlocal text
                                while time.monotonic() < deadline:
                                    match = re.search(pattern, text)
                                    if match:
                                        return match
                                    if process.poll() is not None:
                                        raise RuntimeError("installed guest exited during validation")
                                    try:
                                        chunk = channel.recv(65536)
                                    except socket.timeout:
                                        continue
                                    if not chunk:
                                        raise RuntimeError("installed serial transport closed")
                                    transcript.write(chunk)
                                    transcript.flush()
                                    text += chunk.decode(errors="replace")
                                    if "Traceback (most recent call last)" in text:
                                        raise RuntimeError("installed data or session validation failed")
                                raise RuntimeError("installed password login/qualification timed out")

                            wait_for(r"login: ")
                            channel.sendall(b"operator\n")
                            wait_for(r"Password:")
                            channel.sendall((PASSWORD + "\n").encode())
                            time.sleep(2)
                            channel.sendall(b"printf 'PHIOS_LOGIN_OK:%s\\n' \"$(id -u)\"\n")
                            wait_for(r"PHIOS_LOGIN_OK:1000")
                            time.sleep(3)
                            capture_display(qmp, output, name=f"screen-installed-{phase}-greeter")
                            qmp_request(qmp, {"execute": "send-key", "arguments": {"keys": [
                                {"type": "qcode", "data": key} for key in ["ctrl", "alt", "f1"]]}})
                            time.sleep(1)
                            send_text(qmp, "operator")
                            time.sleep(1)
                            send_text(qmp, PASSWORD)
                            program = Path(__file__).with_name("installed_probe.py").read_text() + f"\nprobe({source!r}, {phase})\n"
                            encoded = base64.b64encode(program.encode()).decode()
                            channel.sendall(f"python -c 'import base64; exec(base64.b64decode(\"{encoded}\"))'\n".encode())
                            result = wait_for(r"PHIOS_INSTALLED_CHECK_OK:(\{[^\r\n]+\})")
                            details = json.loads(result[1])
                            if details["source_commit"] != source or details["phase"] != phase:
                                raise RuntimeError("installed receipt identity mismatch")
                            receipt["boot_ids"].append(details["boot_id"])
                            receipt["record_sha256"] = details["record_sha256"]
                            capture_display(qmp, output, name=f"screen-installed-{phase}")
                finally:
                    if process.poll() is None and not (output / f"screen-installed-{phase}.ppm").exists():
                        try:
                            capture_display(qmp, output, name=f"screen-installed-{phase}-failure")
                        except (OSError, ValueError, RuntimeError):
                            pass
                    stop(process, abrupt=(phase == 1))
        if len(set(receipt["boot_ids"])) != 2:
            raise RuntimeError("a distinct installed reboot was not observed")
        receipt["no_iso_boot_passed"] = True
        receipt["abrupt_virtual_restart_passed"] = True
        print("Disposable installation, no-ISO graphical login, data restore and abrupt virtual restart passed")
    except BaseException as exc:
        receipt["error"] = str(exc)
        raise
    finally:
        (output / "installed-evidence.json").write_text(json.dumps(receipt, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iso", required=True, type=Path)
    parser.add_argument("--source", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    qualify(args.iso, args.source, args.output.resolve())
