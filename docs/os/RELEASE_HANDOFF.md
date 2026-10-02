# PhiOS Linux candidate handoff

Current outcome: an unpublished experimental `0.1.0-alpha.1` Linux distribution
candidate has passed actual UEFI VM live boot, normal non-root desktop lifecycle,
blank-disk installation, durable canonical data/backup/restore, bounded governed
Linux effect and matched root/EFI recovery. A separate QA artifact passed a real
ephemerally signed package transaction, refusals and interruption. Physical
hardware, the final signed transition and distribution delivery remain open.
This is not a supported beta or OS 1.0. Nothing has been merged or published by
this handoff; no private PhiKernel/TIEKAT implementation is needed to boot it.

## Exact qualified observation candidate and local field result

| Identity | Value |
| --- | --- |
| Reviewed code PR/head | [288](https://github.com/MichaelWave369/PhiOS/pull/288), `57666cc68fcf8a5ff4c92e0b0548ab6632534061` |
| Tested prospective source / identical tree | `a44dd077e70d853cef24a30258c2734f48fcfad3` / `ad830c4434b3e85736258774b6e0bbc9d2023976` |
| Normal ISO SHA-256 / bytes | `0e68508d052c08489dfa693b2294dd75343123b33abf2e67c9a729a3e0de0aa6` / 1,802,334,208 |
| Original qualification | [36966541666](https://github.com/MichaelWave369/PhiOS/actions/runs/36966541666), attempt 1, all nine jobs successful |
| Normal ISO/payloads | [11210343338](https://github.com/MichaelWave369/PhiOS/actions/runs/36966541666/artifacts/11210343338), expires 2026-10-09 UTC |
| Normal compact evidence | [11210248671](https://github.com/MichaelWave369/PhiOS/actions/runs/36966541666/artifacts/11210248671), ZIP SHA-256 `178a69ce18ed296e51be1684764238844aed00686c974f8d180d35b152a19f59` |
| Separate QA ISO SHA-256 | `e7aff49826fe116dd85343a8a82598c0cf71dab6132a2829e68e85508e934680` |
| Separate QA compact evidence | [11209989491](https://github.com/MichaelWave369/PhiOS/actions/runs/36966541666/artifacts/11209989491), ZIP SHA-256 `96a0e55d9d5acdfb31c65f46da1992dcd531c9a3ae546882ca8945c1723b092f` |
| Owner-local field receipt | [virtualbox-field-a44dd077.json](evidence/virtualbox-field-a44dd077.json) |

The offline reader returns normalized historical observations only; Bubble Zero
and the canonical-history backend remain unavailable. PhiOS stays `1.0.0` with
Arch package revision 2, PhiShell stays `0.16.0-4`, and the distribution remains
experimental `0.1.0-alpha.1`. The original run passed 2,437 Python tests with six
existing optional skips, Ruff/mypy (306 files), wheel/vector/ledger and 197
frontend/host tests. Normal/QA live/installed probes supplied ten ordinary-user
reader/tamper-refusal pairs; these are repeated service checks, not ten distinct
boots. Original compact evidence/provenance was reviewed independently; large
ISO/package/source/notice payload hashes remain producer observations.

The owner supplied `PhiOS-PR288-test-report.md` and two JSON files for separate
VM `PhiOS-PR288`, VirtualBox `7.2.20r175154`. The report's before-boot ISO digest,
size and guest source match the exact normal provenance above. Automatic
desktop/Waybar/cursor/clicks, reader/repeatability/immutability/refusals, actual
lock/wrong-password/same-session unlock and full ACPI shutdown/cold start passed
as reported. Both user and system failed-unit lists were empty. **Launcher
regression is PARTIAL FAIL:** Super+Space reportedly inserts literal `drun` and
requires Ctrl+A before `chromium`, initially and after cold boot. Reality Ledger
opens with its backend unavailable. The transient `vmwgfx` warning is retained.

This review hashed all three supplied files and reproduced both JSON attachments
byte for byte from the pinned packet. The report explicitly says the JSON was
regenerated on the Windows host after guest validation because TCP/serial export
failed. These are not raw guest captures. The cited screenshots and separate raw
guest logs were not supplied here; this review did not operate the owner's VM
or independently hash its Windows ISO. Guest interactions remain reported field
evidence. Repeated historical output after boot is not memory reconstruction.

The narrow remaining launcher observation is documented in DESKTOP_OPERATION.md.
No runtime, packet, code pin, package revision or authority changes accompany
this field record. The exact tested #288 bytes and every earlier receipt remain
unchanged. This documentation continuation qualifies no replacement ISO;
`publication_authority=false`, `release_ready=false`, and physical/signing/source
delivery qualification remain separate. Nothing is merged, tagged or published.

## Preceding qualified launcher candidate and local field result

| Identity | Value |
| --- | --- |
| Reviewed code PR/head | [286](https://github.com/MichaelWave369/PhiOS/pull/286), `ff05e82d80b5cfb6c1699c57e3d6e2aff0daaaf8` |
| Tested prospective merge source | `0f17bac1ed22bb21374c5471bef32e5e099f5845` |
| Identical source tree | `5a64718e021156c068771da1ebb0b27abf12cdc5` |
| Normal ISO SHA-256 / bytes | `8635a5f1277ca01ef7174b6e3b325e3cf9e972572070eb84d7395b9cec3dcd08` / 1,802,309,632 |
| Exact-source qualification | [36939975061](https://github.com/MichaelWave369/PhiOS/actions/runs/36939975061), attempt 1 |
| Download normal ISO and payloads | [11199488836](https://github.com/MichaelWave369/PhiOS/actions/runs/36939975061/artifacts/11199488836) |
| Normal compact evidence | [11199553909](https://github.com/MichaelWave369/PhiOS/actions/runs/36939975061/artifacts/11199553909), ZIP SHA-256 `90b423de52af7a843476345ae3c8be1a2894db6c9c578f28e925f4cdf51f0400` |
| Separate QA ISO SHA-256 | `13860c836c931daad4bc2c7575e4ba66c100004798cc420a670ea298e27b33a2` |
| Separate QA compact evidence | [11200063827](https://github.com/MichaelWave369/PhiOS/actions/runs/36939975061/artifacts/11200063827), ZIP SHA-256 `5b2595ab1e9438c63834e1ad3ee086ce1f705a3e6086ab562916593869343767` |
| Owner-local report and screenshot receipt | [virtualbox-field-0f17bac1.json](evidence/virtualbox-field-0f17bac1.json) |

These unpublished unsigned review artifacts expire **2026-10-08**. The launcher
repair opens/restores/focuses existing tool windows and explains missing
integrations without adding process-launch authority or installing runtimes.
The OS remains experimental `0.1.0-alpha.1`; PhiShell remains `0.16.0` with Arch
package revision 4. Full availability is described in
[APP_AVAILABILITY.md](APP_AVAILABILITY.md).

All nine original qualification jobs passed: 2,358 Python tests with six
existing optional skips, Ruff/mypy, wheel/vector/ledger checks, and 91 frontend
plus 106 host tests. The normal ISO repeated two real live PAM desktop boots,
two active-session rebinding checks, lock/refusal/unlock and logout/login, then
three disk-only installed/data/proof/recovery boots. The separate QA ISO passed
its ephemeral test-signed package/refusal/interruption/recovery scope. Both
compact ZIP digests and their retained available file/checksum/provenance
records were independently reviewed. Large ISO/package/source/notice payloads
were not downloaded again here; their hashes remain producer observations.

On 2026-10-01 the owner supplied a local GPT-5.6 report for separate VM
`PhiOS-PR286`, with VirtualBox `7.2.20r175154`. The reported before-boot ISO hash
matches this exact normal provenance. Automatic desktop/Waybar/cursor startup,
Apps/Home/Start/search, System Inspector/Reality Ledger/ΦDream/Builder window
lifecycles and Chromium/Foot shortcuts passed before and after a full ACPI
shutdown/cold start. Existing VMs were preserved. This review hashed the report
and two screenshots and inspected their visible states; it did not operate the
owner's VM or independently hash its Windows ISO. Interaction results remain
the local tester's reported evidence.

The supplied older extraction failed the #286 hash check and was not booted;
the matching image was located under `36939975061-attempt-1`. Wofi required
replacing literal `drun` with `Chromium` on both launcher uses. These observations
are preserved. Reality Ledger opened, while the screenshot honestly reports its
canonical-history backend as unavailable. External runtimes/model inference,
VirtualBox lock/refusal/unlock, installation/recovery, physical Skytech/RTX 5070,
actual maintainer signing and source/license delivery remain separate. The
earlier #283 blank lock-screen observation is unresolved.

This evidence-only continuation is a different source identity and qualifies
no replacement ISO. It preserves #286, #283 and all earlier qualification/failure
receipts. The aggregate receipts retain `publication_authority=false` and
`release_ready=false`; no merge, tag or publication is authorized by this report.

## Preceding qualified compatibility candidate (identity retained)

| Identity | Value |
| --- | --- |
| Reviewed code PR/head | [283](https://github.com/MichaelWave369/PhiOS/pull/283), `d1a4a2bc515907d1011b6aa1c2a203acc200cad8` |
| Tested prospective merge source | `9510024d06d822729bd98579fefb6644ca0498c0` |
| Identical source tree | `0dd0e998671105174b4bf2918a00ca06ac68f44a` |
| Normal ISO SHA-256 | `33bfb34251d7f65abe7f8a9d600c21794d051640a305d50c1bca9b21364c2c68` |
| Exact-source qualification | [36916494462](https://github.com/MichaelWave369/PhiOS/actions/runs/36916494462), attempt 1 |
| Download normal ISO and payloads | [11191052839](https://github.com/MichaelWave369/PhiOS/actions/runs/36916494462/artifacts/11191052839) |
| Normal compact evidence | [11191232645](https://github.com/MichaelWave369/PhiOS/actions/runs/36916494462/artifacts/11191232645), ZIP SHA-256 `1fd270906735df097194500dc13d01047a98529f3278c05858731b23bb8cd2d6` |
| Separate QA compact evidence | [11190712079](https://github.com/MichaelWave369/PhiOS/actions/runs/36916494462/artifacts/11190712079), ZIP SHA-256 `a2df96771ec0af3825ee49ef2be2701948bcd8923184f3cdc38d6fc9db04cb5a` |
| Owner-supplied VirtualBox field receipt | [virtualbox-field-9510024d.json](evidence/virtualbox-field-9510024d.json) |

These unsigned review artifacts expire **2026-10-08**. The exact normal ISO passed
the existing automated live/install/recovery qualification plus the new active
Wayland session rebinding probes. The owner subsequently supplied a local
VirtualBox report recording the before-boot full ISO hash match, automatic
cursor/session startup and a full cold power cycle without manual exports or
target restarts. This review hashed the report text and checked its source/ISO
binding against retained normal provenance; it did not operate the owner's VM,
independently hash that local ISO or acquire its raw logs/screenshots.

The reported Super+L blank-screen observation remains unresolved: VirtualBox
wrong-password refusal and PAM unlock were not tested. ACPI shutdown succeeded;
the reported refused `sudo poweroff` did not test the documented guest logind
path. Exact VirtualBox version, VirtualBox installation, physical Skytech/RTX
5070, actual maintainer signing and source/license delivery remain separate.
The field evidence is bounded compatibility evidence, not release authorization.
This documentation continuation is a different source identity and qualifies
no replacement ISO. Preserve #283's qualified head, source and artifact bytes.

## Preceding source-delivery candidate (identity retained)

| Identity | Value |
| --- | --- |
| Reviewed code PR/head | [281](https://github.com/MichaelWave369/PhiOS/pull/281), `3d282bdd6466052def8e632245f312863040cafc` |
| Tested prospective merge source | `1c16c4732442d69d2c7b5763212f1977860a15ae` |
| Identical source tree | `0ccf3ccc589e0bad79e9917f2c01818772926ee1` |
| Normal ISO SHA-256 | `376fd601f66b13dccd6a08644a7b807129f315882d355fd376d0934a80ae29aa` |
| First-party source archive SHA-256 | `0a2a58aa9ce77e369435e731510859cdee7fc820a9f2333e308441013faf42ec` |
| Normal image qualification | [36832501182](https://github.com/MichaelWave369/PhiOS/actions/runs/36832501182) |
| Download normal ISO and payloads | [11147798040](https://github.com/MichaelWave369/PhiOS/actions/runs/36832501182/artifacts/11147798040) |
| Compact evidence | [11147969308](https://github.com/MichaelWave369/PhiOS/actions/runs/36832501182/artifacts/11147969308) |
| Persisted receipt | [delivery-normal-1c16c473.json](evidence/delivery-normal-1c16c473.json) |

These preceding unsigned review downloads expire **2026-10-08**. A later build, branch
update, final merge or tag has a separate identity. Download the normal payload,
verify its complete ISO/source/artifact hashes against SHA256SUMS and provenance,
and retain the receipts with that exact build. The separate QA image contains
test fixtures and is not the physical observation candidate.

The owner also tested this exact candidate in Windows 11 Home / VirtualBox on
2026-10-01. Live UEFI/PAM and interactive desktop worked after enabling VMSVGA
3D acceleration, exporting the cursor workaround and rebinding the session
target. Initial renderer/cursor failures and the full supplied configuration
remain in [VIRTUALBOX_COMPATIBILITY.md](VIRTUALBOX_COMPATIBILITY.md) and
`evidence/virtualbox-field-1c16c473.json`. The narrow automatic startup correction
is the separately qualified #283 candidate recorded above. The new local report
supports its automatic startup case while preserving the original failures and
manual recipe. The preceding table and existing receipts retain their original
tested identities. Skytech/RTX 5070 remains physically untested.

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
| [281](https://github.com/MichaelWave369/PhiOS/pull/281) | Offline exact component source/notice delivery records and packet verification, stacked on integration #280 |
| [282](https://github.com/MichaelWave369/PhiOS/pull/282) | Documentation-only source-delivery qualification and original hardware handoff |
| [283](https://github.com/MichaelWave369/PhiOS/pull/283) | Scoped VirtualBox/VMSVGA cursor behavior and active Wayland service rebinding, independently qualified after #282 |
| [285](https://github.com/MichaelWave369/PhiOS/pull/285) | Evidence-only #283 automatic-startup/cold-cycle field report, preserving lock/shutdown/Secure Boot observations |
| [286](https://github.com/MichaelWave369/PhiOS/pull/286) | Bounded Home/Start/search/Apps callbacks and honest integration status, separately qualified after #285 |

Use the complete main-targeted integration PR as the merge vehicle after its
own exact-source qualification passes. It contains the candidate and aggregate
controller together, so main can require its observed `release-gate` before
integration. The component PRs above remain focused review references. Requiring
`release-gate` on the earlier component heads would leave them pending because
they predate that controller. Keep every merge and release under maintainer review.

The preceding #283 code continuation's aggregate gate passed all nine jobs in
[run 36916494462](https://github.com/MichaelWave369/PhiOS/actions/runs/36916494462)
for source `9510024d06d822729bd98579fefb6644ca0498c0`, with 2,358 Python tests
passed and six existing optional skips. The normal ISO passed two live boots,
manual PAM locking/refusal/unlock, complete logout/reauthentication and two new
active-session rebinding observations; production installation, three disk-only
boots, durable data/proof and matched root/EFI recovery passed on the same bytes.
The separate QA artifact repeated its ephemeral signed-package, refusal,
interruption and recovery cases. Both compact ZIP digests, 57 normal / 51 QA
metadata file hashes/sizes, 15 available checksum payloads per archive and the
source/ISO bindings were independently checked. Normal recovery/wrong-password
screenshots were visually inspected. Large ISO/package/source/notice archives
were not redownloaded here; their digests remain producer identities. The
owner-supplied local report separately records the normal ISO's full hash match
and VirtualBox automatic startup/cold-cycle results, with its exceptions intact.

The first #283 normal attempt failed the newly added rebinding observation in
run 36913191826; its install/recovery phase was skipped. Its source/ISO, serial
exception, screenshot and compact-archive hashes remain in
`evidence/virtualbox-compatibility-attempts.json`. Passing the later exact source
or its local VirtualBox retest does not replace this failed attempt.

The preceding source-delivery code continuation's aggregate gate passed all nine jobs in
[run 36832501182](https://github.com/MichaelWave369/PhiOS/actions/runs/36832501182)
for source `1c16c4732442d69d2c7b5763212f1977860a15ae`, with 2,324 Python tests
passed and six existing optional skips. Both exact normal and separate ephemeral
signed QA image lanes repeated their live/install/data/proof/desktop/recovery
scopes. Both downloaded compact ZIP digests, 15 available checksum payloads each
and available provenance records were checked. The actual 1,778,503-byte
first-party source archive was independently reconstructed from this exact
Git commit with the builder's normalized tar/gzip parameters and matched its
full recorded digest. Normal recovery and wrong-password screenshots were
visually inspected. ISO/package/third-party notice archive bytes were not
redownloaded; their identities remain producer hashes. See
`evidence/qualification-gate-1c16c473.json` and its linked receipts.

The delivery checker observed one verified first-party material file and all 501
component reviews still pending; the supplier notice archive and third-party
source/build material have not been supplied locally. The existing 746 captured
supplier notice files do not establish delivery/content/license compliance.
`evidence/source-delivery-1c16c473.json` records that exact observation. This
evidence-only handoff is a later source identity; its documentation CI does not
qualify a new image. Requalify final publication bytes after freezing them.

The preceding main-targeted integration's aggregate gate passed all nine jobs in
[run 36827706986](https://github.com/MichaelWave369/PhiOS/actions/runs/36827706986)
for source `a3572a9bac7051b70af2ef66e75bc021f4214b31`, with 2,287 Python tests
passed and six existing optional skips. The two compact archives were downloaded
and independently matched to GitHub's archive digests; 15 available checksum
payloads per archive and their available provenance records were checked. Normal
live/install/data/proof/recovery/desktop and the separate ephemeral signed QA
scope passed on their own exact ISO bytes. The normal inventory has 501 component
origins and 746 captured supplier notice files. Installed recovery and actual
wrong-password screen-lock screenshots were visually inspected. Large ISO,
package, source and notice archives were not redownloaded to the review host;
their hashes remain the producer's recorded identities. See
`evidence/qualification-gate-a3572a9b.json` and its two linked receipts.

The preceding integration attempt 36825649652 held the aggregate gate after
signed Arch downloads timed out before a normal image existed; its screenshot
preservation also failed because PIL had not yet been installed. The successful
later code guards that step and keeps attempt-specific artifacts. The failed run
remains recorded; its passed QA image never qualified the missing normal image.

The preceding desktop aggregate gate passed all nine jobs in
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
   SOURCE_DELIVERY.md documents the offline `init` / `check` / `bundle` tool for
   exact component coverage, declared reviews and retained local source/build/
   notice bytes. Its check of the integration metadata finds all 501 component
   reviews pending. Packaging is held until reviews and exact material bytes
   are supplied; complete delivery records do not authenticate a reviewer or
   prove the content/legal review is correct.
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
