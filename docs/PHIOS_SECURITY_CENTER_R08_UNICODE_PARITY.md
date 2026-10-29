# PhiOS Security Center R0.8: Unicode scalar acceptance

**No changes to device inspection authority.** This rung closes an
ambiguity in the browser's strict JSON ingestion for signed FieldShield
IOC packs, manifests, trust policies and user-selected observations.

After JSON escape decoding, the browser parser now rejects isolated
UTF-16 high/low surrogates anywhere in string values or object keys.
`JSON.parse` alone allows them. `TextEncoder` can silently replace
them with U+FFFD on later encoding, creating a different byte meaning
than Python's decoder or the signed input. Valid UTF-8 Unicode and
correctly paired surrogate escapes continue to work.

The shared test corpus is versioned and byte-identical in:

- `FieldShield/tests/fixtures/fieldshield-unicode-scalar-parity.v1.json`
- `PhiOS/phishell/src/security/fixtures/fieldshield-unicode-scalar-parity.v1.json`

The **7 valid / 12 rejected synthetic cases** cover nested keys,
array strings, lone and paired escapes and backslash-literal text.
An additional test generates a temporary Ed25519 key, cryptographically
verifies a synthetic signed pack and asserts malformed observation JSON
is rejected before exact-indicator matching.

This does not make the computer safe, authenticate a real-world
publisher or scan a device. All operations are limited to explicitly
selected local JSON and browser memory. No network access, upload,
IPC, filesystem walking, telemetry, host authority or remediation
has been added.

This changes parsing acceptance only. Some formerly accepted malformed
JSON must now be reissued rather than auto-corrected. Verify:

    cd phishell && npm test && npm run build

Co-review FieldShield's corresponding PR and complete PhiOS
qualification before merging manually.
