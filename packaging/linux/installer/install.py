"""Experimental offline UEFI installer; only an explicitly confirmed zeroed disk.

Installed behind a root-owned `python -I` wrapper. No automatic disk selection,
erase-existing mode, confirmation bypass, remote request handler or shell eval.
"""
from __future__ import annotations

import argparse
import fcntl
import getpass
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

ENV = {"PATH": "/usr/bin", "LANG": "C.UTF-8", "HOME": "/root"}
SOURCE = Path("/run/archiso/bootmnt/arch/x86_64/airootfs.sfs")
IDENTITY = Path("/usr/share/phios/source-commit")
MINIMUM = 16 * 1024**3
REQUIRED = ("lsblk", "wipefs", "sgdisk", "udevadm", "mkfs.fat", "mkfs.btrfs",
            "mount", "umount", "rsync", "chroot", "arch-chroot", "btrfs", "blkid", "bootctl")


def run(*args: str, data: str | None = None) -> str:
    executable = shutil.which(args[0], path=ENV["PATH"])
    if executable is None:
        raise ValueError(f"required program unavailable: {args[0]}")
    result = subprocess.run([executable, *args[1:]], input=data, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            env=ENV, check=False)
    if result.returncode or "==> ERROR:" in result.stdout:
        # Password input is never included in a command, exception or receipt.
        raise RuntimeError(f"{args[0]} failed (exit {result.returncode}): {result.stdout[-4000:]}")
    return result.stdout


def validate_inventory(row: dict[str, Any], signatures: list[Any], *, busy: bool) -> dict[str, Any]:
    if row.get("type") != "disk" or row.get("ro") not in (False, 0):
        raise ValueError("target must be a writable whole disk")
    path = row.get("path")
    if not isinstance(path, str) or re.fullmatch(r"/dev/(sd[a-z]+|vd[a-z]+|nvme[0-9]+n[0-9]+|mmcblk[0-9]+)", path) is None:
        raise ValueError("unsupported or noncanonical disk path")
    if row.get("children") or any(row.get("mountpoints") or []) or busy:
        raise ValueError("mounted disks, swap, partitions and device holders are refused")
    if signatures or row.get("fstype") or row.get("pttype"):
        raise ValueError("used disks are refused; existing data is never erased by this installer")
    if type(row.get("size")) is not int or row["size"] < MINIMUM:
        raise ValueError("a disk of at least 16 GiB is required")
    serial = row.get("serial") or row.get("wwn")
    if not isinstance(serial, str) or not serial.strip():
        raise ValueError("a stable serial number or WWN is required")
    if any(ord(c) < 32 or ord(c) == 127 for c in serial):
        raise ValueError("disk identity contains unsafe control characters")
    return {"path": path, "size_bytes": row["size"], "serial_or_wwn": serial.strip(),
            "model": row.get("model"), "major_minor": row.get("maj:min")}


def inventory(device: str) -> dict[str, Any]:
    path = Path(device)
    if not path.is_absolute() or path.resolve() != path or not stat.S_ISBLK(path.stat().st_mode):
        raise ValueError("use the canonical /dev path of a real whole disk")
    run("udevadm", "settle")
    rows = json.loads(run("lsblk", "--json", "--bytes", "--paths", "--tree", "--output",
                         "NAME,PATH,TYPE,SIZE,RO,MODEL,SERIAL,WWN,MOUNTPOINTS,FSTYPE,PTTYPE,MAJ:MIN", device))["blockdevices"]
    if len(rows) != 1:
        raise ValueError("target inventory is ambiguous")
    info = path.stat()
    number = f"{os.major(info.st_rdev)}:{os.minor(info.st_rdev)}"
    sys_device = Path("/sys/dev/block") / number
    holders = sys_device / "holders"
    slaves = sys_device / "slaves"
    busy = bool(list(holders.iterdir()) or list(slaves.iterdir()))
    # lsblk sees mounts in this namespace; inspect swap and kernel mount IDs too.
    if any(line.split()[2] == number for line in Path("/proc/self/mountinfo").read_text().splitlines()):
        busy = True
    for line in Path("/proc/swaps").read_text().splitlines()[1:]:
        swap = Path(line.split()[0])
        if swap.exists() and swap.stat().st_rdev == info.st_rdev:
            busy = True
    signatures = json.loads(run("wipefs", "--no-act", "--json", device))["signatures"]
    identity = validate_inventory(rows[0], signatures, busy=busy)
    if identity["path"] != device or identity["major_minor"] != number:
        raise ValueError("block device identity changed during inventory")
    return identity


