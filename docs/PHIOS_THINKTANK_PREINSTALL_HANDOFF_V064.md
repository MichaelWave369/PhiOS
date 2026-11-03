# PhiOS ThinkTank v0.64: Real offline-build to App Platform artifact handoff

## Status: SOURCE-BOUND, HASH-VERIFIED, REVIEW-ONLY. NO INSTALL AUTHORITY.

This rung moves the existing merged ThinkTank v0.61 offline-cache build and
hosted Chrome render into a **real PhiOS App Platform package-artifact
inventory**. It deliberately does not call AppInstallService, register apps,
grant desktop launch, start providers, or change any existing release gate.

Pinned source: ThinkTank merged #54
`655d96f7ff892c9989f75cf874e74689f7694127`.
The later optional PhiServe backend from ThinkTank #55 is excluded.

## One real integration, with an explicit boundary

The existing ThinkTank pilot already executes an actual npm ci --offline and
npm run build under Docker --network none using a pre-staged npm cache, then
runs its compiled React UI in hosted Chrome. Its resulting receipt is NOT a
PhiOS App Platform build-execution receipt.

The new scripts/thinktank_preinstall_handoff.py:

1. Re-reads the canonical held candidate and AppManifest. Requires exact
   source commit, repository, unknown redistribution and empty app permissions.
2. Confirms Git-tracked upstream npm lock bytes, exact HEAD, and their digest.
3. Verifies every on-disk production dist artifact against the independently
   written hosted render receipt; checks static links, file bounds and symlinks.
4. Constructs **real phios.apps.package_install.PackageArtifact objects** for
   exactly those files. Computes the canonical App Platform artifact-set digest
   over their approved relative dist/ names, byte lengths, and SHA-256 hashes.
5. Emits a small review-only JSON inventory, retained alongside the existing
   hosted Chrome evidence. No executable bundle or npm cache is uploaded.

This is the precise asset/receipt handoff the installer previously lacked.
It is **not** equivalent to a build-execution receipt, an offline build receipt,
an approved package plan, actual guest installation, or a production release.

### Acceptance command (existing hosted pilot workflow)

The dedicated workflow builds the actual pinned ThinkTank source, then runs:

    python scripts/thinktank_preinstall_handoff.py \
      --source .pilot/think-tank \
      --dist "$RUNNER_TEMP/thinktank-offline-work/dist" \
      --committed-lock .pilot/think-tank/package-lock.json \
      --hosted-receipt pilot-evidence/thinktank-web-hosted.json \
      --output pilot-evidence/thinktank-preinstall-handoff.json

Focused synthetic negative cases:

    python -m pytest -q tests/test_thinktank_preinstall_handoff.py

The new test suite refuses source or lock drift, content tampering, missing
assets, unsafe links, candidate promotion, and authority injection in a
same-run hosted receipt.

## Actual next gate: approved positive QEMU lifecycle

- Review third-party dependency and asset redistribution permissions.
- Run the existing PhiOS *governed* acquisition, build execution and npm
  offline build services to produce their genuine canonical receipts, subject
  to exact operator review. The hosted receipt is NOT permitted as a substitute.
- Only then allow the existing v0.33 package planning and installation services
  to consume the verified artifact set in a disposable QEMU guest.
- Confirm real Wayland/browser launch, persistence on no-ISO reboot, and
  v0.40 side-by-side update and rollback with independent guest evidence.
- Keep one-use build permissions, desktop grants, app registration and release
  approvals separate. No silent promotion from candidate catalog or CI green.
- Never ship compiled third-party assets in public CI artifacts until approved.

Both this inventory and the merged v0.63 real-guest HOLD gate are
necessary-but-not-sufficient evidence. Neither claims that ThinkTank is
installed or live inside PhiOS.

**Ledger Above Ego. DONE Means Verified.**
