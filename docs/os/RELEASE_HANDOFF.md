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
| Reviewed branch head | `0ea1fced470abf75701a4cad8f806551078b1b76` |
| Tested prospective merge source | `5145b4dabd0e70d4b8d35691041a4d9f797affe9` |
| Identical source tree | `59ec972739f5293bb3de57d7369892b98b68c4b3` |
| Normal ISO SHA-256 | `e60b64623a0008b27439f98eacd22cc9d4e0ce714d4b7b8684276f425988349b` |
| First-party source archive SHA-256 | `19a5f6e6a51242d9d7e989b7e6579c95b3cbe5778ac39b643380876240eb5911` |
| Normal image qualification | [36812104386](https://github.com/MichaelWave369/PhiOS/actions/runs/36812104386) |
| Download normal ISO and payloads | [11140626238](https://github.com/MichaelWave369/PhiOS/actions/runs/36812104386/artifacts/11140626238) |
| Compact evidence | [11140895800](https://github.com/MichaelWave369/PhiOS/actions/runs/36812104386/artifacts/11140895800) |
| Persisted receipt | [normal-installed-5145b4da.json](evidence/normal-installed-5145b4da.json) |

These unsigned review downloads expire **2026-10-08**. A later build, branch
update, final merge or tag has a separate identity. Download the normal payload,
verify its complete ISO/source/artifact hashes against SHA256SUMS and provenance,
and retain the receipts with that exact build. The separate QA image contains
test fixtures and is not the physical observation candidate.

## Ordered code review

Review and merge only in stack order after assessing each stated boundary:

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

The aggregate gate passed all nine jobs in run 36816117488 for source
`5a1431f4758029a9c04abfb5471351e9abf88a3f`, with 2,279 Python tests passed and
six existing optional skips. Its actual normal and signed QA scopes and exact
hashes are in `evidence/qualification-gate-5a1431f4.json`. The later desktop
candidate has a different source/artifact and its own pending qualification.
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
   software rendering in QEMU. Audio/session locking/Wi-Fi configuration are
   presently unqualified features; resolve observations and requalify changed
   artifacts before promising them. Preserve Windows and its independent backup.
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
