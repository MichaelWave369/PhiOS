# PhiOS ThinkTank guest lifecycle v0.62: held, read-only acceptance assessor

## Scope

This rung does not install ThinkTank, boot an ISO, launch Chrome, grant desktop
permissions, start a model, or approve redistribution. It connects existing
PhiOS App Platform receipt validators into one read-only assessor intended for
an already provisioned, disposable PhiOS x86_64 guest.

Reviewed upstream ThinkTank source: 655d96f7ff892c9989f75cf874e74689f7694127
(merged ThinkTank PR #54, with committed npm lockfile).
The phios.thinktank-web catalog candidate remains HELD_FOR_OPERATOR_REVIEW with
redistribution unknown, no app installation, and no provider/model authority.
ThinkTank PR #55's optional PhiServe integration is NOT included in this pin.

## Actual evidence inspected

The assessor reuses the current:
- Candidate inspector, refusing unauthorized source/permissions/review changes
- Desktop catalog scanner, rehashing installed static files and verifying
  existing browser/static plans, desktop grant, and XDG entry
- Installed BuildPackagePlan and AppInstallReceipt parsers, requiring the exact
  reviewed ThinkTank source repository/commit and canonical receipt lineage
- Optional DesktopLaunchReceipt parser, binding completed status to the current
  grant/plan/installed app
- Optional DesktopUpdateReceipt and DesktopRollbackReceipt pair, requiring
  the rollback to match the update and current active bundle/grant

No file writes, network calls, app install, launch, process execution, service
start, or permission mutations are performed. It refuses symlinked JSON files,
oversize JSON, stale source pins, mismatched receipts, and duplicate ready apps.
Its JSON result includes only source and artifact hashes, bounded flags, and
required next acceptance gates, not personal data or raw application state.

## Example inside the guest

Provide the real PhiOS application roots selected for the test; these path
names are placeholders, not asserted OS defaults.

    python scripts/thinktank_guest_acceptance.py \
      --desktop-root /PATH/TO/DESKTOP_BUNDLES \
      --applications-root /PATH/TO/XDG_APPLICATIONS \
      --install-root /PATH/TO/PHIOS_INSTALLED_APPS \
      --launch-receipt /PATH/TO/DESKTOP_LAUNCH_RECEIPT.json \
      --update-receipt /PATH/TO/DESKTOP_UPDATE_RECEIPT.json \
      --rollback-receipt /PATH/TO/DESKTOP_ROLLBACK_RECEIPT.json \
      --require-complete-lifecycle

For the initial state with no installed app, omit the optional receipts and
the strict flag. The report then remains HELD, with explicit missing evidence.
The strict flag must return nonzero until the local install, launch and rollback
receipt chain is self-consistent. Even then it does not attest a VM boot.

Focused tests:

    python -m unittest discover -s tests -p 'test_thinktank_guest_acceptance.py' -v

These tests include mocked App Platform receipts. They do not constitute real
PhiOS installation, independent QEMU qualification, physical device coverage,
or release authorization.

## Actual QEMU acceptance still required

1. Reconcile the reviewed upstream lock and existing Trellis/closure evidence.
   Preserve the seven outstanding v0.69 release preflight holds. Never publish
   unreviewed or potentially nonredistributable dependencies.
2. Create an unpublished, disposable x86_64 guest using the existing
   packaging/linux/tests/qemu_install.py machinery. Record the exact image and
   source commit, a second no-ISO boot, and network isolation, with no host disk
   attached and no personal user state.
3. Subject to separately reviewed, exact operator authorization, use ONLY the
   existing PhiOS app intake/build, package install, static-web, browser-session
   and desktop plan/grant services. Do not create a parallel installer.
4. Observe an actual visible ThinkTank UI launch and local interaction, deny
   unapproved outbound access and model/provider bridges, and independently
   verify state persistence after a guest reboot.
5. Exercise a second separately reviewed app revision through the existing
   side-by-side update and v0.40 rollback contract. Rehash both versions and
   compare the existing receipt chain using the assessor.
6. Retain only sanitized, SHA-bound artifacts and refusal evidence. Do not
   claim physical hardware support, license clearance, operator permission
   or external DONE from a hosted test.

## Evidence limits

- Ready desktop catalog means local filesystem and receipt consistency only.
- Matching launch receipt does not independently attest a rendered GUI.
- Matching rollback receipt does not independently attest the switch/reboot.
- No guest boot, network-denial, restart, physical device, Windows/macOS,
  Android/Quest, or publication claim is made by this script.
- Output status always remains HOLD_FOR_OPERATOR_REVIEW.

## Next separate creative pipeline rung

For one legally usable, locally acquired UE/Fab static mesh, retain exact
source license and GLB export hashes. PixelForge must perform guarded local
export and verify GLB bytes; FramefieldStudio must import the same GLB and
animate a transform-only scene, explicitly excluding unverified skeletal
rigging/skinning and broad material support. Capture an actual sequence/video
handoff into ParaCut, final output digest, and Windows workstation acceptance.
No Fab source asset redistribution or general pipeline DONE without license
review, actual handoff receipts, and physical-device verification.

Ledger Above Ego: passing an assessor is not a booted guest, and a booted guest
does not authorize redistribution.
