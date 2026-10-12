# PhiOS pinned Arch snapshot package-fetch resilience

## Observed failure

PhiOS PR #306 initially passed its **offline public ecosystem catalog**, PhiShell build, and Python tests. The `normal-image / fixture-free-candidate` job failed before image construction during the isolated Arch package transaction:

```
error: failed retrieving file 'python-3.14.7-1-x86_64.pkg.tar.zst.sig'
  from archive.archlinux.org : Operation too slow.
  Less than 1 bytes/sec transferred the last 10 seconds
error: failed to commit transaction (failed to retrieve some files)
```

This is an upstream HTTPS transfer-speed timeout while retrieving a signed Arch Linux package **signature**. It is not a failed source compilation, completed ISO, package authenticity rejection, or post-boot qualification. The package transaction refused to proceed.

## Change

`packaging/linux/build-linux.sh` continues to use the exact `packaging/linux/release.json` Arch archive snapshot, Archiso version and pinned Docker builder digest. Before `pacman -S --needed` installs the existing exact package list, it invokes `phios_prefetch_snapshot_packages`:

- `pacman --disable-download-timeout -Sw --needed --noconfirm` downloads the **same signed packages and dependencies** from the **same archive**; `-Sw` does not install anything.
- Up to **three** attempts are permitted. Each attempt is bounded by GNU `timeout` (600 seconds plus a 15-second termination grace period). Pacman is allowed to keep valid signed packages already downloaded between attempts.
- The retry path does not change package identities, repository URLs, snapshot date, trusted signing keys, signature validation, installed versions, or install permissions. No mirror fallback or signature bypass is permitted.
- If prefetch never succeeds, the script **fails closed** and does not attempt the subsequent package installation.
- After successful prefetch, the actual `pacman -S --needed` is deliberately a **single transaction without an automatic retry**. The existing pinned Archiso version check and all later ISO/QEMU release gates remain intact.

This specifically addresses transient archive speed faults. It does not guarantee the archive is available, that signatures are valid, or that the OS will build/boot/install successfully. Other stages may still fail independently.

## Acceptance

The offline tests in `tests/test_arch_snapshot_prefetch.py` mock pacman to prove first-attempt success, two-transient-errors-then-success, persistent three-attempt failure, no-package refusal, exact package/option reuse and builder order. `.github/workflows/arch-snapshot-fetch-contract.yml` runs these without downloading external packages.

The existing `PhiOS qualification` workflow must still build the **fixture-free ISO** and complete QEMU boot/installation/recovery checks against the exact changed source before an OS-release candidate can be promoted. A green mock test alone is not a signed/booted ISO.

**Ledger Above Ego. DONE Means Verified.**
