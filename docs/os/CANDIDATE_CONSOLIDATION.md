# PhiOS Linux candidate consolidation

Status: draft integration record. This document does not grant release, signing, merge, publication, hardware-support, or runtime authority.

## Purpose

This branch consolidates the reviewed Linux development-preview stack into one main-targeted candidate so the active PhiOS source of truth no longer depends on a long chain of stacked pull requests.

The candidate preserves the implementation and evidence lineage from the following work:

- #270 operator terminal authority boundary
- #271 Linux release foundation
- #272 durable private state and data-only recovery
- #273 explicit blank-disk installation
- #274 staged signed updates and matched root/EFI recovery
- #275 exact artifact inventory and fixture-free candidate
- #276 bounded Linux governed effect
- #277 fixture-free install/recovery qualification
- #278 aggregate same-source release qualification gate
- #279 desktop network/audio/PAM-lock paths
- #280 main-targeted OS candidate integration
- #281 source/notice delivery verification
- #282 qualification handoff
- #283 VirtualBox cursor/session compatibility
- #285 VirtualBox field evidence
- #286 PhiShell app-entry repair
- #287 launcher field evidence
- #288 NBG-A observation provider
- #289 NBG-A/VirtualBox field evidence
- #290 explicit unseeded application launcher candidate

PR #284 froze the original NBG-A v0.1 public contract on a sibling branch. The reviewed contract/parser work was later incorporated into #288; #284 is retained as historical review evidence rather than a separate integration dependency.

## Integration rule

This consolidation must be qualified as its own exact main-targeted source.

Success of prior stacked branches does not automatically qualify a new prospective merge commit, tag, signed release, or publication artifact.

A successful consolidation gate may establish only that the integrated source satisfies the currently automated qualification scope. It does not change:

- `release_ready=false`
- `publication_authority=false`
- physical hardware qualification
- maintainer signing identity
- third-party source/license review
- final release publication authority

## Cleanup rule

After the consolidation PR itself passes the required same-source gate and is merged to `main`:

1. retain all evidence and failure receipts in the repository;
2. close superseded stacked PRs #270-#290 with a pointer to the consolidation merge;
3. do not delete historical branches merely to make the PR list shorter until the merge identity is preserved;
4. start new feature work from the consolidated `main`, not from an older stack branch.

The first planned post-consolidation product rung is the PhiOS Toolchain Capsule contract for governed, versioned build environments.
