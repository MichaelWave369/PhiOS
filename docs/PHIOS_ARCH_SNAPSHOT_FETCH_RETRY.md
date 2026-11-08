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

## Follow-up: independent Archiso package fetch on November 7, 2026

The merged PhiOS R9 source `82a845891c828f0af28aecdcc942958512a4c6b4` had a **green pull-request qualification**, but its separate [main-branch qualification](https://github.com/MichaelWave369/PhiOS/actions/runs/42413825424) failed. The `normal-image / fixture-free-candidate` job failed **inside `mkarchiso`**, after the builder's earlier signed prefetch and base package installation had succeeded. The frozen [archive.archlinux.org](https://archive.archlinux.org/) returned several `HTTP/2 stream reset` errors for `linux-firmware-*` and `icu` package files. No normal-profile ISO, QEMU preview, or normal installed recovery was qualified. The downstream release gate correctly failed.

The existing builder prefetch covered the host upgrade and builder dependency list, **not the independent Archiso `packages.x86_64` root filesystem transaction**. Merely retrying the builder step cannot fully mitigate this second request burst.

### Scoped resilience correction

- After `prepare_profile.py` creates the exact locked Archiso profile and before `mkarchiso`, run `phios_prefetch_archiso_profile_packages` with the generated `pacman.conf` and exact `packages.x86_64` file.
- Run `pacman --config <reviewed-profile> --disable-download-timeout -Syw --noconfirm` with every profile package, **without `--needed`**. That last distinction matters: the fresh ISO rootfs still needs packages that are already installed in the builder. `-Syw` downloads but never installs. Archiso shares the system pacman cache when no alternate cache directory is configured.
- Refuse missing/invalid package lists or a profile cache that differs from the builder cache. Bound prefetch to **three attempts**, each capped at 600 seconds with a 15-second termination grace, separated by five seconds. Preserve cached packages across attempts and refuse to build if prefetch cannot complete.
- Reduce the isolated Archiso profile's parallel package downloads from 5 to 2 to lower upstream concurrent HTTP/2 pressure. No package pin, snapshot date, repository, builder digest, signing policy, or VM gate is changed.
- Do **not** retry a partially installed rootfs or bypass the release gate. The actual `mkarchiso` install remains single-shot. Mock coverage verifies signed-pinned arguments, repeated errors then success, persistent error refusal, empty/malicious list refusal, same cache, no `--needed`, and exact build ordering.

**Required proof:** the new candidate's isolated prefetch mock CI plus a **full** PhiOS qualification: fixture-free ISO build, signed source/package inventory, QEMU normal desktop boot and installed recovery. A passed mock test is not evidence that the upstream archive was reachable or that a real ISO booted. Even after a successful CI rerun, it would not establish physical-device readiness, general release authorization, Secure Boot, or a supported native installer.

## Follow-up: PixelForge R10 post-merge builder fetch, November 8, 2026

The PixelForge R10 PR [#407](https://github.com/MichaelWave369/PhiOS/pull/407) itself passed its candidate tests and PhiOS qualification. It merged at `a8758f40606b2b08796908d96922eb522022c38d`. The **subsequent main-branch qualification** [run 42429247833](https://github.com/MichaelWave369/PhiOS/actions/runs/42429247833) encountered a different network failure than the #406 Archiso-stage retry: the **builder package prefetch** failed before the ISO was constructed. The frozen Arch archive returned 10-second connection timeouts for Chromium, GCC, LLVM libraries, Perl and Qt packages across all three attempts. No signed package transaction or application build failure is established by that log, and no normal ISO/VM install recovery qualified.

### Additional download-only fallback

The first builder package prefetch attempt still uses the ordinary pacman/libalpm downloader and its existing `--disable-download-timeout` setting. This protects against low-speed transfer timeouts but does **not reliably avoid the observed 10-second connection establishment timeout**. If that first attempt fails, a temporary pacman configuration is created that is a byte-preserved copy of the builder's existing configuration **except** for a single explicit `XferCommand` inside `[options]`. Attempts 2–3 remain `pacman -Sw --needed --noconfirm` without installing anything, but download over HTTPS via a bounded, redirected HTTPS-only curl transport with a 45-second connect window, HTTP/1.1, resume support, and two limited curl retries. Both whole-attempt timeouts remain 600 seconds. The temporary config is deleted when the function returns.

Pacman continues to resolve the same signed package identities/dependencies and enforce the same source configuration, repository Include directives, trusted keys, and `SigLevel`; curl does **not** substitute for pacman's signature validation. The fallback explicitly refuses an existing, unreviewed `XferCommand`, missing curl, unreadable pacman config, or a config without `[options]`. No mirror changes, package-version changes, insecure TLS flags, signature bypass, manual archive replacement, or retries of a partially applied installation occur. The initial full snapshot prefetch, single-shot installed transaction, independent Archiso cache prefetch, ISO/QEMU gates and release hold remain intact.

Offline test cases cover native-first behavior, transport fallback and identical configuration across later attempts, refusal to overwrite existing transfer policy, no-option-section refusal, no-package refusal, and full failure holding image qualification. **Only a fresh fixture-free image run with boot and install checks can prove the upstream network issue is actually resolved.** A green mock test cannot.
