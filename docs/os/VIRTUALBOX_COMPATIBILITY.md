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

A later owner cold boot showed `vmwgfx` warning about an unsupported hypervisor
and the separate unavailable TDX host feature before boot continued. The field
receipt preserves those screenshot messages and its digest. The messages alone
do not establish a fatal boot failure or persistence of the manual cursor
override after a power cycle. Keep this observation separate from a new-ISO
automatic startup pass.

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
and requires replacement running browser/panel process IDs after the user
manager imports the connected compositor's display environment and clears stale
DISPLAY on both live boots. This verifies rebinding under QEMU;
it does not emulate a Windows VirtualBox 3D driver or prove the new automatic
cursor branch in VirtualBox.

Each changed source and ISO requires its own complete qualification and a
fresh local VirtualBox test of automatic startup without manual exports/target
restart. The follow-up #283 result is recorded below; it does not change the
original candidate hashes/receipts. Do not merge, tag, sign, publish or infer
physical support from this observation.

The first follow-up normal-image attempt rendered PhiShell/Waybar but failed
the new probe while it tried to obtain a service process's display environment
from `/proc/PID/environ`; the initial timeout omitted the failing PID/environment
predicate. Its install/recovery phase was skipped. The revised probe
uses the user manager's explicit `show-environment` state, validates only its
display keys, connects to the actual compositor socket and requires individually
active replacement Chromium/Waybar processes. The failed source/ISO, serial
exception, screenshot and independently checked compact-archive hashes remain
in [virtualbox-compatibility-attempts.json](evidence/virtualbox-compatibility-attempts.json).
The failed gate is not replaced by its screenshot or a separate QA result.

## Automatic startup field retest on #283

On 2026-10-01 the owner supplied `PhiOS-PR283-test-report.md`, produced by a
local Windows desktop Codex GPT-5.6 test. Its 3,096 uploaded bytes were hashed by
this review: `f242dc804437395a576e740d36c6201c2eb75d19e3fa341d1f9154791443b7fc`.
The normalized receipt is
[virtualbox-field-9510024d.json](evidence/virtualbox-field-9510024d.json).
The observations below are **reported results**: this review did not operate
the VM, independently hash its local ISO, or acquire screenshots, raw guest logs
or command transcripts. The exact VirtualBox version remains unspecified.

