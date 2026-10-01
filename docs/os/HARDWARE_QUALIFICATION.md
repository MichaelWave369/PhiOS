# Named hardware qualification handoff

The proposed first physical target is Mikey's Windows 11 Skytech desktop:
Core Ultra 9 285K, RTX 5070 12 GB and 32 GB DDR5. These are supplied candidate
details, not observed Linux compatibility. No physical hardware is qualified.
The successful QEMU tests use software rendering and provide no evidence for
this GPU, motherboard firmware, audio, network radios or physical power loss.

| Target | Current evidence | Gate |
| --- | --- | --- |
| Disposable x64 UEFI/KVM VM, 2 CPUs, 4 GiB RAM, 32-GiB disk | Live/installed login, persistent data, bounded signed update/interruption and matched recovery passed | Fixture-free exact final artifact and Linux proof workflow must also pass |
| Supplied Skytech/Core Ultra 9/RTX 5070 machine | No boot or driver observations | Live boot, GPU/input/network/audio/firmware tests first |
| Dedicated empty physical test disk | No selected disk or test | Exact installer identity/blankness/confirmation, no-media boot, persistence, update and recovery |

## Exact candidate first

Use only the normal image from the **Fixture-free OS candidate (unpublished)**
workflow, after its exact source/ISO receipt passes. Do not use the separate
QA image containing disposable test credentials/services. These images are
unsigned unpublished previews, not supported installers. Verify the downloaded
ISO against its exact `SHA256SUMS`, provenance and recorded qualification
receipt before preparing removable media. On Windows:

```powershell
Get-FileHash .\phios-linux-0.1.0-alpha.1-x86_64.iso -Algorithm SHA256
```

Compare the complete digest, not a filename or another build's successful test.
The first physical gate is a live removable-media boot with no installation.
Document actual firmware configuration, UEFI mode and Secure Boot status; this
candidate does not support Secure Boot or BIOS. Preserve the existing Windows
installation and its independent backup. A hardware installation test requires
a separately identified dedicated empty disk; the current installer does not
support dual boot, partition reuse or preserving contents on its target.

## Observations and manual results

Inside the exact normal live image, run as the ordinary user:

```bash
phios-hardware-report --iso-sha256 VERIFIED_ISO_SHA256 > hardware-observation.json
```

Replace the placeholder. The collector reads public source/kernel/UEFI,
board/firmware, PCI IDs/bound drivers and audio-card count. It performs no
effects, probes no credentials and records no hostname, account name, disk
serial, MAC/IP address, Wi-Fi SSID or user-state content. It marks the supplied
ISO hash as supplied, because it does not independently read the downloaded
ISO bytes. Absence of virtualization detection does not prove physical hardware.
All compatibility results remain `not tested` until actual observations exist.

Record pass/fail/not available with evidence for resolution/rendering and
multiple displays; keyboard/mouse/keymap; wired networking and Wi-Fi association,
DHCP/DNS; audio playback/recording; sleep/resume; shutdown/restart; and storage
visibility. Record missing drivers and services honestly. Audio/session locking
and Wi-Fi configuration are not currently qualified product features. A blank
audio-card count or successful PCI enumeration is not audio/GPU compatibility.
Resolve observed blockers, build a new exact candidate and repeat affected
tests before moving to installation.

Only after choosing a dedicated empty test disk should the operator review the
production installer plan and explicit confirmation described in INSTALLATION.md.
Then prove password-authenticated no-media boots, acknowledged canonical data
after restart, separate verified data-only backup, the actual signed target
transition, interrupted update, matched live-media recovery, preserved data and
inactive old authority. Physical power-loss testing is a separate storage gate,
not implied by terminating QEMU. Preserve failures and identify the exact
machine, source, ISO and transition; do not infer a supported hardware family.

## Release holds

Hardware results, the independently authenticated maintainer release public key
and full fingerprint, actual signed final transition, and third-party source/
license delivery review are still missing. RELEASE_ARTIFACTS.md describes the
remaining signing/publication gates. No release key is generated on behalf of
the maintainer and no test key becomes a release identity.