def verify_zeroed(device: str, size: int) -> None:
    """Probe every byte, including unsigned data with no filesystem signature."""
    fd = os.open(device, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        total = 0
        while chunk := os.read(fd, 8 * 1024**2):
            if chunk.count(0) != len(chunk):
                raise ValueError("target is not fully zeroed; no disk writes were performed")
            total += len(chunk)
        if total != size:
            raise ValueError("disk size changed or a read was incomplete")
    finally:
        os.close(fd)


def confirmation(identity: dict[str, Any], source: str, username: str, hostname: str) -> tuple[dict[str, Any], str]:
    plan = {"schema_version": "phios.blank-disk-install-plan.v1", "target": identity,
            "source_commit": source, "username": username, "hostname": hostname,
            "layout": {"gpt": True, "esp_bytes": 1024**3, "filesystem": "btrfs",
                       "subvolumes": ["@root", "@home", "@log", "@snapshots"]},
            "encrypted": False, "secure_boot": False, "firmware_variables_changed": False,
            "experimental": True, "release_ready": False}
    digest = hashlib.sha256(json.dumps(plan, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return plan, f"INSTALL {identity['path']} {digest}"


def validate_account(username: str, hostname: str) -> None:
    if re.fullmatch(r"[a-z][a-z0-9_-]{0,30}", username) is None or username in {
        "root", "phios", "phios-agent", "phios-greeter", "nobody",
    }:
        raise ValueError("choose a new lowercase account name; live/system accounts are reserved")
    if re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", hostname) is None:
        raise ValueError("invalid hostname")


def write(root: Path, name: str, content: str, *, mode: int = 0o644) -> None:
    path = root / name
    # The immutable source is trusted, but generated files must not follow its
    # absolute symlinks out of the installation target (notably /etc/os-release).
    if path.is_symlink():
        path.unlink()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, mode)
    with os.fdopen(fd, "w") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(path, mode)


def configure(root: Path, username: str, password: str, hostname: str, root_uuid: str, esp_uuid: str) -> None:
    for pattern in ["etc/sysusers.d/phios-live.conf", "etc/tmpfiles.d/phios-live.conf",
                    "etc/mkinitcpio.conf.d/archiso.conf", "etc/systemd/system/phios-live-*.service",
                    "etc/systemd/system/multi-user.target.wants/phios-live-*.service",
                    "etc/systemd/system/greetd.service.d/phios.conf", "usr/local/bin/phios-live-*",
                    "etc/sudoers.d/phios-live-installer", "etc/systemd/system/serial-getty@ttyS0.service"]:
        for path in root.glob(pattern):
            path.unlink()
    if (root / "etc/machine-id").exists():
        write(root, "etc/machine-id", "")
    random_seed = root / "var/lib/systemd/random-seed"
    random_seed.unlink(missing_ok=True)
    passwd = (root / "etc/passwd").read_text().splitlines()
    if any(line.split(":")[0] == username for line in passwd):
        raise ValueError("account already exists in source image")
    if any(line.startswith("phios:") for line in passwd):
        run("chroot", str(root), "userdel", "--force", "phios")
    if any(line.split(":")[2] == "1000" and not line.startswith("phios:") for line in passwd):
        raise ValueError("source has an unexpected UID 1000 account")
    groups = (root / "etc/group").read_text().splitlines()
    for line in groups:
        if line.split(":")[2] == "1000":
            if not line.startswith("phios:"):
                raise ValueError("source has an unexpected GID 1000 group")
            run("chroot", str(root), "groupdel", "phios")
    run("chroot", str(root), "groupadd", "--gid", "1000", username)
    run("chroot", str(root), "useradd", "--uid", "1000", "--gid", username, "--create-home",
        "--groups", "wheel", "--shell", "/bin/bash", username)
    run("chroot", str(root), "chpasswd", data=f"{username}:{password}\n")
    run("chroot", str(root), "usermod", "--lock", "root")
    home = root / "home" / username
    for path in [home, home / ".local", home / ".local/state", home / ".local/state/phios"]:
        path.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(path, 0o700)
        os.chown(path, 1000, 1000)
    write(root, "etc/sudoers.d/phios-admin", "%wheel ALL=(ALL:ALL) ALL\n", mode=0o440)
    run("chroot", str(root), "visudo", "--check")
    write(root, "etc/hostname", hostname + "\n")
    write(root, "etc/hosts", f"127.0.0.1 localhost\n::1 localhost\n127.0.1.1 {hostname}\n")
    write(root, "etc/greetd/config.toml", '[terminal]\nvt = 1\n[default_session]\n'
          'command = "tuigreet --cmd phios-session"\nuser = "phios-greeter"\n')
    write(root, "etc/sysusers.d/phios-system.conf", 'u phios-agent 1001 "Reserved isolated agent" /var/lib/phios-agent /usr/bin/nologin\n'
          'u phios-greeter - "PhiOS Greeter" /var/lib/phios-greeter /usr/bin/nologin\n')
    write(root, "etc/tmpfiles.d/phios-system.conf", "d /var/lib/phios-agent 0700 phios-agent phios-agent -\n")
    write(root, "etc/fstab", f"UUID={root_uuid} / btrfs defaults,noatime,compress=zstd,subvol=@root 0 0\n"
          f"UUID={root_uuid} /home btrfs defaults,noatime,compress=zstd,subvol=@home 0 0\n"
          f"UUID={root_uuid} /var/log btrfs defaults,noatime,compress=zstd,subvol=@log 0 0\n"
          f"UUID={root_uuid} /.snapshots btrfs defaults,noatime,compress=zstd,subvol=@snapshots 0 0\n"
          f"UUID={esp_uuid} /boot vfat defaults,umask=0077 0 2\n")
    write(root, "etc/mkinitcpio.conf", "MODULES=(btrfs)\nBINARIES=()\nFILES=()\n"
          "HOOKS=(base systemd autodetect microcode modconf kms keyboard sd-vconsole block filesystems fsck)\n")
    kernels = list((root / "usr/lib/modules").glob("*/vmlinuz"))
    if len(kernels) != 1:
        raise ValueError("exactly one packaged Linux kernel is required")
    shutil.copyfile(kernels[0], root / "boot/vmlinuz-linux")
    write(root, "etc/mkinitcpio.d/linux.preset", 'ALL_config="/etc/mkinitcpio.conf"\nALL_kver="/boot/vmlinuz-linux"\n'
          "PRESETS=('default' 'fallback')\ndefault_image=\"/boot/initramfs-linux.img\"\n"
          'fallback_image="/boot/initramfs-linux-fallback.img"\nfallback_options="-S autodetect"\n')
    run("arch-chroot", str(root), "mkinitcpio", "-P")
    run("bootctl", f"--root={root}", "--esp-path=/boot", "--install-source=image", "--variables=no", "install")
    write(root, "boot/loader/loader.conf", "default phios.conf\ntimeout 5\neditor no\n")
    write(root, "boot/loader/entries/phios.conf", "title PhiOS Linux development installation\n"
          "linux /vmlinuz-linux\ninitrd /initramfs-linux.img\n"
          f"options root=UUID={root_uuid} rw rootflags=subvol=@root\n")
    release = json.loads((root / "usr/share/phios/linux-release.json").read_text())
    write(root, "etc/os-release", 'NAME="PhiOS Linux Preview"\nID=phios\nID_LIKE=arch\n'
          f'PRETTY_NAME="PhiOS Linux {release["os_version"]} Experimental Installation"\nVERSION_ID="{release["os_version"]}"\n')
    # The live file:// package repository lives only in the isolated builder.
    write(root, "etc/pacman.conf", "[options]\nArchitecture = x86_64\nCheckSpace\n"
          "SigLevel = Required DatabaseOptional\nLocalFileSigLevel = Required\n"
          "[core]\nInclude = /etc/pacman.d/mirrorlist\n[extra]\nInclude = /etc/pacman.d/mirrorlist\n")
    write(root, "etc/pacman.d/mirrorlist", f'Server = https://archive.archlinux.org/repos/{release["arch_snapshot"]}/$repo/os/$arch\n')


def apply(plan: dict[str, Any], password: str) -> dict[str, Any]:
    identity = plan["target"]
    device = identity["path"]
    if inventory(device) != identity:
        raise ValueError("disk changed after review; no disk writes performed")
    verify_zeroed(device, identity["size_bytes"])
    workspace = Path(tempfile.mkdtemp(prefix="phios-install-", dir="/run"))
    receipt = {"schema_version": "phios.blank-disk-install.v1", "plan": plan,
               "stage": "prepared", "disk_modified": False, "installed": False, "release_ready": False}
    mounts: list[Path] = []
    lock = os.open(device, os.O_RDONLY | os.O_NOFOLLOW)
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        if inventory(device) != identity:
            raise ValueError("disk changed before partitioning")
        source = workspace / "source"
        root = workspace / "target"
        top = workspace / "top"
        for path in [source, root, top]:
            path.mkdir(mode=0o700)
        run("mount", "-o", "loop,ro,nodev,nosuid", str(SOURCE), str(source))
        mounts.append(source)
        if (source / "usr/share/phios/source-commit").read_text().strip() != plan["source_commit"]:
            raise ValueError("immutable live source differs from reviewed package source")
        receipt.update(stage="partitioning", disk_modified=True)
        write(workspace, "receipt.json", json.dumps(receipt, indent=2) + "\n", mode=0o600)
        run("sgdisk", "--clear", "--new=1:0:+1G", "--typecode=1:ef00", "--change-name=1:PHIOS_ESP",
            "--new=2:0:0", "--typecode=2:8300", "--change-name=2:PHIOS_ROOT", device)
        # udev observes the block-device lock. Release it before waiting for
        # partition events; otherwise settle can wait on our own open lock.
        os.close(lock)
        lock = -1
        run("udevadm", "settle")
        suffix = "p" if device[-1].isdigit() else ""
        esp, system = Path(device + suffix + "1"), Path(device + suffix + "2")
        for _ in range(30):
            if esp.exists() and system.exists():
                break
            time.sleep(0.1)
        for partition in [esp, system]:
            info = partition.stat()
            link = (Path("/sys/dev/block") / f"{os.major(info.st_rdev)}:{os.minor(info.st_rdev)}").resolve()
            if not stat.S_ISBLK(info.st_mode) or link.parent.name != Path(device).name:
                raise ValueError("new partition does not belong to confirmed disk")
        run("mkfs.fat", "-F", "32", "-n", "PHIOS_ESP", str(esp))
        run("mkfs.btrfs", "-L", "PHIOS_ROOT", str(system))
        run("mount", str(system), str(top))
        mounts.append(top)
        for subvolume in plan["layout"]["subvolumes"]:
            run("btrfs", "subvolume", "create", str(top / subvolume))
        run("mount", "-o", "subvol=@root,compress=zstd", str(system), str(root))
        mounts.append(root)
        for subvolume, relative in [("@home", "home"), ("@log", "var/log"), ("@snapshots", ".snapshots")]:
            path = root / relative
            path.mkdir(parents=True)
            run("mount", "-o", f"subvol={subvolume},compress=zstd", str(system), str(path))
            mounts.append(path)
        (root / "boot").mkdir()
        run("mount", str(esp), str(root / "boot"))
        mounts.append(root / "boot")
        receipt["stage"] = "copying immutable source"
        run("rsync", "-aHAX", "--numeric-ids", "--one-file-system", "--exclude=/home/***",
            "--exclude=/boot/***", "--exclude=/var/log/***", str(source) + "/", str(root) + "/")
        root_uuid = run("blkid", "-s", "UUID", "-o", "value", str(system)).strip()
        esp_uuid = run("blkid", "-s", "UUID", "-o", "value", str(esp)).strip()
        if not re.fullmatch(r"[0-9a-f-]{36}", root_uuid) or not re.fullmatch(r"[0-9A-F]{4}-[0-9A-F]{4}", esp_uuid):
            raise ValueError("invalid new filesystem UUID")
        receipt["stage"] = "configuring installed system"
        configure(root, plan["username"], password, plan["hostname"], root_uuid, esp_uuid)
        receipt.update(stage="installed; no-ISO boot unqualified", installed=True,
                       root_uuid=root_uuid, esp_uuid=esp_uuid)
        write(root, "var/lib/phios/install-receipt.json", json.dumps(receipt, indent=2) + "\n", mode=0o600)
        os.sync()
        return receipt
    except BaseException as exc:
        receipt["error"] = str(exc)
        raise
    finally:
        failures = []
        for path in reversed(mounts):
            try:
                run("umount", str(path))
            except (ValueError, RuntimeError) as exc:
                failures.append(str(exc))
        if lock >= 0:
            os.close(lock)
        receipt["cleanup_errors"] = failures
        write(workspace, "receipt.json", json.dumps(receipt, indent=2) + "\n", mode=0o600)
        print(f"Private installation evidence: {workspace}/receipt.json", flush=True)
        if failures:
            raise RuntimeError("installation mounts remain active; preserve evidence and do not reboot")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--disk", required=True)
    parser.add_argument("--username", required=True)
    parser.add_argument("--hostname", default="phios")
    parser.add_argument("--plan", action="store_true", help="Read-only inventory; never installs")
    args = parser.parse_args()
    try:
        if os.geteuid() != 0:
            raise ValueError("run the root-owned installer with sudo from the live preview")
        validate_account(args.username, args.hostname)
        if not SOURCE.is_file() or not Path("/sys/firmware/efi").is_dir():
            raise ValueError("the configured PhiOS x64 UEFI live image is required")
        for name in REQUIRED:
            if shutil.which(name, path=ENV["PATH"]) is None:
                raise ValueError(f"required installer program unavailable: {name}")
        source = IDENTITY.read_text().strip()
        if re.fullmatch(r"[0-9a-f]{40}", source) is None:
            raise ValueError("exact installed source identity is required")
        identity = inventory(args.disk)
        plan, phrase = confirmation(identity, source, args.username, args.hostname)
        print(json.dumps(plan, indent=2), flush=True)
        if args.plan:
            return 0
        if not sys.stdin.isatty() or not sys.stdout.isatty():
            raise ValueError("installation requires an interactive terminal; no bypass is provided")
        print("Checking every byte of the selected disk for zeroed contents...", flush=True)
        verify_zeroed(args.disk, identity["size_bytes"])
        password = getpass.getpass("New account password (12 or more characters): ")
        if len(password) < 12 or ":" in password or "\n" in password or "\r" in password:
            raise ValueError("password must be at least 12 characters without colon or line breaks")
        if getpass.getpass("Repeat new account password: ") != password:
            raise ValueError("passwords do not match; no disk writes performed")
        print("This creates an unencrypted experimental installation. All selected disk contents will be replaced.", flush=True)
        print("Type the exact confirmation below, or press Ctrl-C to cancel:\n" + phrase, flush=True)
        if input("> ") != phrase:
            raise ValueError("confirmation did not match; no disk writes performed")
        result = apply(plan, password)
        print(json.dumps(result, indent=2), flush=True)
        print("Remove live media and test the installed boot. Keep this preview available for recovery.")
        return 0
    except (KeyboardInterrupt, EOFError):
        print("Installation cancelled. Preserve any installation evidence if disk writes had begun.")
        return 130
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f"Installation held: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