| Tested identity | Value |
| --- | --- |
| Reviewed code PR/head | [283](https://github.com/MichaelWave369/PhiOS/pull/283), `d1a4a2bc515907d1011b6aa1c2a203acc200cad8` |
| Qualified prospective source / identical tree | `9510024d06d822729bd98579fefb6644ca0498c0` / `0dd0e998671105174b4bf2918a00ca06ac68f44a` |
| Normal ISO expected and reported observed SHA-256 | `33bfb34251d7f65abe7f8a9d600c21794d051640a305d50c1bca9b21364c2c68` |
| Exact-source qualification | [36916494462](https://github.com/MichaelWave369/PhiOS/actions/runs/36916494462), attempt 1, all nine jobs passed |
| Normal ISO/payloads | [11191052839](https://github.com/MichaelWave369/PhiOS/actions/runs/36916494462/artifacts/11191052839), expires 2026-10-08 |

The reported before-boot ISO hash matches the previously independently reviewed
normal-image provenance for the qualified source above. The source identity is
bound through that provenance/run; the field report itself supplies the ISO
digest and PR, not a Git commit. An older extracted ISO `376fd601...` was found
but was not attached or booted in this test. Its original field evidence remains
separate and unchanged.

The new `PhiOS-PR283` VM was separate from the existing `PhiOS` VM: Arch Linux
(64-bit), EFI, no enrolled Secure Boot platform key, 8192 MB RAM, four vCPUs,
new 64 GB VDI, VMSVGA/128 MB with 3D acceleration on, NAT, no shared folders,
and disabled clipboard/drag-and-drop. Windows 11 Home is the owner's preceding
host context; the new report does not independently establish the edition/build.

| Observation | Reported result |
| --- | --- |
| Initial live boot and Wayland session | PASS |
| Graphical greeter and `phios` / `phios` login | PASS; greeter tested after terminating the current session and returning to tty1 |
| PhiShell / Waybar | PASS; interactive shell and populated panel visible |
| Cursor visibility and movement | PASS; guest-rendered cursor moved by VirtualBox absolute pointer injection, including after cold boot |
| Automatic cursor/session startup | PASS; Wayfire environment already contained `WLR_NO_HARDWARE_CURSORS=1`, with no manual export or target restart |
| System-manager failed units | None reported by `systemctl --failed`; user-manager failed-unit output not supplied |
| Full shutdown and cold power-on | PASS via VM ACPI power button; `VMState=poweroff` observed before a cold start returned to PhiShell, Waybar and working cursor |

This establishes reported compatibility evidence for the automatic startup case
on these exact live ISO bytes. It does not qualify VirtualBox installation,
network connectivity, audio, suspend, physical hardware, another VirtualBox
version or every supported desktop operation.

### Preserved observations and the remaining lock check

The report records three additional observations without converting them into
passes:

1. **Super+L produced a blank screen rather than a visible lock UI.** The test
   then terminated the session and verified a fresh greeter login. It did not
   test wrong-password refusal or PAM unlock from the locked session. The
   packaged `phios-lock` requests a solid dark `111318` background and does not
   request an idle-visible indicator; upstream swaylock separately provides
   `--indicator-idle-visible`. This is consistent with a blank idle lock screen,
   but is an inference, not evidence that locking succeeded in this VM. Keep the
   observation unresolved until the actual lock/refusal/unlock sequence passes.
2. **`sudo poweroff` was refused by the live account.** ACPI shutdown/cold restart
   succeeded. The live user retains its narrow sudo authority; no permission
   was expanded. The documented guest `systemctl poweroff`/logind/PolicyKit path
   was not tested by this command.
3. **Explicit Secure Boot disable reported no enrolled platform key.** The VM
   recovered to its graphical desktop. Effective Secure Boot off is reported;
   Secure Boot support or key enrollment is not established.

For the bounded remaining VirtualBox lock check, retain this exact ISO and VM
configuration. Invoke Super+L, observe whether typing produces an indicator,
enter an incorrect disposable password and verify the desktop stays locked,
then enter the public live password `phios` followed by Enter. Verify the same
session returns with PhiShell, Waybar and a functional cursor. Preserve the
appearance, refusal and unlock results; terminating the session or restarting
the compositor is not a successful unlock. Record the exact VirtualBox version
and retain relevant screenshots/logs separately. This check requires no new
runtime, sudo policy or global cursor changes.

## Launcher field retest on #286

On 2026-10-01 the owner supplied `PhiOS-PR286-test-report.md` from local Windows
Codex GPT-5.6 and two PNG screenshots. This review hashed all three supplied
files, inspected the images and checked the reported used ISO against retained
normal provenance, the exact source tree and the successful original run. It
did not operate the VM or independently hash the Windows ISO. Interaction,
shutdown and service results remain the local tester's reported observations.
The normalized receipt is
[virtualbox-field-0f17bac1.json](evidence/virtualbox-field-0f17bac1.json).

| Identity | Value |
| --- | --- |
| Reviewed code PR/head | [286](https://github.com/MichaelWave369/PhiOS/pull/286), `ff05e82d80b5cfb6c1699c57e3d6e2aff0daaaf8` |
| Qualified prospective source | `0f17bac1ed22bb21374c5471bef32e5e099f5845` |
| Identical source tree | `5a64718e021156c068771da1ebb0b27abf12cdc5` |
| Normal ISO SHA-256 | `8635a5f1277ca01ef7174b6e3b325e3cf9e972572070eb84d7395b9cec3dcd08` |
| Original qualification | [36939975061](https://github.com/MichaelWave369/PhiOS/actions/runs/36939975061), attempt 1, all nine jobs successful |
| Report SHA-256 / bytes | `8e8f092e38bb590bb062de3dbc09ddeb5201f03ffb17e982cb919a5f9d6525da` / 3,704 |
| Supplied hypervisor version | Oracle VirtualBox `7.2.20r175154` |

The local tester created a separate `PhiOS-PR286` VM and preserved `PhiOS` and
`PhiOS-PR283`: Arch Linux 64-bit, EFI, 8192 MB RAM, four CPUs, new 64 GB VDI,
VMSVGA/128 MB/3D enabled, NAT, no shared folders, and clipboard/drag-and-drop
disabled. This report does not independently establish host Windows build or
Secure Boot state. No external application runtime was installed.

| Check | Reported result |
| --- | --- |
| ISO integrity before boot | Full expected digest matched in extraction `36939975061-attempt-1` |
| Graphical greeter / public live-account login | PASS before cold boot |
| Automatic desktop, PhiShell, Waybar, visible movable cursor | PASS before and after cold boot |
| Apps, Home, Start, search | PASS before and after cold boot; search exercised System Inspector, then Builder |
| System Inspector, Reality Ledger, ΦDream, Builder | Open/minimize/reopen/close PASS for each before and after cold boot |
| Integration labels | Browsallax `Not bundled`, PhiVessel `Advisory only`, BrainC `Client only` |
| Chromium / Foot shortcuts | PASS before and after cold boot; Chromium needed the Wofi search-text workaround below |
| Complete shutdown / cold start | ACPI reached `VMState=poweroff`, then returned to automatic graphical desktop |
| Failed units after cold boot | `systemctl --failed` reported zero; no separate user-manager output supplied |

`25-cold-apps-launcher.png` shows the Apps library, integration labels, a visible
pointer and Waybar. `35-final-phishell.png` shows PhiShell, Research Field and
Reality Ledger; the ledger explicitly reports canonical history **UNAVAILABLE**.
PhiVessel says chat is not connected. These static images support the visible
UI states, not a click transcript, backend-health result or model-inference test.
Their complete hashes, sizes and dimensions are in the receipt; image bytes are
not copied into the public repository.

Two observations remain intact:

1. The owner-named extraction still contained the older ISO with digest
   `376fd601...`. It failed the expected #286 hash check and was not attached or
   booted in this test. The matching image was found in the separate run
   `36939975061-attempt-1` extraction and verified before boot. An identical
   filename does not establish candidate identity.
2. On both Super+Space uses, Wofi initially displayed literal `drun` in its search
   field. Selecting that text and replacing it with `Chromium` successfully
   launched the browser. This is an unresolved reported launcher quirk; this
   review does not diagnose it or change its command in an evidence-only PR.

This closes the fresh #286 VirtualBox launcher/window interaction test within
the reported VM configuration. It supplies no new VirtualBox lock/refusal/PAM
unlock result; the earlier #283 blank-screen observation remains unresolved.
Installation/recovery, network/audio/suspend, external runtimes/backend health,
physical Skytech/RTX 5070, actual signing and source/license delivery remain
separate. The qualified source/ISO and all earlier failure receipts remain
unchanged. This documentation continuation qualifies no replacement image and
does not authorize merge, tag or publication.

Detection references: [systemd virtualization identifiers](https://github.com/systemd/systemd/blob/main/src/basic/virt.c),
[Oracle VMSVGA PCI definitions](https://github.com/VirtualBox/virtualbox/blob/main/src/VBox/Devices/Graphics/DevVGA-SVGA.h),
[systemd PartOf lifecycle semantics](https://www.freedesktop.org/software/systemd/man/systemd.unit.html),
and [swaylock appearance options](https://github.com/swaywm/swaylock/blob/master/swaylock.1.scd).
