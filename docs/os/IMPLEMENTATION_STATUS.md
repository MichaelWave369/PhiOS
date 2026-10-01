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
| R8: Whole-OS update and recovery | Explicit public-key enrollment, signed verifier, staged package application and matched root/EFI checkpoints | Full 2,218-test CI and bounded end-to-end VM run 36805999628 passed: valid update, invalid/cancelled/replayed/dependency refusal, abrupt termination during a real package hook, unchanged active system, deliberate kernel boot failure, matched live recovery and three password-authenticated disk-only boots; arbitrary transitions and hardware remain unqualified |
| R9: Qualify hardware and one Linux governed workflow | Pending | Named hardware matrix and observed effect verification |
| R10: Sign and publish the exact qualified artifact | Exact native/Python/npm inventory, supplier license notices, CycloneDX SBOM and source/ISO/artifact provenance; fixture-free build/normal PAM qualification workflow | Eight focused inventory/refusal tests and validation against pinned official CycloneDX 1.6 schemas passed locally; actual image/VM CI pending; third-party source/license review, release identity, signatures and maintainer publication remain held |

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

These are bounded VM qualifications. The later bounded update/recovery qualification is recorded below. Physical power loss, Linux governed effects, named hardware support and signed public release remain held. No adapter is promoted and no publication authority follows from the receipts.

## Signed update and matched recovery VM evidence

Image run [36805999628](https://github.com/MichaelWave369/PhiOS/actions/runs/36805999628) passed for source `29def30a3079c99972f1606ae44ea3478d0f79d1`, ISO SHA-256 `391efdfd41e0217706b2b4028c47e9d37f7014762afc5d6831a30eb6bb2dba4b`. The disposable 32-GiB disk, two CPUs, 4 GiB RAM, UEFI/KVM, no network/host disks/shared folders and CI-only fixture bounds are unchanged. Production public-key enrollment cancellation and acceptance passed with an ephemeral test key. A real signed package was installed; missing/wrong-key/tampered/expired/replayed bundles, cancellation and a real dependency failure were refused. Abrupt termination occurred inside a real pacman installation hook; a second live boot verified the retained interrupted stage and unchanged active root, EFI and counter.

Three distinct password/PAM and greetd disk-only desktop boots passed. After deliberate default/fallback initramfs corruption, the kernel actually panicked because it could not mount its root. Explicit live-media recovery restored the matched root/EFI checkpoint, removed the added test package and rolled-back signing trust, advanced the independent generation to two, and preserved the canonical data/acknowledged receipt hash. Root/EFI switching remains non-atomic. The successful added-package fixture does not qualify arbitrary kernel upgrades or an actual future signed release transition.

Receipt: `docs/os/evidence/recovery-29def30a.json`. [Logs/screenshots](https://github.com/MichaelWave369/PhiOS/actions/runs/36805999628/artifacts/11137448503) and [unsigned QA image/packages](https://github.com/MichaelWave369/PhiOS/actions/runs/36805999628/artifacts/11137807998) expire 2026-10-08. The recovered desktop screenshot was visually inspected. Ordinary CI [36805999618](https://github.com/MichaelWave369/PhiOS/actions/runs/36805999618) passed 2,218 tests with six existing optional skips, including eight actual signature/expiry/revocation cases and four actual enrollment cases. All four prior failures remain in `docs/os/evidence/recovery-attempts.json`. Real hardware, fixture-free exact release-artifact qualification, source/license completion and maintainer signing/publication remain held; no adapter or execution authority is promoted.
