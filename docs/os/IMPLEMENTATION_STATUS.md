# Linux OS implementation register

Controlling input: the operator-approved *PhiOS OS Release Audit and Plan*,
2026-09-30, SHA-256 `aba53c05f18ac2f874236a1b6566b74096eabff9422e9e0fee0b5da54b54a676`, audited source `dad7a7d7cd53874926ad366f19d3fc0fa6b99a49`.
This register tracks candidate implementation, not permission to publish or
proof that PhiOS is a completed OS. Preserve the repository AGENTS.md rules.

| Requirement | Candidate change | Evidence / remaining gate |
| --- | --- | --- |
| R1: HTTP callers cannot mint operator authority | Decision, binding and lease POSTs held; explicit terminal review | HTTP rejection, cancellation and stale-review tests; same-user isolation and Windows ACL evidence remain required |
| R2: Freeze a truthful Linux release contract | Candidate contract and generated metadata corrected | docs/os/RELEASE_CONTRACT.md and packaging/linux/release.json; Python and OS release tracks separate |
| R3: Install current Python and UI packages | Current-source PKGBUILDs, JS lock and native pacman adapter | Pinned Arch image package/install smoke passed in runs 36786368318 and 36798467774; signed upstream inputs; local development packages unsigned |
| R4: Real non-root graphical login and supervised services | Wayfire session and user service target | Run 36798467774 passed real live/installed login, observer/browser readiness, sidecar restart and logout; no privileged browser or agent auto-start |
| R5: Produce and UEFI boot exact live ISO | Isolated Archiso/QEMU workflow | Exact source 0253b6e0fb27251fe2da37b6d8c1e31245a64290 and ISO SHA-256 recorded below; live lifecycle and two distinct boots passed |
| R6: Recover durable private state | Locking/sync, transactional outbox and data-only recovery | Contention, interruption, backup/restore and schema refusal tests; installed acknowledged state survived abrupt VM restart in 36798467774; physical power-loss qualification pending |
| R7: Explicit blank-disk installation | Experimental root-owned offline CLI and disposable qualification lane | 20 local refusal/cancellation/identity tests; cancellation, actual installation, no-ISO desktop boot and fresh data restoration passed on the named disposable VM; hardware beta pending |
| R8: Whole-OS update and recovery | Candidate pinned signed transition verifier and offline matched root/EFI checkpoints | 45 local transition/recovery refusal checks; six real-signature cases passed in CI 36797267222 (that run separately failed an fsync-test deadline, preserved and repaired); deliberate unbootable-root recovery VM qualification and signed package application pending |
| R9: Qualify hardware and one Linux governed workflow | Pending | Named hardware matrix and observed effect verification |
| R10: Sign and publish the exact qualified artifact | Held | Proven preceding gates, hashes, SBOM, signatures, source/license notices and maintainer release decision |

## First builder handoff

The approval boundary is a bounded candidate repair. Core normalized
contracts, adapter selection, advisory rollout behavior and private PhiKernel
internals remain untouched. Existing terminal services perform each stage
separately; no capability payload or lease lifetime is selected by the CLI.

Focused security tests and Python lint/type checks are required before review.
The full existing suite must also run in GitHub CI: the local execution host
restricts AF_UNIX, network enumeration and bubblewrap preflight. Environment
failures must be preserved and reported separately, never silently skipped to
claim a pass. Reviewers should rerun the boundary tests and assess the stated
same-user trust limitation before merging. Later milestones must update this
register with actual artifact identities and evidence, rather than readiness
percentages or forecast dates.

Validation: 73 focused Python tests passed; Ruff and mypy (301 source files) passed. PhiShell production build and 12 targeted HTTP boundary/proposal tests passed. Full PhiShell TypeScript suite passed; three existing Node integration tests fail on this host due to restricted network enumeration and absent systemd, as recorded in the audit. GitHub CI remains the required full-platform check.

## Linux foundation handoff

The candidate implements release-contract, package, session and live-image build milestones. 85 focused Python release/desktop/profile tests, lint and types pass locally. PhiShell build and the Arch inventory/security transport tests pass. Image run [36786368318](https://github.com/MichaelWave369/PhiOS/actions/runs/36786368318) qualified the live lifecycle for source `5339f180ad9f8dbac11906c5e962728f80853e91`, ISO SHA-256 `5f3eacd5ce24c6cb8ea0067aad23054f5ca33caa146c5600eb4d625942c049ca`. Root autologin and unrelated releng services are removed. The CI-only qualification fixture is excluded from normal local previews.

## Installed VM evidence

Image run [36798467774](https://github.com/MichaelWave369/PhiOS/actions/runs/36798467774) passed for source `0253b6e0fb27251fe2da37b6d8c1e31245a64290`, ISO SHA-256 `8599bbc7ff2ed35432bae23692464d4d5afa9ffdfc787699a7be88f2cfc62f5c`. A newly created 32-GiB disk, serial `PHIOS_CI_BLANK`, was the only target. The VM had x64 UEFI/KVM, two CPUs, 4 GiB RAM, no network or shared folders, and no attached host disk. Cancellation preserved the blank target; production installation, normal password/PAM and greetd logins, the actual Wayfire/PhiShell desktop, verified backup/fresh restore, and acknowledged state after abrupt virtual restart passed. Installed boot IDs were `e5ba8528af464b8192312d9aab0db869` and `caa9695c41c64c3d898e12c1bd3234f5`.

Evidence receipt: `docs/os/evidence/installation-0253b6e0.json`. [Reviewable logs and screenshots](https://github.com/MichaelWave369/PhiOS/actions/runs/36798467774/artifacts/11135321615) and [unsigned image/packages](https://github.com/MichaelWave369/PhiOS/actions/runs/36798467774/artifacts/11134958214) expire 2026-10-08 under the seven-day CI retention policy. CI-only serial-console injection and public disposable credentials are recorded; they are excluded from normal installations. The screenshot was visually inspected. Ordinary CI runs 36798467750 and 36798463744 also passed for installer head `f135a24d3d88173f611829317e4ad04ebc22eff3`.

These are bounded VM qualifications. Whole-OS updates/recovery, physical power loss, Linux governed effects, named hardware support and signed public release remain held. No adapter is promoted and no publication authority follows from the receipts.
