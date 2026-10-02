# NBG-A qualification observation provider v0.1

This experimental provider makes the reviewed #284 public contract usable on the
current PhiOS/Linux continuation. It reads a fixed public qualification packet,
checks its document bytes and returns normalized Memory Receipts with directional
documentary paths. It is an offline reader of historical evidence, not a live
PhiKernel memory service or a new source of release authority.

## Read the observations

The Arch package installs the packet and its four public documents under
`/usr/share/phios/nbga`. From Foot in a candidate containing this change:

```sh
python -m phios.adapters.nbga_observation
```

To inspect the launcher retest after checking the complete packet:

```sh
python -m phios.adapters.nbga_observation \
  --bubble-id bubble:phios:virtualbox:launcher-0f17bac1
```

From the repository root, use its public evidence directory explicitly:

```sh
python -m phios.adapters.nbga_observation --evidence-root docs/os/evidence
```

Success returns JSON and exit status 0. Missing, altered, unsupported or malformed
evidence returns an unavailable JSON result and exit status 2, without any partial
observations or host paths. This command creates no files and starts no service.
The previous #286 ISO does not contain this new provider.

## Evidence and paths

| Bubble | Evidence preserved |
| --- | --- |
| `original-1c16c473` | Owner-reported renderer failure with 3D off, invisible pointer after enabling 3D, separate cursor override and session-target rebinding |
| `failed-attempt-146e470f` | Reviewed failed normal CI rebinding attempt; installation/recovery skipped; screenshot/QA pass did not qualify that normal image |
| `automatic-9510024d` | Owner-local #283 automatic startup and cold cycle; unresolved blank lock screen, untested PAM unlock, refused sudo poweroff |
| `launcher-0f17bac1` | Owner-local #286 navigation/window/shortcut checks and cold cycle; older ISO rejected, Wofi drun workaround, unavailable canonical-history backend |

Full bubble identities begin `bubble:phios:virtualbox:`. The `documented-follow-up`
Gear path identifies the sequence of reviewed records. It does not prove a causal
relationship or execute a transformation. `event_head` identifies the last
documentary evidence reference; it is not an implemented append-only runtime log.

The provider's code pins the complete packet to SHA-256
`d61f0bd49de27f770e62d36871dbd335f82684c526a8631b19da6dc2b5651608`.
The packet pins each document's complete digest and size. Every document is read
and checked before a query filter is applied. Updating the packet requires a
reviewed code-pin change; a packet cannot provide its own trusted digest. Python
callers supplying a custom `expected_packet_sha256` own that external trust input.

`evidence_integrity=verified-against-pins` means the selected documentary bytes
match these reviewed pins. It does not independently authenticate the original
Windows tester, prove a reported event occurred or hash the historical ISO,
screenshots, packages and logs referenced inside the documents. The packet is
not a maintainer-signed publication artifact. Those underlying items retain the
exact producer/reviewer/owner-reported status recorded in the original receipts.

Memory Receipts preserve `owner-reported` or `reviewed-ci-record` trust states,
with no manufactured numeric confidence. Their public `provenance_root` hashes a
domain-separated record of the packet digest and referenced document pins. This
identifies documentary lineage; it is not a private PhiKernel governance root,
an anchor promotion or proof that an observation is true.

## Refusals and authority

The reader rejects packet/digest/size mismatches, missing or non-regular files,
symbolic-link evidence, traversal/URL filenames, duplicate packet JSON fields, unknown
schemas/fields, non-finite JSON numbers, unbounded data, unresolved/repeated
references, disconnected/cyclic paths, conflicting Gear definitions and attempts
to assert `verified` trust. Complete references and path endpoints must resolve
within the checked packet.

The existing NBG-A public parser remains unchanged from #284. Private payloads,
authority grants and unknown contract fields remain refused. No network request,
process execution, memory write, anchor, decay, manifest commit, adapter promotion,
model selection or OS policy change is introduced by the reader. It bypasses no
existing governed canonical-memory service or read/compare permission.

Bubble Zero is explicitly **unavailable: no continuity backend**. No roots,
checkpoint or restored identity are invented. The result retains
`publication_authority=false` and `release_ready=false`.

## Qualification and next step

Focused tests cover the real documentary sequence, deterministic read-only
queries, failures surviving filtering, external pins, file/schema/path refusals,
lineage checks, trust-state limits and CLI refusal output. The existing external
desktop probe additionally invokes the installed reader with Python isolated
mode as UID 1000 during live/installed VM checks. It also alters a copied prior
failure document in a disposable user-owned directory and requires refusal of
the latest-observation query without any partial results. It records the packet digest,
four checked documents, tamper refusal and unavailable continuity backend alongside its current
source identity. Historical #286 observations do not qualify the new boot.

This continuation copies the three reviewed #284 contract files onto the #287
branch chain; those sibling PRs and prior qualified source/ISO/failure receipts
remain unchanged. PhiOS's Arch package revision increases to 2; software and OS
release versions remain unchanged. Changed candidate bytes require their own
full normal/QA qualification and a fresh owner-local field test before claiming
VirtualBox compatibility for this candidate.

The next rung can consume a genuine normalized runtime observation behind the
existing PhiKernel boundary. Persistence, Bubble Zero verification and A-TEAM
mutation operations require separately reviewed contracts and a persistent
installed test environment. A live ISO's temporary overlay does not establish
cold-power-cycle memory reconstruction. Private PhiKernel/TIEKAT implementation
internals remain outside public PhiOS.

## Owner-local #288 field observation

The owner-local VirtualBox `7.2.20r175154` report for exact normal ISO `0e68508d...`
records ordinary-user reader success, repeated filtered output, unchanged
installed hashes, and refusal of both a tampered and a missing prior-failure
document in disposable copies. Automatic desktop/cursor startup, actual
lock/wrong-password/same-session unlock and ACPI cold boot also passed as
reported. Wofi launcher regression remains **PARTIAL FAIL**; the canonical-history
backend remains unavailable and the `vmwgfx` warning is preserved.

The supplied full/filtered JSON files were regenerated on the Windows host after
the guest run was validated: TCP and ordinary-user serial export failed. This
review hashed both attachments and reproduced their exact bytes with the pinned
provider. That verifies reproducible historical output, not raw guest capture or
new memory persistence. Cited screenshots were not supplied to this review.
The normalized field receipt is
[virtualbox-field-a44dd077.json](os/evidence/virtualbox-field-a44dd077.json).
It remains outside the unchanged four-document packet. No new observation is
silently inserted into the qualified #288 reader, and no release authority is
created by its field test.
