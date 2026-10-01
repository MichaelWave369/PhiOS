"""Qualify installation only on a fresh, locally created 32 GiB virtual disk."""
from __future__ import annotations

import argparse
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


def failed_boot(common: list[str], output: Path, receipt: dict[str, Any]) -> None:
    """Require an observed kernel/root failure, never treat a timeout as proof."""
    qmp, serial = output / 'failed-boot-qmp.sock', output / 'failed-boot-serial.log'
    command = common + ['-serial', f'file:{serial}', '-qmp', f'unix:{qmp},server=on,wait=off']
    receipt['commands'].append(command)
    with (output / 'failed-boot-qemu.log').open('w') as log:
        process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic() + 180
            while time.monotonic() < deadline:
                text = serial.read_text(errors='replace') if serial.exists() else ''
                if 'Kernel panic' in text or 'Unable to mount root fs' in text:
                    receipt['simulated_boot_failure_observed'] = True
                    break
                if 'login: ' in text or process.poll() is not None:
                    raise RuntimeError('the deliberately broken root unexpectedly booted or VM exited')
                time.sleep(1)
            else:
                raise RuntimeError('no specific unbootable-system failure was observed')
        finally:
            if process.poll() is None:
                capture_display(qmp, output, name='screen-failed-boot')
            stop(process)


def recover_live(common: list[str], iso: Path, output: Path, receipt: dict[str, Any]) -> None:
    qmp, serial = output / 'recovery-qmp.sock', output / 'recovery-live-serial.log'
    command = common + ['-drive', f'file={iso.resolve()},if=none,id=installation,format=raw,media=cdrom,readonly=on',
        '-device', 'ide-cd,drive=installation,bootindex=1', '-serial', f'file:{serial}',
        '-qmp', f'unix:{qmp},server=on,wait=off']
    receipt['commands'].append(command)
    with (output / 'recovery-live-qemu.log').open('w') as log:
        process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic() + 900
            login_sent = False
            while time.monotonic() < deadline:
                text = serial.read_text(errors='replace') if serial.exists() else ''
                if 'PHIOS_BOOT_FAILED' in text or process.poll() is not None:
                    raise RuntimeError('live system/root/EFI recovery fixture failed')
                if 'PHIOS_LOGIN_REQUIRED:' in text and not login_sent:
                    enter_live_login(qmp)
                    login_sent = True
                marker = 'PHIOS_OS_RESTORE_OK:' + receipt['recovery_checkpoint_generation']
                if marker in text:
                    assert 'PHIOS_OS_RESTORE_CANCEL_OK' in text
                    receipt['matched_root_efi_restored'] = True
                    break
                time.sleep(1)
            else:
                raise RuntimeError('live-media recovery timed out')
        finally:
            if process.poll() is None:
                capture_display(qmp, output, name='screen-recovery-live')
            stop(process)
            if not receipt.get('matched_root_efi_restored') and serial.exists():
                print('\n'.join(serial.read_text(errors='replace').splitlines()[-160:]))


