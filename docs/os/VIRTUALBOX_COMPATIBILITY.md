# VirtualBox live compatibility observation

On 2026-10-01 Mikey reported a local live test on Windows 11 Home using Oracle
VirtualBox. This is owner-supplied compatibility evidence for the existing
qualified normal candidate, with the failed configurations preserved below.
It does not qualify physical Skytech/RTX 5070 hardware, installation, audio,
network connectivity, suspend, a signed transition or publication.

| Tested identity | Value |
| --- | --- |
| Source PR | [281](https://github.com/MichaelWave369/PhiOS/pull/281) |
| Reviewed head | `3d282bdd6466052def8e632245f312863040cafc` |
| Qualified prospective source | `1c16c4732442d69d2c7b5763212f1977860a15ae` |
| Normal ISO SHA-256 | `376fd601f66b13dccd6a08644a7b807129f315882d355fd376d0934a80ae29aa` |
| Existing qualification | [36832501182](https://github.com/MichaelWave369/PhiOS/actions/runs/36832501182) |
| Field receipt | [virtualbox-field-1c16c473.json](evidence/virtualbox-field-1c16c473.json) |

The field report supplied this identity; this review did not independently hash
the owner's mounted ISO or acquire the raw Wayfire/service logs. The attached
desktop screenshot was inspected: PhiShell v0.16.0 and a visible pointer are
present. The receipt retains the screenshot digest, without copying the image
into the public repository. Interaction and the staged failures/successes are
owner observations. The exact VirtualBox version was not supplied.

## Configuration and outcomes

Arch Linux (64-bit) guest, EFI enabled, Secure Boot off, 8192 MB RAM, four vCPUs,
64 GB virtual disk, VMSVGA, 128 MB video RAM, NAT and no shared folders. The exact
normal ISO above was mounted. No installation was reported.

| Stage | Configuration / observation | Result |
| --- | --- | --- |
| Initial live boot | EFI, live environment, greetd/tuigreet, public `phios` / `phios` PAM and tty login | PASS |
| Initial renderer | VMSVGA, 3D acceleration off; graphical session immediately exits | FAIL |
| Renderer retry | Power off VM, enable 3D acceleration, retain VMSVGA/128 MB | PASS: PhiShell, Reality Ledger, launcher, windows and Waybar visible |
| Initial pointer | Hover/right-click works after renderer retry, pointer invisible | FAIL |
| Cursor workaround | Export `WLR_NO_HARDWARE_CURSORS=1` before launching `phios-session` from tty2 | PASS: visible functional cursor and rendering; desktop initially blank |
| Existing services | Browser and Waybar active; Chromium uses `--ozone-platform=wayland --app=http://127.0.0.1:3969/`; Waybar sees display | Active services alone did not establish a rendered desktop |
| Session rebinding | Stop then start `phios-session.target` from the new graphical session | PASS: full PhiShell/Waybar desktop, cursor and normal interaction |

Reported initial renderer messages, retained verbatim:

```text
VMware: No 3D enabled
MESA-EGL warning: egl: failed to create dri2 screen
EGL_NOT_INITIALIZED
Failed to initialize EGL context
Could not initialize renderer
Failed to create renderer
```

The pointer behavior is consistent with a hardware-cursor issue. Services left
running from the previous session are consistent with the blank desktop after
launching a new compositor: importing environment variables does not change an
already-running process. These are bounded diagnoses, not additional raw-log
observations or evidence for every VirtualBox version.

## Reproduced manual recipe on the original candidate

Power off the VM and select VMSVGA, 128 MB VRAM and **3D acceleration on**.
After ordinary live tty login, launch:

```sh
export WLR_NO_HARDWARE_CURSORS=1
phios-session
```

If earlier user services remain bound to the old session, open the ordinary
Linux terminal in the new graphical session with Super+Alt+Enter and run:

```sh
systemctl --user stop phios-session.target
systemctl --user start phios-session.target
```

The live overlay is volatile. This manual recipe documents the owner's result;
it does not claim the original ISO contains an automatic compatibility fix.

## Narrow candidate correction and verification

The follow-up session wrapper sources a packaged compatibility helper before
starting Wayfire. The helper requires **both** successful
`systemd-detect-virt --vm` identification as `oracle` and a sysfs PCI display
device with vendor/device `15ad:0405` (VMSVGA). Only this combination sets
`WLR_NO_HARDWARE_CURSORS=1`. VMware shares the PCI identity, so the PCI device
alone is insufficient. Missing/failed detection or another device leaves the
cursor environment unchanged. No Guest Additions, new kernel/driver, global
cursor setting or real-hardware renderer behavior is added. Host-side 3D
acceleration remains an operator VM setting.

The Wayfire autostart hook refuses missing display/runtime variables or a
non-socket display path. It imports the compositor's Wayland/runtime/desktop
environment into the user systemd and D-Bus activation environments, clears an
obsolete Xwayland DISPLAY when none is supplied, then stops/starts the existing
session target. Existing PartOf dependencies rebind browser, panel and other
session services. Session cleanup and non-root startup remain in place.

Focused tests execute the shell helper with captured PCI identities and check
VirtualBox selection, VMware/KVM/real-hardware exclusion, incomplete detection,
operator environment preservation, socket gating, relative/absolute
display paths, import-before-restart ordering and failure propagation. The
normal-image QEMU gate additionally contaminates the manager's display variables
while the real browser and panel are active, invokes the packaged ready hook,
and requires replacement process IDs with the actual compositor socket and
cleared stale DISPLAY on both live boots. This verifies rebinding under QEMU;
it does not emulate a Windows VirtualBox 3D driver or prove the new automatic
cursor branch in VirtualBox.

Changed source and ISO bytes require their own complete qualification and a
fresh local VirtualBox test of automatic startup without manual exports/target
restart. Keep the original candidate hashes/receipts intact. Do not merge, tag,
sign, publish or infer physical support from this observation.

Detection references: [systemd virtualization identifiers](https://github.com/systemd/systemd/blob/main/src/basic/virt.c),
[Oracle VMSVGA PCI definitions](https://github.com/VirtualBox/virtualbox/blob/main/src/VBox/Devices/Graphics/DevVGA-SVGA.h),
and [systemd PartOf lifecycle semantics](https://www.freedesktop.org/software/systemd/man/systemd.unit.html).
