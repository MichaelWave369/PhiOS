# PhiOS CI QEMU crash isolation: Ubuntu 24.04 LTS runner trial

## Evidence and scope

The post-merge PhiOS qualification of commit
`e9b28ad4c453a60aa989324694259c39c79af62b` failed in
[GitHub Actions run 43661264730](https://github.com/MichaelWave369/PhiOS/actions/runs/43661264730).

The normal ISO successfully passed initial graphical live preview, installation
and two installed-disk boots. It correctly observed an intentionally corrupted
initramfs causing a kernel panic. The final attempt to boot the *same ISO*
as recovery media then failed at the first normal login wait.

The fail-closed diagnostic added in PR #417 made the fault actionable:

- `normal_live_vm_failures[0].stage` = `normal-restore-live`
- `qemu_exit_code_before_cleanup` = **-11** (Linux signal 11, SIGSEGV)
- 113 bytes of early firmware/terminal escape output, no Linux or PhiOS marker
- Empty QEMU stderr log, but QEMU had already exited with SIGSEGV
- Host `MemAvailable` was about 13.3 GiB. Cgroup memory counters were
  unavailable; absence of an OOM counter cannot categorically exclude it.

The affected workflows had `runs-on: ubuntu-latest`. On the failed run this
selected a newer Ubuntu runner, which installed QEMU 10.2.1. This is a
**host emulator crash**, not evidence of a regression in PhiPredict scoring
or a verified failure of the PhiOS recovery program.

## Controlled hypothesis

The QEMU/OVMF/KVM combination delivered by the moving `ubuntu-latest` image
might be responsible for intermittent early-startup SIGSEGV after restarting
the disposable guest and remounting the recovery ISO.

To test this hypothesis, pin only the two VM image qualification jobs to
`ubuntu-24.04`. Ubuntu 24.04 is an LTS base with a separately supported QEMU
package family. Always print the exact installed OS, kernel, QEMU version and
SHA-256 of the two OVMF firmware files during the qualification job.

The image build still uses the exact committed Arch builder-image digest
and the exact source commit. No PhiOS package or runtime code changes.

This does **not prove** the new runner will solve the crash. It may expose
a compatibility difference, and a single success does not establish
absence of intermittent failure. For a real fix, compare several
independent runs and, if necessary, gather a QEMU native backtrace.

## Unchanged release integrity

- The same production normal ISO build and independent unsigned QA ISO build.
- The same QEMU guest memory, CPU count, devices, pflash variables,
  disk image, installation commands and recovery sequence.
- The same deliberately damaged-root test and requirement to boot the
  original recovery ISO and restore its matched checkpoint.
- The same runtime security restrictions and read-only review metadata.
- The same failure propagation and release gate. **No retries,
  tolerance increments, skips, forced success or auto-merge.**

If any of the original image qualification, installed-disk recovery,
Python, wheel, memory, ledger, or final release-gate checks fail, the
experiment fails.

## Acceptance

PR CI must pass all existing gates on the candidate commit. After merge
(if accepted) an independent push-to-main qualification must also pass.
Further episodes of SIGSEGV require a proper native QEMU crash backtrace,
not merely relabeling the problem a flaky test.