def install_live(common: list[str], iso: Path, output: Path, source: str, receipt: dict[str, Any],
                 *, signed_update: bool) -> None:
    for attempt in range(2 if signed_update else 1):
        prefix = 'install-live' if attempt == 0 else 'interrupted-resume-live'
        qmp, serial = output / (prefix + '-qmp.sock'), output / (prefix + '-serial.log')
        command = common + ['-drive', f'file={iso.resolve()},if=none,id=installation,format=raw,media=cdrom,readonly=on',
            '-device', 'ide-cd,drive=installation,bootindex=1', '-serial', f'file:{serial}',
            '-qmp', f'unix:{qmp},server=on,wait=off']
        receipt['commands'].append(command)
        interrupted = False
        with (output / (prefix + '-qemu.log')).open('w') as log:
            process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
            try:
                deadline = time.monotonic() + (1800 if receipt['accelerator'] == 'kvm' else 3000)
                login_sent = False
                while time.monotonic() < deadline:
                    text = serial.read_text(errors='replace') if serial.exists() else ''
                    if 'PHIOS_BOOT_FAILED' in text or process.poll() is not None:
                        raise RuntimeError('live installer or signed package qualification failed')
                    if 'UEFI Interactive Shell' in text:
                        raise RuntimeError('firmware did not boot the installation ISO')
                    if 'PHIOS_LOGIN_REQUIRED:' in text and not login_sent:
                        enter_live_login(qmp)
                        login_sent = True
                    if signed_update and 'PHIOS_SIGNED_STAGE_IN_PROGRESS' in text:
                        if attempt != 0:
                            raise RuntimeError('unexpected second package interruption')
                        updates = re.findall(r'PHIOS_SIGNED_UPDATE_OK:(\{[^\r\n]+\})', text)
                        if len(updates) != 1:
                            raise RuntimeError('exact successful signed package transaction not observed')
                        for case in ['missing-signature', 'wrong-key', 'tampered', 'expired', 'replay', 'dependency']:
                            if 'PHIOS_SIGNED_REFUSAL_OK:' + case not in text:
                                raise RuntimeError('signed update refusal case missing: ' + case)
                        receipt['signed_update_transaction'] = json.loads(updates[0])
                        receipt['signed_update_refusals_observed'] = True
                        receipt['interrupted_signed_transaction_observed'] = True
                        interrupted = True
                        break
                    if f'PHIOS_INSTALLED_DISK_OK:{source}' in text:
                        if signed_update:
                            if attempt != 1 or 'PHIOS_INTERRUPTED_UPDATE_HELD_OK' not in text:
                                raise RuntimeError('actual interrupted-stage recovery not observed')
                            receipt['interrupted_update_active_root_preserved'] = True
                        elif 'PHIOS_INSTALL_CANCEL_OK' not in text or 'PHIOS_INSTALLED_SEED_OK:' not in text:
                            raise RuntimeError('production cancellation and data seed not observed')
                        generations = re.findall(r'PHIOS_OS_CHECKPOINT_OK:([0-9a-f]{32})', text)
                        if receipt['recovery_requested']:
                            if len(generations) != 1:
                                raise RuntimeError('explicit recovery checkpoint not observed')
                            receipt['recovery_checkpoint_generation'] = generations[0]
                            if signed_update and generations[0] != receipt['signed_update_transaction']['generation']:
                                raise RuntimeError('recovery selected a different update checkpoint')
                        receipt['installed'] = True
                        return
                    time.sleep(1)
                else:
                    raise RuntimeError('live install/update qualification timed out')
            finally:
                if process.poll() is None:
                    try:
                        capture_display(qmp, output, name='screen-' + prefix)
                    except (OSError, ValueError, RuntimeError) as exc:
                        receipt['display_capture_error'] = str(exc)
                stop(process, abrupt=interrupted)
                if not receipt['installed'] and not interrupted and serial.exists():
                    print('\n'.join(serial.read_text(errors='replace').splitlines()[-160:]))
    raise RuntimeError('disposable installed target never qualified')


