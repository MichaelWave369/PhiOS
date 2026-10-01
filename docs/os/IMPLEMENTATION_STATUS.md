# Linux OS implementation register

Controlling input: the operator-approved *PhiOS OS Release Audit and Plan*,
2026-09-30, SHA-256 `aba53c05f18ac2f874236a1b6566b74096eabff9422e9e0fee0b5da54b54a676`, audited source `dad7a7d7cd53874926ad366f19d3fc0fa6b99a49`.
This register tracks candidate implementation, not permission to publish or
proof that PhiOS is a completed OS. Preserve the repository AGENTS.md rules.

| Requirement | Candidate change | Evidence / remaining gate |
| --- | --- | --- |
| R1: HTTP callers cannot mint operator authority | Decision, binding and lease POSTs held; explicit terminal review | HTTP rejection, cancellation and stale-review tests; installed UID-separated fixed proof passed. Arbitrary same-UID administrator isolation is outside this claim; Windows qualification remains separate |
| R2: Freeze a truthful Linux release contract | Candidate contract and generated metadata corrected | docs/os/RELEASE_CONTRACT.md and packaging/linux/release.json; Python and OS release tracks separate |
| R3: Install current Python and UI packages | Current-source PKGBUILDs, JS lock, native pacman adapter, NetworkManager and user audio/PAM lock stack | Exact normal and QA image package/install gates passed in 36823086807; signed pinned upstream inputs; local development packages remain unsigned |
| R4: Real non-root graphical login and supervised services | Wayfire and user services, audio/session cleanup, manual PAM lock and ordinary PolicyKit agent | 36823086807 passed live/installed PAM desktop, sidecar restart, all 13 units inactive at logout, service/audio/network reauthentication and lock/wrong/correct-password cases; physical and specific graphical administration tests remain separate |
| R5: Produce and UEFI boot exact live ISO | Isolated Archiso/QEMU workflow | Exact normal source/tree/ISO hashes in desktop-normal-a7bcd986.json; two distinct live boots and three no-ISO installed boots passed; no physical support inference |
| R6: Recover durable private state | Locking/sync, transactional outbox and data-only recovery | Contention, interruption, backup/restore and schema refusal tests; installed acknowledged state survived abrupt VM restart in 36798467774; physical power-loss qualification pending |
| R7: Explicit blank-disk installation | Experimental root-owned offline CLI and disposable qualification lane | 20 local refusal/cancellation/identity tests; cancellation, actual installation, no-ISO desktop boot and fresh data restoration passed on the named disposable VM; hardware beta pending |
| R8: Whole-OS update and recovery | Explicit public-key enrollment, signed verifier, staged package application and matched root/EFI checkpoints | Full 2,218-test CI and bounded end-to-end VM run 36805999628 passed: valid update, invalid/cancelled/replayed/dependency refusal, abrupt termination during a real package hook, unchanged active system, deliberate kernel boot failure, matched live recovery and three password-authenticated disk-only boots; arbitrary transitions and hardware remain unqualified |
| R9: Qualify hardware and one Linux governed workflow | UID-separated installed-only proof-note broker, canonical bound single-use lease, independent protected ledger and read-only hardware collector/protocol | 21 focused tests and actual sudo/PAM/UID 1001 proof, cancellation, denial, replay, expiry and historical-authority refusal after restart/recovery passed on the exact normal ISO in run 36812104386; supplied Skytech target remains physically unqualified |
| R10: Sign and publish the exact qualified artifact | Actual native/Python/npm and bundled frontend inventory, supplier notices, CycloneDX SBOM and exact source/ISO/artifact provenance | 11 focused inventory/refusal tests, pinned CycloneDX schema validation and exact fixture-free live/install/state/recovery VM qualification passed in run 36812104386; final signed transition, hardware, source/license delivery, release identity and publication remain held |

## Latest desktop and aggregate qualification

