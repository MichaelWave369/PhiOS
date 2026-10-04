# Exact candidate source and notice delivery

On a Linux maintenance host with Python 3.11 or newer,
`packaging/linux/source_delivery.py` prepares a separate, offline review and
delivery packet for one **normal** candidate. It uses the final SBOM component
identities, including distinct installed and bundled frontend origins. Supplier
license labels remain declarations. No license conclusion or disposition is
selected automatically, and nothing is downloaded, signed or published.

The release owner must review the actual applicable terms, corresponding source,
build instructions/patches, required notices and delivery arrangement for each
component. The tool checks recorded coverage and local bytes. A reviewer name and
timestamp are recorded assertions, not authenticated decisions or proof that the
legal/content review is correct. See RELEASE_ARTIFACTS.md for the independent
release signing, hardware, final-transition and publication gates.

## Bind the review to the candidate

Start with the exact normal candidate payload from RELEASE_HANDOFF.md. In one
directory retain `provenance.json`, `sbom.cdx.json`, `source-review.json`,
`third-party-notices.json` and `SHA256SUMS` unchanged. These metadata files may
also come from its compact evidence archive, using the actual
`PhiOS/PhiOS/dist/fixture-free/` directory. The tool checks their hashes against
checksums/provenance, their common source identity, and complete SBOM coverage.
It refuses the separate QA image.

```sh
python3 packaging/linux/source_delivery.py init \
  --candidate /path/to/exact-normal-candidate \
  --output /path/to/source-delivery-manifest.json
```

`init` creates a new file and refuses to overwrite an existing review. Every
component starts pending. The manifest binds the source commit/epoch, ISO
identity, first-party source and supplier notice archives, and exact metadata
hashes. A changed build needs a new manifest; do not transfer completed reviews
to changed component identities without fresh review.

Checksums/provenance here do not authenticate their publisher. A compact archive
also does not contain the ISO/source/notice archive bytes. Verify the actual ISO
and authenticated final signature separately. The report always records
`iso_bytes_independently_verified: false` because this tool does not read the ISO.

## Supply real material and record reviews

Place the selected source, actual build/patch material and notices beneath one
explicit local materials directory. Use ordinary relative paths without spaces,
traversal, symlinks or special files. Input archives stay opaque and are never
extracted. Each catalog entry has these exact fields:

```json
{
  "path": "sources/component-version.tar.gz",
  "kind": "corresponding-source",
  "sha256": "ACTUAL_FULL_LOWERCASE_SHA256",
  "size": 12345,
  "origin": "Actual source origin and exact revision/version",
  "custody": "How these exact bytes were acquired and retained"
}
```

Replace every example value with the actual record. `kind` is
`corresponding-source`, `build-material` or `notice`. Use `sha256sum` and the
actual file byte count to record identity. The checker independently reads and
hashes each local file; a URL or claimed hash without supplied bytes is held.
An Arch binary `.pkg.tar.*`, wheel or ISO cannot satisfy a source/build record.
A source filename alone does not establish that its contents correspond to the
distributed binary; the reviewer must inspect the actual material.

Supply the exact `phios-source.tar.gz` and `third-party-notices.tar.gz` named by
the bound provenance as corresponding-source and notice catalog entries. The
checker requires those exact archive hashes/sizes before packaging. The
first-party archive contains the checked-out code, packaging/build files and
patches; it does not replace third-party corresponding source. Do not include
private release keys or private PhiKernel/TIEKAT implementation material.

For each component, preserve `component`, `name`, `version` and
`declared_licenses`. Fill its `review` with an explicit `source-required` or
`no-source-required` disposition, reviewer, timezone-bearing ISO timestamp,
applicable terms and rationale. Record source/build/notice paths as references
to the material catalog. `source-required` requires both corresponding-source
and build/patch records. `no-source-required` still requires actual reviewed
terms and a rationale; it is never inferred from MIT/GPL/custom supplier labels.
Notice references may be empty only when that reviewed rationale explains the
applicable delivery requirements. One retained material path can be shared by
several exact component origins. Unreferenced extra files are refused.

## Check and seal the packet

```sh
python3 packaging/linux/source_delivery.py check \
  --candidate /path/to/exact-normal-candidate \
  --manifest /path/to/source-delivery-manifest.json \
  --materials /path/to/materials

python3 packaging/linux/source_delivery.py bundle \
  --candidate /path/to/exact-normal-candidate \
  --manifest /path/to/source-delivery-manifest.json \
  --materials /path/to/materials \
  --output /path/to/source-delivery.tar.gz
```

| Exit | Meaning |
| --- | --- |
| `0` | Init succeeded, or all delivery records/files are present, or a complete packet was sealed |
| `1` | Invalid identity/record, changed/missing bytes, unsafe path, or incomplete bundle request |
| `2` | Check was valid but component reviews or the exact source/notice archives remain pending |

`check` emits a report with pending component identities, missing candidate
archives, verified local material counts and the canonical manifest hash.
`bundle` refuses incomplete records, seals and rechecks material bytes, and
retains the original candidate metadata, manifest, report, selected material
and a new internal checksum index in a deterministic gzip/tar archive. It
refuses output overwrite. Matching inputs produce matching packet bytes; this
does not imply reproducibility of the OS image itself.

File material is bounded to 8 GiB each / 32 GiB total; metadata to 16 MiB.
Materials use non-following descriptor-relative opens. Changing material or
candidate bytes between checking and sealing holds the packet.

`delivery_records_complete` means only that the specified declarations and
local byte records are complete. Reports always retain
`review_declarations_authenticated: false`,
`license_source_compliance_reviewed: false`, `release_ready: false` and
`publication_authority: false`. The release owner still evaluates the supplied
terms/content and delivery arrangement before publishing final distribution
bytes with their required accompanying materials.

## Continuation observation

The independently checked normal metadata from integration run **36827706986**
has 501 component origins and 746 supplier notice files. Initializing/checking
that exact candidate leaves all 501 reviews pending and requires the actual
first-party source and supplier notice archive bytes. This is the observed
starting point, not a completed source-delivery gate. The compact observation
receipt is `evidence/source-delivery-a3572a9b.json`.

The later source-delivery code run **36832501182** passed all nine jobs for
source `1c16c4732442d69d2c7b5763212f1977860a15ae`, including the 37 new delivery
checks in full Python CI (2,324 passed / six existing optional skips), both exact
normal and ephemeral signed QA image scopes. Both compact archive digests,
available checksum/provenance payloads and source identities were checked.
The first-party archive was independently reconstructed from that exact Git
commit with the builder's tar/gzip parameters; its actual 1,778,503 bytes and
SHA-256 `0a2a58aa9ce77e369435e731510859cdee7fc820a9f2333e308441013faf42ec`
matched candidate provenance. The tool then verified that one supplied material,
left all 501 reviews pending, and held delivery for the remaining material and
review work. `evidence/source-delivery-1c16c473.json` records the exact first-party
reconstruction and observation. A matching source archive does not complete
third-party content/notice delivery or authenticate a reviewer.
