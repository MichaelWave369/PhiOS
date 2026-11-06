# PhiOS R5E: installed-guest desktop lifecycle

**State: review-branch candidate, unqualified.** Not VM evidence, verified publisher authentication, signed public distribution, or permission to install third-party code.

## Gap addressed in code, pending installed-QEMU evidence

R5D proved desktop update/rollback on a disposable CI runner separately from a live UID-1000 app/data probe inside QEMU. R5E injects an additional test-only guest program through the existing serial probe. It calls the actual PhiOS DesktopAppInstaller, DesktopUpdateService and DesktopRollbackService inside the installed guest, and restores only its fixed fixture-owned JSON.

- Boot 1: create deterministic existing v0.40 fixture *inside installed guest*, register v1, launch real v1 loopback HTTP process; update desktop to v2, launch a new v2 process; deliberately make test data incompatible; separately review rollback request, restore v1 desktop and exact fixture JSON data, launch v1 process, record digest-bound results.
- Boot 2 (ISO detached): verify v1 desktop entry/payload/data hashes, launch a fresh v1 process. R5D persistence checks continue separately.
- Boot 3 (requested OS recovery): repeat identity and persistence checks after the existing root/EFI recovery.
- Host rejects missing PHIOS_R5E_GUEST_OK markers, wrong source/UID/boot identities, replayed IDs, changed transition SHA-256 values, changed data SHA and falsely claimed production authority. Retains guest observation in r5e_guest_desktop_boots.

The guest program reuses the existing deterministic v0.40 test-helper definitions without pytest. Those helper-generated BuildPackagePlan and AppInstallReceipt objects contain **synthetic fixture metadata**, not an authenticated real build. The installed guest runs *desktop registration/update/rollback*, **not AppInstallService.install**. The host injects this program only during qualification; it is not bundled in the release ISO.

| Claim | Status | Required actual evidence |
| --- | --- | --- |
| DesktopAppInstaller registration in installed guest | Code present | Normal/QA installed-QEMU tests at new exact source |
| DesktopUpdateService and DesktopRollbackService executed in installed guest | Code present | Raw serial/HTTP/receipt observations |
| User-data hash and v1 desktop survive no-ISO reboot and OS recovery | Host validator requires equality | Unique observed QEMU boot IDs and retained guest disk |
| Real AppInstallService.install inside guest | **NO** | Later release/build/install receipt binding |
| Publisher ownership, trustworthy artifact signature | **NO** | Independently verified publisher identity and key policy |
| Native third-party app sandbox and dependencies | **NO** | Separate enforcement/hardware acceptance |
| Generic app user-data rollback | **NO** | Approved per-app data-contract test |
| Public image release/physical-device support | **NO** | Independent signed, physical, licensing and release checks |

## Local preflight

Run python -m py_compile on packaging/linux/tests/r5e_desktop_guest.py, packaging/linux/tests/r5e_guest_validator.py and packaging/linux/tests/qemu_install.py. Run pytest -q tests/test_r5e_guest_validator.py tests/test_r5d_guest_probe_contract.py tests/test_app_platform_v061_living_application.py. These tests cannot replace the installed-VM image qualification.

## Smallest acceptance

After separate approval to execute workflows, run release-qualification.yml on the exact proposed PR head. Both normal-image and qa-image jobs must execute with exact source/ISO SHA-256 and real installed disk-only boots. Preserve raw serial/QEMU logs and inspect the service transition and live-process checks; do not treat the marker alone as independent proof.

Further R5F work must replace these fixture-only package receipts with genuine AppInstallService.install, reproducible artifact, ephemeral signed test root and independent approval evidence. R5E must not quietly gain production install authority.
