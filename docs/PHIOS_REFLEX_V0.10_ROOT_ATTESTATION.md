# PhiReflex v0.10 — Root Pinning and External Attestation

## Status

PhiReflex v0.10 hardens the root around v0.9 authenticated routing authority.

The central rule is:

```text
local trust-anchor file
!=
external root of trust
```

v0.10 does not widen the v0.6 routing-influence surface. It adds:

- an externally supplied exact trust-anchor pin;
- signed attestation of the installed provider adapter source digest;
- signed one-use activation nonces;
- exportable, offline-verifiable ledger checkpoint bundles;
- signed replication snapshots that may align or conflict but never overwrite local authority state.

## External root pin

The official v0.10 live path requires:

```text
PHIOS_REFLEX_ROOT_PIN=issuer_id:key_id:anchor_sha256
```

The pin binds one exact locally trusted anchor.

Example shape:

```text
operator:key-1:012345...cdef
```

The runtime checks:

1. issuer ID;
2. key ID;
3. exact validated trust-anchor SHA-256.

A missing pin, missing anchor, or digest mismatch removes live PhiReflex routing authority.

### Important trust boundary

v0.10 deliberately does **not** persist a second local "pin file" and call it stronger security.

If an attacker can modify both:

```text
~/.phios/reflex/authority/trust/...
and
the value used as PHIOS_REFLEX_ROOT_PIN
```

then the attacker controls the root.

The pin becomes meaningfully stronger when its value is supplied from a separately protected source such as:

- service configuration owned by a more privileged account;
- OS credential / secret infrastructure;
- container or deployment secret;
- hardware-backed configuration exposed through a future pin-provider adapter.

Actual TPM, Keychain, Credential Manager, or Secret Service storage is **not claimed by v0.10**.

## Provider adapter source attestation

v0.9 binds:

- provider;
- model set;
- adapter ID;
- adapter version.

v0.10 additionally computes SHA-256 over the installed Python source file resolved from:

```text
module:qualname
```

For Jev:

```text
phios.reflex.providers.jev:JevReflexProvider
```

The signed v0.10 `ReflexProviderArtifactAttestation` binds:

- provider-manifest envelope SHA-256;
- adapter ID;
- adapter version;
- exact adapter source SHA-256;
- issue/effective epochs;
- optional expiration epoch;
- issuer/key;
- Ed25519 signature.

Live activation and evaluation require the currently installed adapter source digest to match an effective signed attestation.

Therefore:

```text
same provider name
+ same model
+ same adapter version label
+ different installed source bytes
→ no live influence
```

## One-use activation nonces

v0.9 limits how many times a grant may activate.

v0.10 additionally requires a signed `ReflexActivationNonce` for each official activation.

The nonce binds:

- nonce ID;
- exact authenticated grant SHA-256;
- exact activation-request SHA-256;
- issuer/key;
- issue epoch;
- expiration epoch;
- Ed25519 signature.

The nonce is burned **before** delegation into the lower activation layer.

This is intentionally fail closed:

```text
reserve nonce
↓
delegate activation
↓
success → CONSUMED

or

delegate failure / crash boundary
→ nonce remains spent
```

A downstream failure may waste a nonce. It may not leave a successfully usable replay token.

## Official activation path

The v0.10 activation path requires:

1. exact external root pin;
2. v0.8 authenticated grant;
3. v0.9 live signing key;
4. v0.9 effective grant-use policy;
5. remaining grant activation count;
6. v0.9 authenticated provider manifest;
7. v0.10 authenticated installed-source digest;
8. v0.10 unused signed activation nonce;
9. all existing policy, validity, revocation, CAS, lease, and authority checks.

Only then may bounded v0.6 routing influence become live.

Direct v0.9 lifecycle activation is retired from the official shell path.

## Normal dispatch

Normal:

```bash
phi dispatch ...
```

now follows:

```text
v0.7 persisted runtime
↓
v0.8 authenticated grant
↓
v0.9 trust lifecycle + provider manifest
↓
v0.10 external root pin
↓
v0.10 installed adapter source digest
↓
v0.6 bounded reflex influence
↓
planner
```

If root or source attestation fails:

