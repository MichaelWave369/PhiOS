# Φ Universal App Center R5C · Trust & Recovery Lab

**Status: real side-by-side desktop transition and recovery rehearsal in disposable Linux CI filesystem. NOT a production Linux ISO, not a physical-device rollback, not a publisher approval.**

## Why this rung exists

PhiOS already has the R5A content-integrity verifier, the R5B Ed25519 statement review, existing v0.50 release-install proposal and package installer, and v0.40 actual desktop update/rollback services. R5C creates a **repeatable, positive and negative recovery rehearsal** around those real services and retains bounded evidence.

## Actual workflow exercised by the R5C test

1. Build two local test app payloads and their exact receipts in a fresh pytest temporary directory. These are synthetic **file-based test apps**, not downloaded third-party production apps.
2. Register **v1.0.0** using the actual \`DesktopAppInstaller\` so there is an actual desktop entry and active launch grant in this isolated filesystem.
3. Plan v1.0.0 → v2.0.0 and require the existing exact update-plan SHA, prior grant, candidate desktop-plan SHA, and requested permission before invoking \`DesktopUpdateService.execute\`.
4. Verify **actual launcher bytes changed**, a candidate bundle and signed-*none* retention marker were created, the update receipt was written, and the actual \`snapshot_desktop_catalog\` shows v2 ready and v1 retained/inactive.
5. Run a **synthetic file-content health probe** that deliberately requires v1 text, while v2 contains v2 text. This *simulates* a failed post-update health policy without claiming that a real process crashed, network was tested, or the package was malicious.
6. Require a separate, non-authoritative rollback plan and explicit exact rollback permissions, then invoke the existing **DesktopRollbackService.execute**.
7. Verify **the original v1 launcher bytes and SHA-256 return**, the target v1 bundle and candidate v2 bundle remain present, the actual catalog shows v1 ready and v2 retained/inactive, and original/update/rollback receipts plus the new retention marker form a consistent chain.
8. Produce the bounded JSON report \`phios.disposable_recovery_lab.v0.1\`. The independent \`phios.apps.recovery_lab.audit_disposable_recovery\` reader cross-checks **actual on-disk files, persisted receipt JSON, receipt digests and catalog state**. It makes no changes and cannot generate install/rollback authority.

The same suite deliberately tests:
- an injected receipt-storage failure during update, demonstrating that the launcher remains on v1 and the candidate desktop bundle is not left active;
- a tampered retention marker, which must block rollback *without touching the active launcher*;
- forged receipt values, missing persisted receipts, and fake claims of a real process crash, which the auditor must reject.

## CI and artifacts

Run:

\`\`\`bash
python -m pip install -e '.[dev]'
pytest -q tests/test_app_platform_v060_recovery_lab.py tests/test_app_platform_v040_update_rollback.py
\`\`\`

The dedicated \`.github/workflows/r5c-trust-recovery-lab.yml\` repeats these tests on an ephemeral Ubuntu GitHub Actions runner and publishes a 14-day **disposable-recovery-observation.json** artifact only after passing. CI validates the report's canonical SHA-256 and requires all production, real-process, signed-artifact linkage, dependency trust, owner trust, device qualification and user-data recovery flags to remain **false**.

The artifact digest detects accidental modification, **not independently authenticated authorship**. The trusted CI run and its job provenance are separate evidence; a user-provided JSON file alone does not prove a lab happened.

The standard PhiOS tests also cover:
- **R5B Ed25519 offline signature review** under an operator-supplied public-key fingerprint, without proving independently enrolled publisher ownership;
- the **v0.50 package installer** and exact release-proposal receipts on another isolated fixture.

These gates currently run on **separate test fixtures**, not one end-to-end signed production package. Do not claim that the publisher-signed release under review was installed and recovered in this R5C scenario.

## Scope and next acceptance

| Gate | R5C evidence |
|---|---|
| Actual local desktop update and exact rollback on disposable filesystem | Rehearsed by CI, after its workflow succeeds |
| Simulated receipt write failure | Actual failure injection, no switched launcher left behind |
| Tamper refusal | Verified retention marker and receipt rejection tests |
| Independent publisher-to-key ownership | **NOT VERIFIED** |
| Exact signed artifact bound to recovered fixture | **NOT VERIFIED** |
| Dependency, toolchain, license, sandbox compatibility | **NOT VERIFIED** |
| Real application process health | **NOT TESTED** |
| Linux ISO boot, installed recovery in UEFI VM, physical-device rollback | **NOT TESTED BY R5C**; PhiOS OS image jobs remain separate |
| User data consistency across rollback | **NOT TESTED** |
| Production-install authority | **NOT GRANTED** |

**R5D next:** enroll owner keys through an independently reviewed trust root, bind the exact reproducibly built signed app artifact to the package receipt, then rehearse a real app process, tested dependencies, user-data policy and recovery on a disposable **installed Linux VM image**. Do not enable an App Center native INSTALL button until those gate results are recorded and tied to the exact candidate.

**Integrity ≠ authenticity. A rollback plan ≠ a successful rollback. A temporary filesystem rehearsal ≠ production recovery.**
