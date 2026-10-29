# Security Center R0.7: strict JSON ambiguity parity

PhiOS's browser-side FieldShield trust and evidence verifier now applies
a deliberately strict, shared JSON interpretation policy. This is an
offline parsing hardening release, not a new host scanner.

The same `fieldshield-strict-json-parity.v1.json` fixture is committed
in PhiOS (`phishell/src/security/fixtures/`) and FieldShield
(`tests/fixtures/`) and tested independently by both engines.

## Required behavior

- Reject duplicate JSON properties even with `\\u` escapes in the key,
  including duplicates nested in objects and arrays.
- Reject `NaN`, `Infinity`, `-Infinity`, and numeric exponents that
  parse into non-finite floating-point values.
- Reject integer tokens outside the IEEE-754 exact safe-integer range.
- Reject non-JSON Unicode whitespace and leading BOM instead of treating
  them as interchangeable with RFC JSON whitespace.
- Reject prematurely terminated objects/arrays, trailing garbage and
  malformed tokens; bound structural nesting at depth 48.
- Avoid including duplicate raw property names (potentially sensitive
  forensic labels) in error text.

These rules apply to operator-selected IOC packs, detached signatures,
trust policies, and observations ingested in PhiOS's browser verification
and matching flow. FieldShield's Python Sentinel and verified signer
reader share an equivalent parsing policy.

Existing protections remain: no network, device scan, automatic evidence
collection, upload, elevated execution, remediation, persisted evidence or
host-security verdict. Only files explicitly selected by the operator are
read in memory; cryptographic verification still requires an independently
pinned Ed25519 public key.

The corpus has six accepted and 23 rejected synthetic examples. The tests
also verify that duplicate observation properties are rejected **after**
a fresh signature verification of the selected pack, not accepted through
a stale receipt. This does **not** prove universal JSON-parser equivalence;
future vector additions and bounded differential tests are still useful.

Run:

    cd phishell
    npm test
    npm run build

Co-review the FieldShield companion PR and full PhiOS qualification before
merging.
