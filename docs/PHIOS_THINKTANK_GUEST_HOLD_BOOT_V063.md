# PhiOS ThinkTank v0.63: actual installed-guest HOLD qualification

**Scope: genuine x86_64 PhiOS VM boot / login / reboot and negative application
qualification. This rung is NOT a ThinkTank install, launch or release.**

The merged v0.62 assessor (PhiOS PR #366) can verify local installed app
receipts, but its unit tests and operator instructions do not prove it ran
inside the installed PhiOS operating system. This rung closes that narrower
evidence gap first, without bypassing license review or any App Platform grant.

## What the existing normal-image CI now does

The unchanged unpublished normal PhiOS ISO is built using its existing
production profile, then installed to an automatically created disposable
32-GiB QEMU disk by packaging/linux/tests/qemu_install.py.

The existing host harness already proves regular password login, installed
no-ISO boot, persistent state across an abrupt virtual restart, and the
recovery path with multiple distinct boot IDs. This PR adds
--thinktank-held-probe to THAT SAME installed-guest session.

Each authenticated installed guest executes only the separately supplied
read-only code from packaging/linux/tests/thinktank_guest_hold_probe.py.
The probe is injected over the existing QEMU serial test channel.
It is **not** baked into the fixture-free production ISO or installed as a
system service.

For each boot it observes:

1. UID 1000 logged in on the installed UEFI guest, not archiso.
2. Exact /usr/share/phios/source-commit and real kernel boot UUID.
3. A real phi-app CLI present on the test user's PATH.
4. Real phios.apps.desktop_catalog.snapshot_desktop_catalog on the user's
   actual default PhiOS App Platform directories.
5. No installed phios.thinktank-web package directory, desktop bundle,
   catalog entry, or persistent XDG launcher. Unsafe links count as failures.
6. The guest's /sys/class/net contains only lo, corroborating the preexisting
   QEMU -nic none setting for this specific virtual machine. This is not
   proof of a generally hardened process sandbox.

The guest prints one small PHIOS_THINKTANK_GUEST_HELD JSON marker. It does
NOT execute a build, install an app, invoke a model/provider, launch the
ThinkTank browser UI, or write app state.

The host independently validates exact schema and fields, source SHA,
phase/boot UUID, guest UID, the held-only status and every FALSE authority
field. It rejects replayed/missing boot IDs, unexpected interfaces, fake
installation or release claims, source mismatch and malformed receipts.
The host attaches the bounded observations to the existing installed-evidence
JSON and requires all three distinct fixture-free guest boots to be present.

## CI and tests

The existing .github/workflows/os-release-candidate.yml checks focused
negative-control tests *before* it builds the normal ISO:

    python3 -m unittest discover -s tests -p 'test_thinktank_qemu_held_gate.py' -v

It then runs its normal fixture-free QEMU recovery with the new flag:

    python3 packaging/linux/tests/qemu_install.py \
      --fixture-free --recovery --thinktank-held-probe \
      --iso dist/fixture-free/phios-linux-0.1.0-alpha.1-x86_64.iso \
      --source "$(cat dist/fixture-free/source-commit.txt)" \
      --output "$RUNNER_TEMP/phios-normal-installed"

The new gate has **no automatic green claims** until the full workflow
succeeds on the exact PR head. Do not infer native Windows/macOS, Quest,
physical x86_64, or native Android qualification from this VM test.

## What remains held (positive ThinkTank app lifecycle)

The reviewed ThinkTank source is SHA
655d96f7ff892c9989f75cf874e74689f7694127. Its currently pinned
frontend and PhiOS-owned Trellis packaging/reproducibility evidence remain
separate from production installer/redistribution authorization.
The existing v0.69 preflight keeps seven human-review blockers.

A later operator-approved rung must:
- reconcile exact dependency and static-asset license/redistribution evidence;
- produce a private non-released app candidate from the pinned source using
  the existing offline build and Trellis package staging;
- use ONLY PhiOS's existing v0.25-v0.57 governed build/install path,
  v0.35 static adapter, v0.38 desktop grant, and v0.40 update/rollback;
- run a genuine visible ThinkTank interaction inside a disposable installed
  guest, with its optional PhiServe bridge unapproved and disabled;
- compare an explicitly reviewed second version, reboot, and prove rollback
  reactivates the original bundle and preserves the correct user data;
- retain scoped hash-bound receipts and negative controls without app
  tarballs, credentials, or unapproved third-party binaries in public
  workflow artifacts.

**A PASS for this rung means a real PhiOS installed guest observed a held
ThinkTank candidate across boots. It does NOT mean ThinkTank was installed.**

Ledger Above Ego. DONE Means Verified.