[Run 36823086807](https://github.com/MichaelWave369/PhiOS/actions/runs/36823086807)
passed all nine jobs for source `a7bcd9863eea12a87c1a9ef1fcbd26211542cd91`,
the same tree as reviewed code head `9c98475274442595c59370113b9c1e0dee595ec9`.
Full Python CI passed 2,287 tests with six existing optional skips, Ruff and
mypy (304 source files); wheel/vector/ledger/PhiShell jobs passed. The normal
ISO repeated installed data/proof/recovery and added restricted DHCP, synthetic
HDA/user PCM, non-root PolicyKit startup, actual Super+L and PAM password
refusal/unlock, complete session shutdown and audio/network reauthentication.
The separate QA artifact repeated signed-package/refusal/interruption/recovery
with an ephemeral test signer and its own different ISO.

`evidence/qualification-gate-a7bcd986.json` links the normal and signed receipts
and their hashes. The normal inventory has 501 components and 746 captured
notice files; the QA inventory has 502 components. Both compact archive hashes,
15 checksum payloads per archive and available provenance sidecars were checked.
Actual lock/refusal, restored desktop and failed-kernel-boot screenshots were
inspected. Large payload hashes remain the producer's hashes; the ISO/source/
package/notice archives were not redownloaded into the review host. The earlier
failed DHCP expectations, captured nmcli parsing regression, Arch download
failure and aggregate holds remain in `evidence/desktop-attempts.json`.

Later integration/documentation/main/tag identities require their own checks.
The complete main-targeted integration includes the qualification controller;
earlier component heads predate that status and remain focused review references.
Physical hardware, the actual authenticated maintainer-signed transition,
source/license delivery, repository protection and publication remain open.
`release_ready` and publication authority remain false.

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

These are bounded VM qualifications. Later update/recovery and Linux proof qualifications are recorded below. Physical power loss, named hardware support and signed public release remain held. No adapter is promoted and no publication authority follows from the receipts.

## Signed update and matched recovery VM evidence

Image run [36805999628](https://github.com/MichaelWave369/PhiOS/actions/runs/36805999628) passed for source `29def30a3079c99972f1606ae44ea3478d0f79d1`, ISO SHA-256 `391efdfd41e0217706b2b4028c47e9d37f7014762afc5d6831a30eb6bb2dba4b`. The disposable 32-GiB disk, two CPUs, 4 GiB RAM, UEFI/KVM, no network/host disks/shared folders and CI-only fixture bounds are unchanged. Production public-key enrollment cancellation and acceptance passed with an ephemeral test key. A real signed package was installed; missing/wrong-key/tampered/expired/replayed bundles, cancellation and a real dependency failure were refused. Abrupt termination occurred inside a real pacman installation hook; a second live boot verified the retained interrupted stage and unchanged active root, EFI and counter.

Three distinct password/PAM and greetd disk-only desktop boots passed. After deliberate default/fallback initramfs corruption, the kernel actually panicked because it could not mount its root. Explicit live-media recovery restored the matched root/EFI checkpoint, removed the added test package and rolled-back signing trust, advanced the independent generation to two, and preserved the canonical data/acknowledged receipt hash. Root/EFI switching remains non-atomic. The successful added-package fixture does not qualify arbitrary kernel upgrades or an actual future signed release transition.

Receipt: `docs/os/evidence/recovery-29def30a.json`. [Logs/screenshots](https://github.com/MichaelWave369/PhiOS/actions/runs/36805999628/artifacts/11137448503) and [unsigned QA image/packages](https://github.com/MichaelWave369/PhiOS/actions/runs/36805999628/artifacts/11137807998) expire 2026-10-08. The recovered desktop screenshot was visually inspected. Ordinary CI [36805999618](https://github.com/MichaelWave369/PhiOS/actions/runs/36805999618) passed 2,218 tests with six existing optional skips, including eight actual signature/expiry/revocation cases and four actual enrollment cases. All four prior failures remain in `docs/os/evidence/recovery-attempts.json`. Later exact normal-image evidence is below; physical hardware, the final signed transition, source/license delivery and maintainer signing/publication remain held.

## Exact normal-image and Linux workflow qualification

[Run 36812104386](https://github.com/MichaelWave369/PhiOS/actions/runs/36812104386)
passed for checked-out source `5145b4dabd0e70d4b8d35691041a4d9f797affe9`,
ISO SHA-256 `e60b64623a0008b27439f98eacd22cc9d4e0ce714d4b7b8684276f425988349b`.
This prospective PR merge commit has the same tree as reviewed branch head
`0ea1fced470abf75701a4cad8f806551078b1b76`. This is the normal image, with no
image QA fixtures, test package, enrolled PhiOS trust or installed live password.
The external probes run through ordinary terminals and are excluded from the ISO.

Two distinct live boots passed normal PAM/greetd login, actual non-root desktop
and observations, sidecar restart, logout cleanup and reauthentication. The same
ISO then passed cancellation and blank-disk installation through the public live
user's narrow maintenance sudo. The installer explicitly reviewed its standard
serial password/PAM option; there was no privileged console injection. Three
distinct disk-only PAM/greetd desktop boots passed canonical data/backup/fresh
restore, acknowledged data after abrupt VM termination, deliberate default and
fallback initramfs failure, actual failed boot and matched root/EFI recovery
through the same normal live image. Root/EFI recovery remains non-atomic.

The actual installed UID 1001 proposer and password-authenticated UID 1000
operator passed protected-store/broker permission denial, cancellation, exact
single-use approval/binding/lease, one fixed 57-byte note and independent readback,
replay refusal and real expiry. Old approvals remained inactive after reboot and
matched OS recovery. This qualifies only the fixed broker effect, not generic
desktop automation, malicious administrator/root isolation or Windows Ghost Walk.

The actual final image inventories contain 386 native, 39 Python, 12 installed
npm and four bundled frontend origin records: 441 CycloneDX components. Bundled
React, ReactDOM, Scheduler and Vite's injected helper are included, even when
already represented by a separate installed origin. There are 620 captured
supplier notice files. Labels/notices do not establish source/license compliance.

Receipt: `docs/os/evidence/normal-installed-5145b4da.json`.
[Unsigned exact normal image and payloads](https://github.com/MichaelWave369/PhiOS/actions/runs/36812104386/artifacts/11140626238)
and [compact logs/screenshots/inventories](https://github.com/MichaelWave369/PhiOS/actions/runs/36812104386/artifacts/11140895800)
expire 2026-10-08. The recovered desktop screenshot was visually inspected;
downloaded compact payload hashes were checked against provenance and SHA256SUMS.
The large ISO/source/package archives were not downloaded again into the review
host; their hashes are the producer's recorded hashes.

The separate QA [run 36812104411](https://github.com/MichaelWave369/PhiOS/actions/runs/36812104411)
also passed the signed-package addition/refusals/interruption and matched recovery
at the same source, with ephemeral test identity and its own different ISO hash.
Receipt: `docs/os/evidence/signed-proof-5145b4da.json`. Its qualification cannot
substitute for a real future maintainer-signed transition on the normal artifact.
Ordinary [CI 36812078517](https://github.com/MichaelWave369/PhiOS/actions/runs/36812078517)
passed 2,250 tests with six existing optional skips, Ruff and mypy (304 source
files); PhiShell CI also passed. The previous schema-validator and external
probe failures remain in `fixture-free-attempts.json` and `linux-proof-attempts.json`.

These receipts identify tested bytes, not every later documentation commit or
final merge/tag. Requalify the final publication source and signed transition.
See RELEASE_HANDOFF.md for the ordered review and remaining physical/signing/
source-delivery work. `release_ready` remains false.
