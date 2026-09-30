# Linux OS implementation register

Controlling input: the operator-approved *PhiOS OS Release Audit and Plan*,
2026-09-30, SHA-256 `aba53c05f18ac2f874236a1b6566b74096eabff9422e9e0fee0b5da54b54a676`, audited source `dad7a7d7cd53874926ad366f19d3fc0fa6b99a49`.
This register tracks candidate implementation, not permission to publish or
proof that PhiOS is a completed OS. Preserve the repository AGENTS.md rules.

| Requirement | Candidate change | Evidence / remaining gate |
| --- | --- | --- |
| R1: HTTP callers cannot mint operator authority | Decision, binding and lease POSTs held; explicit terminal review | HTTP rejection, cancellation and stale-review tests; same-user isolation and Windows ACL evidence remain required |
| R2: Freeze a truthful Linux release contract | Candidate contract and generated metadata corrected | docs/os/RELEASE_CONTRACT.md and packaging/linux/release.json; Python and OS release tracks separate |
| R3: Install current Python and UI packages | Candidate PKGBUILDs, JS lock and native pacman adapter | CI must build/install exact source packages; fixed Arch snapshot and signed upstream inputs |
| R4: Real non-root graphical login and supervised services | Candidate Wayfire session and user service target | Live/VM qualification pending; no privileged browser or agent auto-start |
| R5: Produce and UEFI boot exact live ISO | Candidate isolated Archiso/QEMU workflow | Exact ISO/source/hash/serial/screenshot evidence required; no ready claim until observed |
| R6: Recover durable private state | Pending | Concurrent writes, crash recovery, backup/restore, migrations |
| R7: Explicit blank-disk installation | Pending | Disposable VM install, boot without ISO, persistence |
| R8: Whole-OS update and recovery | Pending | Signed artifacts, failed update recovery; app rollback is insufficient |
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

The candidate implements release-contract, package, session and live-image build milestones. 85 focused Python release/desktop/profile tests, lint and types pass locally. PhiShell build and the Arch inventory/security transport tests pass. The CI image workflow must provide the installed-package and actual UEFI boot evidence before these milestones are called qualified. Root autologin and unrelated releng services are removed. The CI-only live qualification fixture is excluded from normal local previews. Installation, durable crash recovery, OS update/rollback, Linux effect execution, hardware beta and signed public release remain held; no code or evidence in this milestone grants those claims.
