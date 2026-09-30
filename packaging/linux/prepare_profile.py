"""Assemble an isolated Archiso 91 profile; never modify the upstream template."""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path


def prepare(upstream: Path, destination: Path, repo: Path, package_repo: Path, *, smoke: bool) -> None:
    release = json.loads((repo / "packaging/linux/release.json").read_text())
    required = ["profiledef.sh", "efiboot/loader/entries/01-archiso-linux.conf",
                "airootfs/etc/mkinitcpio.conf.d/archiso.conf"]
    for name in required:
        if not (upstream / name).is_file():
            raise ValueError(f"complete Archiso releng template required: {name}")
    if destination.exists():
        raise ValueError("profile destination must be new; refusing to overwrite an existing build")
    shutil.copytree(upstream, destination, symlinks=True)
    # Discard root autologin, ssh, cloud-init and unrelated releng customization.
    shutil.rmtree(destination / "airootfs")
    root = destination / "airootfs"

    def write(name: str, content: str) -> None:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)

    write("etc/mkinitcpio.conf.d/archiso.conf", (upstream / required[2]).read_text())
    snapshot = release["arch_snapshot"]
    pacman = f"""[options]
Architecture = x86_64
SigLevel = Required DatabaseOptional
LocalFileSigLevel = Optional
CheckSpace
ParallelDownloads = 5
[core]
Server = https://archive.archlinux.org/repos/{snapshot}/$repo/os/$arch
[extra]
Server = https://archive.archlinux.org/repos/{snapshot}/$repo/os/$arch
[phios-local]
SigLevel = Optional TrustAll
Server = file://{package_repo.resolve()}
"""
    (destination / "pacman.conf").write_text(pacman)
    shutil.copyfile(repo / "packaging/linux/packages.x86_64", destination / "packages.x86_64")
    version = release["os_version"]
    (destination / "profiledef.sh").write_text(f"""#!/usr/bin/env bash
# Built on the signed Archiso {release['archiso_version']} releng template.
iso_name="phios-linux"
iso_label="PHIOS_PREVIEW"
iso_publisher="PHI369 Labs / Parallax"
iso_application="PhiOS Linux development preview"
iso_version="{version}"
install_dir="arch"
arch="x86_64"
buildmodes=('iso')
bootmodes=('uefi.systemd-boot')
pacman_conf="pacman.conf"
airootfs_image_type="squashfs"
airootfs_image_tool_options=('-comp' 'zstd' '-b' '1M')
file_permissions=(
  ["/usr/local/bin/phios-live-setup"]="0:0:755"
  ["/usr/local/bin/phios-live-smoke"]="0:0:755"
)
""" if smoke else f"""#!/usr/bin/env bash
iso_name="phios-linux"
iso_label="PHIOS_PREVIEW"
iso_publisher="PHI369 Labs / Parallax"
iso_application="PhiOS Linux development preview"
iso_version="{version}"
install_dir="arch"
arch="x86_64"
buildmodes=('iso')
bootmodes=('uefi.systemd-boot')
pacman_conf="pacman.conf"
airootfs_image_type="squashfs"
airootfs_image_tool_options=('-comp' 'zstd' '-b' '1M')
file_permissions=(["/usr/local/bin/phios-live-setup"]="0:0:755")
""")
    entries = destination / "efiboot/loader/entries"
    for path in entries.iterdir():
        if path.name != "01-archiso-linux.conf":
            path.unlink()
    entry = entries / "01-archiso-linux.conf"
    entry.write_text(entry.read_text().replace("Arch Linux", "PhiOS development preview") +
                     "\n# Console logs are preserved by the qualification harness.\n")
    # Keep the upstream identifiers/placeholders needed by mkarchiso.
    lines = entry.read_text().splitlines()
    entry.write_text("\n".join(line + " console=tty0 console=ttyS0,115200" if line.startswith("options ")
                               else line for line in lines) + "\n")
    (destination / "efiboot/loader/loader.conf").write_text("default 01-archiso-linux.conf\ntimeout 1\n")
    write("etc/hostname", "phios-live\n")
    write("etc/locale.conf", "LANG=C.UTF-8\n")
    write("etc/vconsole.conf", "KEYMAP=us\n")
    (root / "etc/localtime").symlink_to("/usr/share/zoneinfo/UTC")
    # Releng masks this interactive first-boot wizard. Keep that behavior for
    # a configured volatile live session rather than blocking graphical.target.
    firstboot = root / "etc/systemd/system/systemd-firstboot.service"
    firstboot.parent.mkdir(parents=True, exist_ok=True)
    firstboot.symlink_to("/dev/null")
    write("etc/sysusers.d/phios-live.conf", 'u phios 1000 "PhiOS Live" /home/phios /bin/bash\n'
          'u phios-agent 1001 "Reserved isolated agent" /var/lib/phios-agent /usr/bin/nologin\n'
          'u phios-greeter - "PhiOS Greeter" /var/lib/phios-greeter /usr/bin/nologin\n')
    write("etc/tmpfiles.d/phios-live.conf", "d /home/phios 0700 phios phios -\n"
          "d /home/phios/.local 0700 phios phios -\n"
          "d /home/phios/.local/state 0700 phios phios -\n"
          "d /home/phios/.local/state/phios 0700 phios phios -\n"
          "d /var/lib/phios-agent 0700 phios-agent phios-agent -\n")
    write("etc/greetd/config.toml", '[terminal]\nvt = 1\n[default_session]\n'
          'command = "tuigreet --cmd phios-session"\nuser = "phios-greeter"\n'
          '[initial_session]\ncommand = "phios-session"\nuser = "phios"\n')
    write("etc/systemd/system/greetd.service.d/phios.conf", "[Unit]\n"
          "Requires=phios-live-setup.service\nAfter=phios-live-setup.service\n")
    write("etc/systemd/system/phios-live-setup.service", "[Unit]\n"
          "Description=Configure the volatile PhiOS live session\nAfter=systemd-tmpfiles-setup.service\n"
          "[Service]\nType=oneshot\nExecStart=/usr/local/bin/phios-live-setup\nRemainAfterExit=yes\n")
    write("usr/local/bin/phios-live-setup", "#!/usr/bin/env bash\nset -euo pipefail\n"
          "systemd-sysusers\nsystemd-tmpfiles --create /etc/tmpfiles.d/phios-live.conf\n"
          "printf 'phios:phios\\n' | chpasswd\nusermod --lock root\n"
          "install -m644 /usr/share/phios/preview-os-release /etc/os-release\n")
    write("usr/share/phios/preview-os-release", f'NAME="PhiOS Linux Preview"\nID=phios\nID_LIKE=arch\n'
          f'PRETTY_NAME="PhiOS Linux {version} Development Preview"\nVERSION_ID="{version}"\n')
    write("etc/systemd/network/20-wired.network", "[Match]\nName=en* eth*\n[Network]\nDHCP=yes\n")
    wants = root / "etc/systemd/system/multi-user.target.wants"
    wants.mkdir(parents=True)
    for name in ["systemd-networkd.service", "systemd-resolved.service", "iwd.service"]:
        (wants / name).symlink_to(f"/usr/lib/systemd/system/{name}")
    graphical = root / "etc/systemd/system/graphical.target.wants"
    graphical.mkdir(parents=True)
    (graphical / "greetd.service").symlink_to("/usr/lib/systemd/system/greetd.service")
    (root / "etc/systemd/system/default.target").symlink_to("/usr/lib/systemd/system/graphical.target")
    (root / "etc/resolv.conf").symlink_to("/run/systemd/resolve/stub-resolv.conf")
    if smoke:
        # The qualification fixture owns this console; an interactive getty
        # must not reset/consume its serial evidence.
        (root / "etc/systemd/system/serial-getty@ttyS0.service").symlink_to("/dev/null")
        write("usr/local/bin/phios-live-smoke", (repo / "packaging/linux/tests/live-smoke.sh").read_text())
        write("etc/systemd/system/phios-live-smoke.service", "[Unit]\nDescription=CI live-image qualification fixture\n"
              "After=greetd.service\n[Service]\nType=oneshot\nExecStart=/usr/local/bin/phios-live-smoke\n"
              "TimeoutStartSec=480\nStandardOutput=tty\nStandardError=tty\nTTYPath=/dev/ttyS0\n")
        (wants / "phios-live-smoke.service").symlink_to("/etc/systemd/system/phios-live-smoke.service")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upstream", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--package-repo", type=Path, required=True)
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()
    prepare(args.upstream, args.destination, args.repo, args.package_repo, smoke=args.smoke)
