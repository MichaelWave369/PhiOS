# Φ Universal App Center R5A — Verified Artifact Intake and Device-Owned Lifecycle

**R5A ships an actual local artifact SHA-256 preflight, a native Android installed-app management route, and browser-managed PWA update/status controls. It does NOT ship a general cross-platform installer or automatically qualified rollback.**

## What now works

| Platform | Evidence | Real device-owned action | Still not authorized |
|---|---|---|---|
| PhiOS Linux development checkout | `interop/artifact_preflight_v1.py` hashes an operator-selected **local regular file** against an explicit JSON proposal and emits a content-integrity receipt | Actual locally bounded SHA-256 verification; PhiShell's Apps window links to the existing read-only System Inspector package observer | SHA match is not signature, origin, license, dependency or runtime safety validation. This preflight never invokes the existing `phi-app` installer |
| Android HOME debug APK | `LauncherApps.getActivityList` reports *actually launchable apps* for current user | Per-app **Info** opens Android's App info; a non-system, non-self app may request an **Android OS-owned uninstall**, with an extra PhiOS confirmation plus Android's own approval | Does not install APKs, update packages, uninstall system/Home apps, silently remove apps, request privileges or prove a GitHub repo is installed |
| PhiOS Web PWA | Browser `display-mode: standalone` is an **observed display context**, not install provenance; `appinstalled` event is session-local | Existing browser-managed install prompt when available, and a **user-initiated scoped service-worker `registration.update()` check** | JavaScript cannot uninstall a PWA, attest its installed version, downgrade an app, or promise a real update was found |
| PhiOS Mobile PWA | Same browser display-context and service-worker observations | User-requested local PWA update check; explicit navigation to first reviewed Web app | No Android native effects or APK installation |

## Local verifier contract (actual bytes, no untrusted code execution)

Manifest JSON schema: `interop/artifact-intake.v1.schema.json` (`phios.artifact-intake.v1`). Run from the **PhiOS source checkout**:

```bash
python interop/artifact_preflight_v1.py \
  --manifest /home/operator/review/app-intake.json \
  --artifact /home/operator/review/release.zip
```

The manifest is bounded at 16 KiB and requires:
- a stable ID and source URL that match the pinned public catalog;
- a 40-hex source commit **declaration** (not yet independently verified against GitHub);
- one exact local basename, byte size 1..256 MiB, and lowercase SHA-256 expected digest;
- requested action `verify_only`, with publisher signature, license, device compatibility, operator approval and install authority **all false**.

The CLI reads only regular local files, refuses symlinks where the OS supports `O_NOFOLLOW`, streams SHA-256, checks file metadata before and after reading, and emits a JSON receipt on successful match. It does **not** write to a package database, acquire dependencies, download code, verify authorship/signatures, start a process, or grant `phi-app` authority. A malicious manifest author could compute a valid hash for malicious bytes. **Integrity != authenticity.**

Native PhiOS still relies on the existing App Platform v0.26+ intake, explicit build/toolchain/install/launch gates, and artifact/recovery policies. This R5A verifier is complementary evidence, not a second privileged package manager.

## User-action and rollback model

The only newly added real removal path is the **Android system uninstaller** for qualifying current-user, non-system installed apps. The OS owns the actual confirmation and result. Removal can delete app data; **automatic rollback is not available**. PhiOS Mobile must not claim recovery until an actual tested rollback artifact and data policy exist. On Linux, governed installed apps and package records remain separate from source bookmarks. On Web, the browser owns PWA removal and updates.

## Qualification gates

- Core: Python negative tests for altered bytes, exact-size mismatch, manifest corruption, symlinks, unknown identities, forged authorization, oversized files; PhiShell build and existing VM qualification.
- Mobile Android: JVM tests of non-system/non-self install observations, plus emulator check that a real installed fixture exposes App info and Android-owned uninstall request **without performing removal**, and that stock Home can be restored.
- Web: Chromium desktop/phone acceptance checks current browsing context, explicit update query and honest uninstall guidance.
- Mobile PWA: offline asset checks and Node assertions that update checks never claim an installed version.

**Next R5B before any generic INSTALL button:** independent publisher identity + license review, exact signed/reproducible artifact, dependency/runtime/sandbox plan, tested installer adapter, explicit consent, signed result receipt and **verified rollback on that device**. Each platform needs separate acceptance evidence. No unattended installs of the 225-source catalog.
