# PhiOS Security Center v0.4: offline, opt-in observation matching

**Scope: user-selected FieldShield JSON observations only. No host scan.**

This v0.4 rung adds an in-browser exact-indicator matcher to PhiShell's
Security Center. Each comparison **freshly verifies** the exact signed
FieldShield v0.3 pack bytes against the selected detached Ed25519 manifest,
manually maintained trust policy and an independently authenticated raw
public-key SHA-256 fingerprint (v0.3). It then compares only evidence JSON
explicitly chosen by the operator.

## How to use

1. In Security Center v0.3, select a `pack.json`, `pack.sig.json`,
   and `trusted.json`, type an independently checked 64-digit
   public-key SHA-256 fingerprint and confirm that check.
2. In the new v0.4 section, select a FieldShield observations JSON file:
   `{"schema":"fieldshield.observations.v1","observations":[{"kind":"domain","value":"example.invalid"}]}`
3. Confirm **I own this evidence or have permission to inspect it**, then
   click **VERIFY PACK AND COMPARE SELECTED OBSERVATIONS**.

All inputs remain in browser memory, only after explicit file selection.
No server request, host scan, file enumeration, process/device probe, IPC,
privilege, upload, telemetry or automatic remediation is introduced.

## What the comparison checks

Matches precisely the FieldShield Sentinel v0.1 observation type semantics:

- `sha256`: case-insensitive 64-digit hexadecimal exact hash.
- `domain`: lowercased, trailing dots stripped, valid DNS label rules.
- `url`: exact HTTP(S) URL text, no credentials/whitespace.
- `path`: exact safe relative paths, backslashes normalized.
- `process`, `bundle_id`: exact case-sensitive trimmed strings.
- URL observations also attempt an exact domain-indicator match for the
  URL hostname (FieldShield behavior).

The matcher **rejects the entire signed pack** if any indicator is
malformed, has duplicate/unsafe ID, invalid confidence/type/value or
missing HTTPS provenance. It does not blindly match strings from
a signed yet semantically invalid pack.

Observations exceeding 100,000 entries and input bytes above 8,000,000
are refused. Other limits: pack 2,000,000 bytes, manifest 16,384 bytes,
trust policy 131,072 bytes, maximum 1,000 findings, maximum 24 example
indicator IDs in the UI. Invalid observation entries are counted as
`uninspected`. If matching reaches its 1,000-finding cap, the report
is marked INCOMPLETE.

The in-memory result reports the selected JSON SHA-256, verified signed
pack SHA-256, exact counts, limited safe indicator IDs and observation
indexes. **Raw evidence values, path names, domains and URLs are not copied
into the result**.

## Verdicts, and what they do NOT mean

- `INDICATORS_FOUND`: exact IOC matches in the selected data.
- `NO_MATCHES_IN_SCOPE`: no IOC matches in the supplied observations.
  **Does NOT mean malware-free.**
- `INCOMPLETE`: invalid/uninspected evidence, hit the findings limit, or
  zero valid inspected observations. Never imply a complete scan.

Even a perfect signature does **not** prove trustworthy publisher identity,
indicator accuracy, timestamp integrity or device infection. The operator
remains responsible for independent trust-root verification. An evidence
observation may be misleading, stale or fabricated. This feature performs
no phone forensics and no device collection.

The comparison result does NOT grant a PhiOS capability or privileged
execution. There is no automatic saving, synchronization, or browser
persistence; reload discards the result. It does not replace the
fully independent offline FieldShield CLI.

## Verification

    cd phishell
    npm test
    npm run build

Tests create synthetic ephemeral signing keys and exercise:
valid exact/domain-fallback matches, inspected and uninspected counts,
typed normalization, no-match and incomplete states, empty observations,
tampered signatures/pack hashes, wrong external pin, locally revoked keys,
duplicate/malformed indicators, oversized input and match caps.

Future direction: compare parity with Python FieldShield using a shared
machine-readable synthetic fixture and structured cross-runtime receipts.
No live device inspection should be enabled without a separate
operator-authorized, sandboxed host process and full policy review.
