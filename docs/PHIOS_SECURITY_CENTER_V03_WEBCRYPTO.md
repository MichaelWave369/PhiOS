# PhiOS Security Center v0.3: browser-only signed IOC verification

**Operator-selected, in-memory WebCrypto Ed25519 verification.**

This milestone closes one specific gap in v0.1/v0.2: the browser can now
cryptographically verify the exact selected FieldShield v0.3 signed IOC pack
instead of only rendering a saved JSON report. It does **not** authenticate
a host, verify the real-world publisher, run Sentinel, attest a device, or
validate whether the indicator claims are accurate.

## Local workflow

Open PhiShell > Apps > Security Center, then the **Verify signed intelligence
bytes** section.

- Choose a locally saved FieldShield `pack.json`, the corresponding
  `pack.sig.json`, and a manually maintained `trusted.json`.
- Independently confirm the **SHA-256 of the raw 32-byte Ed25519 public key**
  using a trusted source outside these files and outside the web page.
  Enter the 64-character lowercase hexadecimal fingerprint.
- Confirm you independently authenticated the pin and click
  **VERIFY SELECTED PACK · IN THIS BROWSER**.

If WebCrypto Ed25519 is unsupported or the browser lacks a secure crypto
context, verification refuses. Offline use is supported when the PhiShell
web assets have been installed locally on a secure origin (e.g. localhost).
There are no network requests in the verifier, even in an offline browser.

## What is cryptographically checked

- Exact pack-byte SHA-256 matches signed manifest.
- Exact Ed25519 signature over FieldShield's v0.3 domain-separated,
  ASCII-sorted canonical JSON manifest fields.
- Trusted publisher/key membership in separately selected policy, local
  revoked-key state, blocked digest list, and minimum issuance date.
- Raw public-key SHA-256 equals the operator-supplied independent pin.
- Manifest signature issue/expiration is valid against the browser clock.
- Signed pack is a basic FieldShield IOC container with a bounded indicator
  count and issue date preceding the signed manifest.
- JSON decoding rejects duplicate keys at all levels; unsupported schema,
  unknown keys and malformed input fail closed.

Supported input bounds: pack 2,000,000 bytes, manifest 16,384 bytes,
trust 131,072 bytes. The selected IOC pack is **never sent** to an API.
All inputs and results are held only in browser/component memory.

## Security limitations

The operator must obtain the external key fingerprint independently.
Merely copying the fingerprint from `trusted.json` or the same package is
circular trust, not real-world publisher authentication. A hostile page,
compromised local OS, manipulated clock or altered trust policy can invalidate
the assumptions.

The verifier does not validate every indicator's semantics, threat claims,
legal redistribution, signature timestamp authority, actual device infection
status, evidence scope, or installed FieldShield runtime. A valid signature
only authenticates bytes to the operator-pinned key **at that instant**.
Because local time is not independently attested, expiry is checked only
against the device's current clock.

A saved v0.2 JSON file remains **historical unauthenticated text** unless
re-verified from the actual source pack, signature and trust bytes. This new
feature does not promote prior receipts into live host evidence.

No app installation, browser file upload, subprocess, network call, event
subscription, system scan, privilege escalation, remediation, telemetry, or
trust-store mutation is added. No host-security green verdict is displayed.

## Testing

    cd phishell
    npm test
    npm run build

The tests use ephemeral Ed25519 keys and synthetic IOC packs; cover valid
FieldShield-compatible signature bytes, tampering, wrong pins, revoked and
unknown keys, blocked hashes, expired and future manifests, duplicate JSON
keys, and refusal to treat any result as host security evidence.

This is a focused prototype crypto client, not an independently audited
software supply-chain verifier or a system-attestation mechanism.
