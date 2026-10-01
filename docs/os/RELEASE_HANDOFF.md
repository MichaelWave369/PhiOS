# PhiOS Linux candidate handoff

Current outcome: an unpublished experimental `0.1.0-alpha.1` Linux distribution
candidate has passed actual UEFI VM live boot, normal non-root desktop lifecycle,
blank-disk installation, durable canonical data/backup/restore, bounded governed
Linux effect and matched root/EFI recovery. A separate QA artifact passed a real
ephemerally signed package transaction, refusals and interruption. Physical
hardware, the final signed transition and distribution delivery remain open.
This is not a supported beta or OS 1.0. Nothing has been merged or published by
this handoff; no private PhiKernel/TIEKAT implementation is needed to boot it.

## Exact candidate for physical observation

| Identity | Value |
| --- | --- |
| Reviewed branch head | `9c98475274442595c59370113b9c1e0dee595ec9` |
| Tested prospective merge source | `a7bcd9863eea12a87c1a9ef1fcbd26211542cd91` |
| Identical source tree | `a85700b2c08e54a066a77a2f4a4db7494b7579ff` |
| Normal ISO SHA-256 | `3b26a7334b36254b4e686843e84924ee14cdb6ef2d6748fd771e09a02e5f79a2` |
| First-party source archive SHA-256 | `41ed0a19a811f7ac6c22edbb555adbc4b55d5421f8ea6b9e73481cd58116d8b7` |
| Normal image qualification | [36823086807](https://github.com/MichaelWave369/PhiOS/actions/runs/36823086807) |
| Download normal ISO and payloads | [11144157950](https://github.com/MichaelWave369/PhiOS/actions/runs/36823086807/artifacts/11144157950) |
| Compact evidence | [11144167873](https://github.com/MichaelWave369/PhiOS/actions/runs/36823086807/artifacts/11144167873) |
| Persisted receipt | [desktop-normal-a7bcd986.json](evidence/desktop-normal-a7bcd986.json) |

These unsigned review downloads expire **2026-10-08**. A later build, branch
update, final merge or tag has a separate identity. Download the normal payload,
verify its complete ISO/source/artifact hashes against SHA256SUMS and provenance,
and retain the receipts with that exact build. The separate QA image contains
test fixtures and is not the physical observation candidate.

## Ordered code review

Review the component PRs in dependency order after assessing each boundary:

| PR | Scope |
| --- | --- |
| [270](https://github.com/MichaelWave369/PhiOS/pull/270) | Browser/operator authority boundary |
| [271](https://github.com/MichaelWave369/PhiOS/pull/271) | Linux contract, packages, non-root desktop and live image |
| [272](https://github.com/MichaelWave369/PhiOS/pull/272) | Private durable state and data-only backup/recovery |
| [273](https://github.com/MichaelWave369/PhiOS/pull/273) | Explicit whole blank-disk installation |
| [274](https://github.com/MichaelWave369/PhiOS/pull/274) | Explicit signing trust, signed package updates and matched root/EFI recovery |
| [275](https://github.com/MichaelWave369/PhiOS/pull/275) | Exact inventories, notices, SBOM/provenance and normal live-image gate |
| [276](https://github.com/MichaelWave369/PhiOS/pull/276) | Restricted Linux proof broker, hardware handoff and bundled frontend inventory |
| [277](https://github.com/MichaelWave369/PhiOS/pull/277) | Exact normal-image installed/recovery gate and explicit serial password login |
| [278](https://github.com/MichaelWave369/PhiOS/pull/278) | Always-reported same-source `release-gate` and reusable qualification jobs |
| [279](https://github.com/MichaelWave369/PhiOS/pull/279) | NetworkManager, user audio, manual PAM locking and their actual desktop probes |

Use the complete main-targeted integration PR as the merge vehicle after its
own exact-source qualification passes. It contains the candidate and aggregate
controller together, so main can require its observed `release-gate` before
integration. The component PRs above remain focused review references. Requiring
`release-gate` on the earlier component heads would leave them pending because
they predate that controller. Keep every merge and release under maintainer review.

The latest aggregate gate passed all nine jobs in
[run 36823086807](https://github.com/MichaelWave369/PhiOS/actions/runs/36823086807)
for source `a7bcd9863eea12a87c1a9ef1fcbd26211542cd91`, with 2,287 Python tests
passed and six existing optional skips. `evidence/qualification-gate-a7bcd986.json`
links the independently hash-checked normal and signed QA receipts. The normal
image has 501 inventoried components and 746 captured supplier notice files.
Virtual DHCP/audio, actual Super+L/PAM lock/refusal/unlock, complete session
shutdown/reauthentication and installed recovery/proof passed. Physical network,
audio, Wi-Fi, GPU and suspend remain unqualified.

The earlier aggregate gate passed all nine jobs in run 36816117488 for source
`5a1431f4758029a9c04abfb5471351e9abf88a3f`, with 2,279 Python tests passed and
six existing optional skips. Its actual normal and signed QA scopes and exact
hashes are in `evidence/qualification-gate-5a1431f4.json`. Each later integration,
documentation commit, main merge or tag has a separate source/artifact identity.
The aggregate normal and QA jobs reuse the existing exact-image procedures. See
BUILD_AND_QUALIFY.md for the `release-gate` required-status handoff.
Review source and tests, not just a green check. Main and OS release-tag protection
still require maintainer configuration. Keep publication separate from the
existing Python `v*`/PyPI workflow. Evidence never promotes an adapter, enrolls a
signing identity or grants execution/publication authority.

Repository protection was rechecked on 2026-10-01. Main still points to
`dad7a7d7cd53874926ad366f19d3fc0fa6b99a49`; its branch response reports no
required checks. The sole active branch ruleset `protec` (13863077) contains
deletion/non-fast-forward rules and no required status or review rule. Configure
the reviewed `release-gate` requirement and main/OS-tag release protections
through maintainer administration before merging/publishing. This candidate
does not claim those settings were applied.

## Remaining work in order

1. **Observe the supplied Skytech on the exact normal live media.** Follow
   HARDWARE_QUALIFICATION.md, initially without installation. Save the read-only
   hardware report plus actual GPU/display/input, network, audio, firmware,
   suspend and shutdown/restart results. RTX 5070 support is not inferred from
   software rendering in QEMU. Virtual audio, restricted DHCP and manual PAM locking passed on this
   candidate; physical audio/network/radio/lock/suspend behavior still requires
   observation. Resolve blockers and requalify changed artifacts before promising them. Preserve Windows and its independent backup.
2. **Qualify installation on a separately identified dedicated empty disk.**
   Review the entire blank target and exact installer phrase. The installer
   supports no dual boot or partition reuse. Prove no-media logins, persistent
   acknowledged data, a separate verified backup, the fixed Linux proof workflow,
   actual signed target transition, interruption and matched recovery. Record
   physical power-loss evidence separately from virtual process termination.
3. **Prepare the actual supported transition and maintainer signing identity.**
   Select the final base/target source and complete package inventories and
   migration policy. Authenticate the maintainer's public key and complete
   fingerprint independently, enroll it explicitly and test the actual signed
   target bundle on the normal base artifact. Never submit a private key to the
   repo, image, test harness or this handoff; the ephemeral QA signer is not a
   release identity. Arbitrary kernel/driver upgrades are not qualified by the
   passed added-package fixture. Preserve failures and successful target hashes.
4. **Complete source and notice delivery for that exact final inventory.**
   Start with source-review.json's component records. Identify applicable terms,
   actual corresponding source and build/patch material where required, custody,
   exact hashes and delivery references. Bundle or accompany the distribution
   with the required materials and notices. Have the release owner review the
   result. Supplier labels, an Arch binary archive link, captured license files
   and valid CycloneDX syntax alone do not complete this gate.
5. **Freeze support scope and qualify final bytes before publication.**
   Record supported machines/features, known issues, maintenance/security update
   and recovery procedures, support contact/owner and the retained evidence.
   Run the package/UI/live/install/recovery gates on the final release source;
   previous PR checks cannot authorize a different final image or transition.
   Sign final SHA256SUMS/provenance externally with the authenticated maintainer
   key and verify the exact signed bytes. After explicit human release-owner
   authorization, publish a prerelease in `phios-linux-v*` with the ISO,
   signatures/public-key verification instructions, inventories/notices/source,
   qualification receipts and support/recovery notes together.

No readiness percentage or forecast date replaces these missing observations.
The requirement register and every generated report continue to distinguish
qualified VM cases from pending physical/signing/delivery work.
