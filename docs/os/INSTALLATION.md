# Experimental blank-disk installation

The candidate manual installer is `phios-install`, packaged behind a root-owned
isolated Python launcher. The disposable installed-image gate passed in
[run 36798467774](https://github.com/MichaelWave369/PhiOS/actions/runs/36798467774).
This remains an experimental development installation; a hardware-supported beta additionally
requires update/recovery and the declared hardware matrix. Keep the verified
live media available. An installed filesystem alone is not a completed OS
release.

## Scope

Supported candidate shape: x86_64, x64 UEFI with Secure Boot disabled, one
canonical disk with a stable serial/WWN, at least 16 GiB, no partitions,
mounts, swap, holders, slaves or recognized signatures. Before installation
the tool reads every byte and requires zeroed contents, including unsigned data
that has no filesystem signature. This can take time on large hardware.
Existing data is refused. There is no automatic disk selection, erase-existing
option, unattended mode, HTTP installer or confirmation bypass.

The layout is a 1 GiB FAT32 ESP and a Btrfs filesystem with separate `@root`,
`@home`, `@log` and `@snapshots` subvolumes. Installation is unencrypted and has
no swap/hibernation setup. Btrfs subvolumes prepare a recovery layout; they do
not by themselves implement OS rollback or protect against drive failure.
BIOS, dual boot, Secure Boot, disk encryption, RAID, existing partitions and
storage migration are held.

## Review and install

Boot the configured PhiOS live preview. Open Foot and inspect the real disks:

```sh
lsblk --bytes --paths --output NAME,TYPE,SIZE,MODEL,SERIAL,WWN,MOUNTPOINTS
```

Replace both placeholders below with a reviewed canonical path and a new
lowercase account name. `--plan` performs read-only inventory and reports the
source, disk, account, hostname, unencrypted layout and held release status:

```sh
sudo phios-install --disk /dev/DEVICE --username YOURNAME --plan
sudo phios-install --disk /dev/DEVICE --username YOURNAME
```

The public volatile `phios` account can invoke this one interactive installer
through sudo; it receives no general passwordless root shell. Root/TTY checks
do not prove a human or isolate a malicious same-user process. The supported
custody boundary is the operator-controlled live boot and reviewed device.

The tool validates the target, checks zeroed contents, requests a fresh password
(at least 12 characters), and displays a confirmation containing the exact
device path and SHA-256 of the complete reviewed plan. Type that full phrase
or cancel. A wrong phrase, EOF or cancellation before the first disk command
does not change the disk. The disk inventory and zeroed contents are rechecked
after confirmation; stale identity is held. Passwords are passed through stdin
only, never argv, logs or receipts.

The first destructive command creates GPT on the selected empty disk. The tool
copies the immutable live squashfs, never the current live overlay or another
user's state. It creates a fresh account and private state, locks root, removes
live credentials/autologin/test fixtures, installs a normal greetd/PAM login,
generates an installed initramfs and installs systemd-boot's fallback loader.
It leaves firmware boot variables/order unchanged. Select the installed disk
in firmware if needed. The live password is never installed as an account
credential.

Installed package repositories remain on the signed pinned Arch snapshot.
The transient unsigned local build repository is removed. A supported PhiOS
package update channel and signed OS publication are separate pending gates;
do not change mirrors or perform partial package upgrades to imply a supported
update policy.

## Failure and first boot

The tool preserves private stage/error evidence under `/run/phios-install-*`.
After disk writes begin, failure does not undo a partial installation or make
the disk blank again. Preserve the evidence off volatile media, inspect the
reported stage and mounts, and recover deliberately. A cleanup failure reports
remaining mounts and returns nonzero; do not reboot while cleanup is held.
There is no implicit retry or automatic wiping of failed targets.

Successful installation writes `/var/lib/phios/install-receipt.json` with exact
source, target identity and filesystem UUIDs. `release_ready` remains false and
installed boot remains unqualified until observed. Remove the ISO, boot the
disk, authenticate the new account and verify Wayfire/PhiShell, private memory
state, package observations and services. Optional memory configuration stays
disabled unless the operator explicitly enables it. See STATE_RECOVERY.md for
data-only migration and backup; authority is never imported from the live
session.

## Disposable qualification

The CI lane creates a new 32 GiB qcow2 image with serial `PHIOS_CI_BLANK`; its
driver accepts no existing image or host device. Networking and shared folders
are absent. A root qualification fixture exists only in the CI live profile
and refuses any other target. It drives the same production CLI through a PTY,
first cancels and checks the disk, then types the exact reviewed confirmation.

The fixture seeds a zero-authority canonical memory record and verified backup
as the new user, confirms removal of live credentials/test fixtures/autologin,
and injects a serial console solely into the disposable installed test target.
The host then boots without the ISO, authenticates through normal password/PAM
login, types credentials at the real greetd greeter, observes the non-root
desktop/services, restores data into a fresh root, and checks an acknowledged
write again after an abrupt virtual restart. Serial-console injection is
recorded in the receipt; no installed automatic login is introduced. Exact
ISO/source hashes, serial logs, boot IDs and screenshots accompany success or
failure. A VM restart is not hardware power-loss qualification.

The qualified source is `0253b6e0fb27251fe2da37b6d8c1e31245a64290`; ISO SHA-256
is `8599bbc7ff2ed35432bae23692464d4d5afa9ffdfc787699a7be88f2cfc62f5c`.
The exact receipt and evidence identities are in
`docs/os/evidence/installation-0253b6e0.json`. CI credentials
are public test-only values; normal local profiles and production installs
contain neither the fixture nor those credentials.

References: [bootctl](https://man.archlinux.org/man/bootctl.1.en),
[lsblk](https://man.archlinux.org/man/lsblk.8.en),
[wipefs](https://man.archlinux.org/man/wipefs.8.en),
[Btrfs subvolumes](https://btrfs.readthedocs.io/en/latest/btrfs-subvolume.html).
