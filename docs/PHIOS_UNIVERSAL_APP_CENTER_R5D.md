# Φ Universal App Center R5D · Living Application and User-Data Recovery

**R5D is two independent, real, test-only qualifications. It is NOT an end-to-end signed application installed and rolled back through PhiOS App Platform inside the guest.**

## Proof A: Actual app process + governed lifecycle + fixture data restore (disposable runner)

The \`tests/test_app_platform_v061_living_application.py\` test uses an isolated temporary directory and the **existing** \`DesktopAppInstaller\`, \`DesktopUpdateService\`, \`DesktopRollbackService\`, their explicit approvals, version retention, grants, receipts and catalog checks.

Unlike the R5C synthetic file-content probe alone, R5D starts actual, bounded **loopback HTTP server subprocesses** for two test versions. The source of that test-only server is \`tests/fixtures/r5d_living_server.py\`; it serves the versioned installed app payload's actual \`dist/index.html\` digest and a separate user-data JSON file. It does NOT execute arbitrary downloaded source.

- Start v1 process and verify response/status, PID, asset SHA-256 and user-data read/write.
- Pin an exact SHA-256 snapshot of the fixture's external JSON user data.
- Use \`DesktopUpdateService\` to update the real desktop registration from v1 to v2.
- Start a new v2 process, observe its installed payload digest, and deliberately run a **test-only migration** that changes JSON schema v1 → v2. A post-update compatibility policy fails because v2 is incompatible with v1's expected schema.
- Require the existing independently explicit exact \`DesktopRollbackRequest\` and use \`DesktopRollbackService\` to restore the previous launcher entry, grant and catalog. R5C's read-only auditor verifies the actual rollback receipt/retention marker/bytes.
- Restore the **one test-owned JSON file** only after validating its pin and supported schema; verify that the old file bytes and SHA-256 return.
- Start a **new live v1 process** and prove that it reads the restored data and can write to it again.
- Reject tampered or symlinked snapshots without modifying the live test data.

The dedicated \`Φ R5D Living Application and Data Recovery\` CI publishes **runner-living-app-recovery.json** only on success. Its producer scope is \`disposable_linux_ci_runner_test_only\`. The report claims tested processes, pinned fixture data restoration and actual **desktop service** transitions, but deliberately holds publisher and device authority.

## Proof B: Actual test app process and user data across installed PhiOS VM boots

The existing \`packaging/linux/tests/qemu_install.py\` uses real QEMU, an installed disposable disk, a normal UID 1000 account and reboots with **no ISO attached**. R5D injects the **test-only** \`living_app_guest.py\` into that guest's interactive Python validation session. This source is passed from the CI host: it is not bundled in the released ISO, is not a signed package, and is not an App Platform-installed application.

- On the first installed boot, create a private per-user state file under \`~/.local/state/phios/r5d-living-test/\`.
- Start a local Python HTTP service bound to \`127.0.0.1\`, verify its actual response and UID, use the service to increment stored user data, and stop the process.
- QEMU is subsequently stopped/abruptly terminated by the existing qualification harness. On the next no-ISO installed boot, the test **must find the prior file and exact expected counter**, start a **new process**, and read/write it successfully again.
- When the existing OS recovery path requests a third installed boot, verify a new app process still reads the prior counter following the OS-level recovery exercise. The test does not modify a production package.
- Each boot emits \`PHIOS_R5D_GUEST_APP_OK:\` with boot ID, source commit, phase, data hash, honest scope flags and explicit held authorities. The host rejects missing/incorrect markers, source/boot mismatches, false reports of signed installs, and missing user-data continuity.
- Guest results are included in the **existing Linux image qualification artifact and review metadata**, not a standalone production-app certificate.

Successful Linux image jobs would prove the test-only process and data survived real VM guest boots and the existing OS-level recovery sequence. They would **not** prove that the exact signed v2 test app was installed and rolled back inside the guest.

## What is **not** yet proven

| Gate | R5D |
|---|---|
| Actual user-space HTTP process before/after governed desktop update and rollback | In disposable runner |
| Pin-verified, specific test JSON user-data restore after incompatible migration | In disposable runner |
| Actual test-only app process and user data across no-ISO installed VM boots | In installed QEMU guest, once Linux image CI passes |
| Owner-to-publisher-key independent authentication | **NO** |
| Exact R5B signed publisher release matched to R5D installed payload | **NO** |
| App Platform update/rollback operation actually executed inside installed VM guest | **NO** |
| Arbitrary application user-data migration and rollback | **NO** |
| Native Linux app permission/sandbox and dependency qualification for third-party code | **NO** |
| Production native install/update/rollback authority | **NONE** |

No new native privilege bridge, app installer, firmware action, automatic deployment or device data deletion is introduced. Existing normal-ISO/QA-ISO VM work remains subject to full PhiOS CI gates.

## Running the suite

\`\`\`bash
python -m pip install -e '.[dev]'
pytest -q \
  tests/test_app_platform_v061_living_application.py \
  tests/test_r5d_guest_probe_contract.py \
  tests/test_app_platform_v060_recovery_lab.py
\`\`\`

The installed VM proof is run by the existing Linux image qualification workflows because the host-side \`qemu_install.py\` now invokes the new R5D guest probe on each installed boot. No network connection is needed beyond loopback.

**R5E next:** bind a reproducibly built and independently authenticated signed artifact to one release-install proposal, install and launch **that exact artifact in the disposable installed VM**, prove its permissions/dependencies and process health, deliberately run the exact update/rollback services *inside the guest*, and verify an operator-approved data recovery policy. Only then discuss a governed native INSTALL action in PhiShell.

**R5C verified a filesystem rollback. R5D verifies actual test processes/data. Neither makes an unsigned third-party program trustworthy by wishful thinking.**
