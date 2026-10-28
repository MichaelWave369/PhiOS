# PhiOS Security Center v0.2: operator-approved offline signed-pack review

**Status: offline cryptographic review of local IOC pack bytes under a caller-supplied
Ed25519 public-key pin. NOT a host scan or publisher identity attestation.**

This rung adds an explicit PhiOS CLI verifier and a separate browser-only
preview for its saved output. The older Security Center v0.1 historical PhiARK
and Sentinel receipt viewers remain read-only and unchanged in authority.

## Source and explicit operator consent

FieldShield v0.3 defines the relevant detached Ed25519 signature and local
trust-policy format. PhiARK R0.7 stores exact signed IOC pack bytes. PhiOS
uses independent Python verification to review these on an operator's local
machine; no FieldShield process is executed and no PhiARK service is contacted.

Install the PhiOS **reflex-authority** optional dependency or its developer
dependencies to supply the already-used cryptography backend. Dependency
acquisition may require network access; **offline verification does not**.
No service is automatically enabled.

The operator separately obtains and validates:

- `pack.json`, the signed FieldShield IOC pack bytes
- `pack.sig.json`, the corresponding detached FieldShield Ed25519 manifest
- `trusted.json`, a manually provisioned local public-key trust policy
- the **out-of-band verified SHA-256 digest of the raw 32-byte Ed25519 public
  key**, independently obtained through a genuinely trusted channel

A digest copied from the same downloaded bundle is **not independently
authenticated**, even if it exactly matches the signature.

Run with explicit approval:

    phi-sentinel-review \
      --pack ./pack.json \
      --signature ./pack.sig.json \
      --trust ./trusted.json \
      --expected-public-key-sha256 <64-hex-out-of-band-key-fingerprint> \
      --i-approve-local-review

Run `python -m phios.apps.sentinel_offline_review` instead of the installed
console command from an appropriate source checkout.

This command reads only the three specified files, requires the external pin,
checks a bounded snapshot of each, verifies the FieldShield v0.3 canonical
signature domain and header, checks expiration and local revocation/blocking
policies, and prints JSON to stdout. It **never writes a file**, opens a
network connection, starts a process, scans a device, or changes a PhiOS grant.
An explicit operator shell redirect can save its stdout if desired.

## Output

The JSON output uses
`phios.security_center.offline_pack_review.v0.2` and status
`ED25519_VALID_UNDER_CALLER_SUPPLIED_PIN_NO_HOST_SCAN`.

It records hashes for exact pack/manifest/trust bytes, caller-supplied
fingerprint, claimed publisher name and key ID, claimed indicator count,
signature expiry and the clock time of review. These are **local-review
observations**. It explicitly records all of these as false:

- independently authenticated public-key provenance **by PhiOS**
- real-world publisher identity authentication
- IOC factual accuracy verification and local device security observation
- any scanner execution or network access
- any launch/gateway authority or effects performed

It does not validate each indicator against FieldShield's full IOC schema,
nor does it verify threat-intelligence rights, accuracy, or independence.

## Browser integration boundary

Use PhiShell > Apps > Security Center and select the saved PhiOS JSON review
under the new offline-review panel. This browser-only component **does not
independently authenticate the JSON** and always shows
`IMPORTED CRYPTO REVIEW · NOT REVERIFIED BY BROWSER`. It does not
connect to the verifier, receive secrets or perform host actions.

No receipt imports become a device-safety badge. Without a separately
reviewed and authorized host transport and a freshness-bound receipt, the
browser cannot establish that a historical JSON came from the locally
executed verifier or reflects the current device.

## Limitations / next gate

- No trusted key providers or deployable signing secrets are shipped.
- Verification uses the host clock; it does not prove secure time.
- A compromised signing key or manipulated trust policy/host can subvert
  assumptions. Out-of-band pin checking is ultimately the operator's job.
- Filesystem symlink checks use O_NOFOLLOW where supported; additional
  hostile concurrent filesystem race hardening is needed for hostile hosts.
- Review receipt JSON is unsigned; cryptographic claims in a browser file
  are only imported text. This is **not** end-to-end OS attestation.
- The legacy, unsigned FieldShield scan path is separate; no privileged
  inspection or remediation has been added to PhiOS.

Future milestone: a strictly local, authenticated, approved transport
that binds the verifier's result to the right caller, host and one-time
request, without exposing a general command execution endpoint.

## Verification

    python -m pytest -q tests/test_sentinel_offline_review_v02.py
    cd phishell && npm test && npm run build

Synthetic tests generate ephemeral keys in memory, covering correct
signatures and explicit consent; altered packs, signatures, publishers,
revocation, digest blocklists, expiry, external-pin mismatches,
ambiguous JSON, and refusal of forged authority.