def qualify(iso: Path, source: str, output: Path, *, recovery: bool = False, signed_update: bool = False, fixture_free: bool = False) -> None:
    if not re.fullmatch(r"[0-9a-f]{40}", source) or not iso.is_file() or output.exists():
        raise ValueError("exact source/ISO and a new owned evidence destination are required")
    if fixture_free and (signed_update or not recovery):
        raise ValueError('normal ISO qualification requires recovery; signed fixture transitions use the separate QA lane')
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
    if signed_update:
        if not recovery:
            raise ValueError('signed-update qualification includes matched root/EFI recovery')
        common += ['-fw_cfg', 'name=opt/phios-ci-signed-updates,string=enabled']
    digest = hashlib.sha256()
    with iso.open("rb") as handle:
        for block in iter(lambda: handle.read(1024**2), b""):
            digest.update(block)
    receipt: dict[str, Any] = {"schema_version": "phios.installed-boot-evidence.v1", "source_commit": source,
          "iso_sha256": digest.hexdigest(), "accelerator": accelerator, "disk_serial": "PHIOS_CI_BLANK",
          "disk_bytes": 32 * 1024**3, "commands": [], "installed": False, "no_iso_boot_passed": False,
          "abrupt_virtual_restart_passed": False, "boot_ids": [], "ci_serial_console_injected": not fixture_free,
          'explicit_serial_console_password_login': fixture_free, 'fixture_free_requested': fixture_free,
          'fixture_free_installed_qualified': False,
          "hardware_qualified": False, "release_ready": False, 'recovery_requested': recovery,
          'simulated_boot_failure_observed': False, 'matched_root_efi_restored': False,
          'whole_os_recovery_passed': False, 'signed_package_application_qualified': False}
    receipt.update(signed_update_requested=signed_update, signed_update_refusals_observed=False,
        interrupted_signed_transaction_observed=False, interrupted_update_active_root_preserved=False)
    try:
        if fixture_free:
            from qemu_normal_live import drive_live
            installed = drive_live(common, iso, source, output, receipt, stage='install')
            receipt['recovery_checkpoint_generation'] = installed['generation']
            receipt['installed'] = True
        else:
            install_live(common, iso, output, source, receipt, signed_update=signed_update)
        # Boot the new disk twice with no ISO attached, normal password/PAM
        # logins and actual greetd keyboard input. Between boots kill QEMU so
        # acknowledged data must survive loss of the guest's memory.
        for phase in ([1, 2, 3] if recovery else [1, 2]):
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
                                        # A traceback can arrive in several serial
                                        # reads. Preserve its actual exception and
                                        # failing line before stopping the guest.
                                        drain_deadline = time.monotonic() + 3
                                        while time.monotonic() < drain_deadline:
                                            try:
                                                extra = channel.recv(65536)
                                            except socket.timeout:
                                                continue
                                            if not extra:
                                                break
                                            transcript.write(extra)
                                            transcript.flush()
                                            text += extra.decode(errors="replace")
                                        print("\n".join(text.splitlines()[-40:]))
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
                            program = Path(__file__).with_name("installed_probe.py").read_text() + \
                                f"\nprobe({source!r}, {phase}, signed_update={signed_update!r})\n"
                            if Path(__file__).with_name('proof_smoke.py').exists():
                                program = Path(__file__).with_name('proof_smoke.py').read_text() + \
                                    (f'\nproof_workflow({source!r})\n' if phase == 1 else f'\nhistorical_proof({source!r})\n') + \
                                    program.replace('from __future__ import annotations\n', '')
                            if fixture_free and phase == 1:
                                program = Path(__file__).with_name('normal_seed.py').read_text() + '\nseed_normal()\n' + \
                                    program.replace('from __future__ import annotations\n', '')
                            # Keep each input line below the terminal's canonical
                            # line bound; a growing base64 -c command can exceed it.
                            channel.sendall(("python - <<'PHIOS_INSTALLED_PROBE'\n" + program +
                                "\nPHIOS_INSTALLED_PROBE\n").encode())
                            result = wait_for(r"PHIOS_INSTALLED_CHECK_OK:(\{[^\r\n]+\})")
                            details = json.loads(result[1])
                            if details["source_commit"] != source or details["phase"] != phase:
                                raise RuntimeError("installed receipt identity mismatch")
                            if Path(__file__).with_name('proof_smoke.py').exists():
                                if phase == 1:
                                    proof_match = re.search(r'PHIOS_LINUX_PROOF_OK:(\{[^\r\n]+\})', text)
                                    if proof_match is None:
                                        raise RuntimeError('actual governed proof receipt missing')
                                    proof = json.loads(proof_match[1])
                                    if proof['source_commit'] != source or not all(proof[k] is True for k in
                                        ['sudo_password_authentication', 'agent_store_denied', 'agent_broker_denied',
                                         'cancel_passed', 'replay_refused', 'expiry_refused']):
                                        raise RuntimeError('governed proof refusal/identity evidence missing')
                                    receipt['linux_governed_workflow'] = proof
                                elif 'PHIOS_LINUX_PROOF_HISTORY_INACTIVE:' not in text:
                                    raise RuntimeError('old-boot proof authority refusal missing')
                                if phase == (3 if recovery else 2):
                                    receipt['linux_governed_workflow_qualified'] = True
                            receipt["boot_ids"].append(details["boot_id"])
                            receipt["record_sha256"] = details["record_sha256"]
                            capture_display(qmp, output, name=f"screen-installed-{phase}")
                            if recovery and phase == 2:
                                # Test-only administration through normal sudo
                                # password authentication; never shipped as a
                                # production effect or a confirmation bypass.
                                damage = "from pathlib import Path; import os; " + \
                                    "[Path('/boot/'+p).write_bytes(b'intentional CI boot corruption') for p in " + \
                                    "['initramfs-linux.img','initramfs-linux-fallback.img']]; " + \
                                    "Path('/usr/bin/wayfire').rename('/usr/bin/wayfire.failed-ci'); " + \
                                    "os.sync(); print('PHIOS_OS_DAMAGE_OK:'+str(os.geteuid()),flush=True)"
                                channel.sendall((f"printf '%s\\n' '{PASSWORD}' | sudo -S python -c \"{damage}\"\n").encode())
                                wait_for(r'PHIOS_OS_DAMAGE_OK:0')
                finally:
                    if process.poll() is None and not (output / f"screen-installed-{phase}.ppm").exists():
                        try:
                            capture_display(qmp, output, name=f"screen-installed-{phase}-failure")
                        except (OSError, ValueError, RuntimeError):
                            pass
                    stop(process, abrupt=(phase == 1))
            if recovery and phase == 2:
                failed_boot(common, output, receipt)
                if fixture_free:
                    restored = drive_live(common, iso, source, output, receipt, stage='restore',
                                          generation=receipt['recovery_checkpoint_generation'])
                    if restored['generation'] != receipt['recovery_checkpoint_generation']:
                        raise RuntimeError('normal recovery restored a different checkpoint')
                    receipt['matched_root_efi_restored'] = True
                else:
                    recover_live(common, iso, output, receipt)
        if len(set(receipt["boot_ids"])) != (3 if recovery else 2):
            raise RuntimeError("a distinct installed reboot was not observed")
        receipt["no_iso_boot_passed"] = True
        receipt["abrupt_virtual_restart_passed"] = True
        if recovery:
            receipt['whole_os_recovery_passed'] = (receipt['simulated_boot_failure_observed'] and
                receipt['matched_root_efi_restored'])
        if signed_update:
            receipt['signed_package_application_qualified'] = (receipt['whole_os_recovery_passed'] and
                receipt['signed_update_refusals_observed'] and receipt['interrupted_signed_transaction_observed'] and
                receipt['interrupted_update_active_root_preserved'])
        if fixture_free:
            receipt['fixture_free_installed_qualified'] = (receipt['whole_os_recovery_passed'] and
                receipt.get('linux_governed_workflow_qualified') is True and len(set(receipt['boot_ids'])) == 3)
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
    parser.add_argument('--recovery', action='store_true', help='Also damage and recover only this disposable installed disk')
    parser.add_argument('--signed-update', action='store_true', help='Also qualify signed packages and actual interrupted staging')
    parser.add_argument('--fixture-free', action='store_true', help='Install/recover the unmodified normal ISO using its limited live sudo and explicitly reviewed serial-console login')
    args = parser.parse_args()
    qualify(args.iso, args.source, args.output.resolve(), recovery=args.recovery, signed_update=args.signed_update, fixture_free=args.fixture_free)