```text
live Reflex privilege collapses
→ no reflex_influence signal
→ ordinary dispatch
```

## Adapter digest inspection

The shell exposes the currently installed adapter digest:

```bash
phi agents reflex-root adapter-digest
```

This returns:

- adapter ID;
- adapter version;
- SHA-256 of installed source bytes.

That digest is suitable for creating the external signed provider-artifact attestation.

## Root-attestation operator surface

Status:

```bash
phi agents reflex-root status
```

Ingest signed provider-artifact attestation:

```bash
phi agents reflex-root artifact-attest provider-artifact.json
```

Ingest signed activation nonce:

```bash
phi agents reflex-root nonce-ingest activation-nonce.json
```

Activate:

```bash
phi agents reflex-root activate \
  --request request.json \
  --grant-id grant-001 \
  --nonce-id nonce-001 \
  --yes
```

Existing optional lease and control-CAS arguments remain available.

## Offline-verifiable checkpoint bundles

v0.9 creates signed checkpoints over:

- exact ledger entry count;
- ledger-head SHA;
- control fingerprint.

v0.10 can export a self-contained verification bundle:

```bash
phi agents reflex-root checkpoint-export cp-001
```

The bundle contains:

- the signed v0.9 checkpoint;
- the exact trust anchor used to verify it;
- a deterministic bundle SHA-256.

It can be verified without reading current PhiOS runtime state:

```bash
phi agents reflex-root checkpoint-verify bundle.json
```

Offline verification proves:

- bundled trust-anchor integrity;
- checkpoint issuer/key match;
- permission to sign ledger checkpoints;
- Ed25519 checkpoint signature;
- bundle integrity.

It proves what the signer attested. It does not independently prove that the bundled trust anchor was the correct organizational root unless the verifier separately trusts that anchor.

## Conflict-only replication snapshots

v0.10 introduces signed `ReflexReplicationSnapshot` artifacts for cross-machine comparison.

A snapshot binds:

- snapshot ID;
- issuer/key;
- export epoch;
- remote `control_sha256`;
- root-anchor SHA-256;
- optional checkpoint envelope SHA-256;
- Ed25519 signature.

Import:

```bash
phi agents reflex-root snapshot-ingest snapshot.json
```

requires the same external root pin.

The result is only:

```text
REPLICATION_ALIGNED
or
REPLICATION_CONFLICT
```

A conflict is receipted into the runtime ledger.

The import path does **not** overwrite:

- policy;
- activation;
- lease;
- grants;
- trust anchors;
- lifecycle state.

This makes v0.10 replication a comparison primitive, not authority synchronization.

## Authority boundary

Even after all v0.10 checks pass:

```text
routing_influence_authority = true
promotion_authority = false
action_authority = false
execution_authority = false
```

v0.10 cannot:

- invent or mutate the external root pin;
- sign authority artifacts;
- create private keys;
- bless changed adapter bytes without a new signature;
- reuse a consumed nonce;
- overwrite local authority because a remote snapshot differs;
- grant tools;
- execute tools;
- bypass CAPS;
- bypass Spine execution permission.

## Tests

v0.10 tests verify:

- exact root pin + provider source attestation + nonce allow activation;
- one nonce cannot be reused even when the grant allows multiple activations;
- missing external root pin collapses existing live influence;
- wrong installed adapter digest cannot authorize activation;
- adapter-source hashing produces a stable SHA-256 digest;
- checkpoint bundles verify offline and fail after tampering;
- replication conflicts produce receipts without overwriting activation state;
- normal shell dispatch restores only v0.10 root-governed influence;
- live root-governed influence remains incompatible with clean shadow measurement;
- direct v0.9 shell activation is disabled.

## Next rung

The next rung should focus on protected pin providers and portable attestation rather than broader model influence.

Candidates for v0.11:

- Windows Credential Manager root-pin provider;
- macOS Keychain provider;
- Linux Secret Service provider;
- TPM / hardware-backed public-key pin provider;
- provider package / wheel Merkle manifests;
- offline checkpoint verification CLI independent of the PhiOS runtime package;
- replication reconciliation proposals that still require explicit operator grants;
- signed recovery-root ceremonies.

The live routing surface should remain narrow until those roots are operationally hardened.
