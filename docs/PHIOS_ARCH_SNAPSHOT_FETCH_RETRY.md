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


## Follow-up: full-upgrade metadata timeout in PhiOS PR #425, November 21, 2026

The exact-head PhiOS R4a qualification failed twice in both normal and QA
image builders **before any package installation**. Pacman could not retrieve
the frozen archive's `core.db` and `extra.db` metadata: each default transfer
connection timed out after roughly 10 seconds. Attempts 1–3 all failed in
`phios_prefetch_snapshot_upgrade`. Python/typing/package tests passed, and
the release gate correctly held the candidate.

The prior HTTPS-only curl fallback covered `phios_prefetch_snapshot_packages`,
but **not the earlier full-snapshot upgrade prefetch**, which is the stage
that actually failed. It already had three bounded attempts but repeated the
native 10-second connection deadline on every attempt.

### Targeted correction

- Keep attempt 1 native pacman and the original `-Syyuu --downloadonly`
  selection against the frozen `2026/09/30` Arch archive.
- After the first failure, reuse the existing `phios_make_pinned_archive_curl_config`
  helper for attempts 2–3. The configuration copy preserves the exact
  repository Include directives, signed package keys and SigLevel and adds
  only HTTPS-only curl transfer with a 45-second connect budget.
- Keep existing 600-second whole-attempt bounds, three attempts and two
  five-second backoffs. Delete the temporary transfer configuration.
- Refuse unexpected existing transfer commands or malformed configurations.
  Never change mirrors, package pins, signature checks, `--downloadonly`
  semantics, single-shot install, ISO or QEMU qualification.
- Offline regression tests now check native-to-curl fallback, unchanged
  signed config, and fail-closed refusal on unreviewed configs.

**Required verification:** this correction needs exact-head offline contract
tests and the full image build plus QEMU qualification. Prior two CI failures
were external archive timeouts; no completed ISO/boot can be claimed. A new
live failure must be investigated separately rather than bypassed.


## Follow-up: pinned archive's origin unreachable after HTTPS retry (PR #425)

The R4a image builds at commit `96784dc` reached the new fallback
correctly, but `archive.archlinux.org` remained unreachable from both
isolated GitHub runners: native pacman hit 10-second connection timeouts,
and HTTPS-only curl hit 45-second connection timeouts or a TCP reset.
Both image builds remained HELD. There was no completed ISO or boot test.

Arch Linux's own infrastructure documents the dedicated managed archive
host **`https://umea.archive.pkgbuild.com`** in
[its infrastructure server inventory](https://github.com/archlinux/infrastructure/blob/main/docs/servers.md#archive-mirrors).

The next candidate uses precisely two **Arch-operated historical archive**
servers, in this order:
1. `umea.archive.pkgbuild.com/repos/2026/09/30/$repo/os/$arch`
2. `archive.archlinux.org/repos/2026/09/30/$repo/os/$arch`

Both share the **same pinned September 30, 2026 snapshot path**.
The builder mirrorlist and the separate Archiso `pacman.conf` list these
same two hosts, so an archive-origin failure cannot simply recur in the
second rootfs installation path. The existing HTTPS-only curl transfer
fallback and signed-package checks remain unchanged. No rolling mirror,
package-version change, keyring bypass, alternate snapshot, CI gate skip,
or unsafe retry of an installation is permitted.

Offline contract tests explicitly check the ordered, reviewed hosts and
their presence in both build stages. They cannot prove endpoint availability.
**Only full fixture-free/QA ISO builds and QEMU boot/recovery checks establish
real qualification.** A network failure still holds the release gate.

## Follow-up: dated repository DB succeeds, package blobs return 404

The exact-head PR #425 qualification at `9b5df90` reached Umeå's
`/repos/2026/09/30/core/os/x86_64/core.db`, but received HTTP 404
for the pinned `glibc-2.44+r50+g1848099f063e-1`,
`coreutils-9.12-2` and `pcre2-10.49-1` package blobs in that
same directory. The second original archive host timed out. No image
was built or installed.

Public indexes of the reviewed Umeå Arch Linux Archive confirm that
the historical `/repos/YYYY/MM/DD` directory contains snapshot
repository databases while the exact signed versioned packages also
exist under `/packages/<initial>/<package-name>/<filename>`.
The specific missing `glibc`, `coreutils` and `pcre2` files and
their detached signatures appear in those historical package indexes.

A new `archive-package-fetch.sh` is used ONLY by pacman during
download-only retries. It validates that the request starts from
exactly one of two reviewed HTTPS archive origins and the **date
from release.json**. Metadata stays on dated repository URLs.
For the pinned package filename, it fetches the **exact identical
version** from the historical archive's package pool, with an
ordered fallback between the same two approved archive hosts.
An external fetch never marks a package installed: pacman continues
to validate its signatures/hashes and its single-shot package install
remains unchanged. A separate temporary destination per origin
prevents mixing partial byte ranges.

The Archiso profile's own download-only cache prefetch is given the
same fallback on attempts 2–3. Its actual mkarchiso installation
keeps the original profile; no unpinned current mirrors, changed
signing keys, signature bypass, altered release pins, skipped VM
qualification, or automatic release are introduced.

**Acceptance:** the offline routing/refusal regression suite and
the full exact-head image/QEMU tests must pass separately. No archive
availability or ISO readiness is claimed from mock tests alone.

### Accepted ALPM epoch characters after first live cache prefetch

In the following exact-head run, the **initial frozen upgrade passed**
with keyring and package-integrity checks; the 318-package builder prefetch
then failed because some source package filenames include an ALPM numeric
epoch (for example `libpipewire-1:1.6.9-1`). The transport allowlist
rejected the colon, including pacman's percent-encoded `%3A` form.
The archive's `/packages/l/libpipewire/` index confirms this exact
epoch-versioned package and signature.

The next patch accepts only literal colons/plus signs and their exact
`%3A`/`%2B` URL encoding in an otherwise strict source filename.
Encoded slashes, path traversal, unapproved URLs, hosts and snapshot dates
are still refused. Offline tests cover both epoch variants and rejection
of encoded slashes. No package version is changed and pacman's signature
verification remains authoritative.
