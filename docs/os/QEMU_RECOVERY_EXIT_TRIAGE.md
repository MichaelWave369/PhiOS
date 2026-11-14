# PhiOS disposable-VM recovery triage (2026-11-14)

## Observed failure

PhiOS main merge of PR #416, commit
`a39d1842c4e8c126d20ee3c3f399a82ab46659e6`, GitHub qualification
run `43636622250`, failed on both the original and failed-job rerun.

Original attempt:
- QA live image qualified neither boot nor reboot; the UEFI boot/session test
  timed out with only early firmware terminal output (no PhiOS marker).
- Normal image passed the fixture-free graphical live preview, installation
  and two installed-disk boots, but lost its serial channel during recovery
  media startup.
- Python tests, packaging wheel, memory-vector and ledger report jobs passed.

Second attempt:
- Normal fixture-free candidate, install and recovery qualified successfully.
- QA live image passed UEFI boot/reboot, disposable installation, two no-ISO
  installed boots, signed staging/refusals and deliberate broken-root
  observation. It then failed at `recover_live` before the recovery marker.
- The `recovery-live-serial.log` contained only 113 bytes of UEFI control
  sequences. `recovery-live-qemu.log` was empty. The original host-side test
  raised `live system/root/EFI recovery fixture failed` on an early QEMU exit.
- The exact reason QEMU exited was **not recorded**, so bootloader error,
  QEMU crash, host OOM-kill, runner host pressure, and other termination paths
  are not distinguishable from existing receipts. No root cause is proven.

These facts do **not** support calling the merged ΦPredict R0.2 code broken.
The isolated ΦPredict and Python jobs passed; the whole OS qualification is
red because real recovery tests did not pass on the same attempt.

## Bounded instrumentation

The new `packaging/linux/tests/qemu_failure_evidence.py` collector is invoked
*only on failure*, before host cleanup calls terminate/kill QEMU:

- Records QEMU's actual `poll()` return code before cleanup, including a
  negative POSIX signal number where present.
- Records sizes and SHA-256 hashes of existing serial/QEMU logs without
  duplicating their contents in JSON.
- Records fixed, nonsecret marker presence for UEFI dispatch, Linux start,
  boot success and recovery success (only in the last 64 KiB of serial).
- Records bounded cgroup-v2 memory events and per-stage deltas, plus
  `MemAvailable` and swap counters where available.

**A cgroup `oom_kill` count is not by itself proof it killed this QEMU.**
Missing counters are reported as empty, not invented. No SSH credentials,
tokens, local memory dumps, full serial transcripts or private paths are
copied to the new event record.

Instrumentation is attached to QA live boot, QA recovery-media boot and
the normal live install/restore driver, which showed similar symptoms.

## Acceptance boundary

This patch does *not* change RAM size, timeout, firmware, boot order,
recovery steps, tests' success conditions, release rules or any application
runtime. A missing recovery marker remains a qualification failure.
The new fields appear in the existing `boot-evidence.json` or
`installed-evidence.json` when failures occur.

Follow-up decision tree:
- If exit code is `-9` and cgroup OOM counters rise during the stage,
  investigate hosted-runner memory pressure and quantify it before
  changing VM allocation.
- If QEMU exits `0` or the serial indicates a wrong boot target,
  inspect persisted OVMF variables/boot selection separately.
- If a QEMU crash reports a signal/fatal stderr, preserve and diagnose that
  exact failure rather than blindly retrying the workflow.
- If no QEMU exit is observed but the guest times out, inspect boot
  screenshot/serial history and kernel/initramfs path.

For now the OS stays **not release qualified** until installation/recovery
success is actually observed on all required jobs of the same commit.
