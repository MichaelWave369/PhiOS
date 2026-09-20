# PhiReflex v0.8 — Authenticated Authority and Coordination

## Status

PhiReflex v0.8 strengthens the authority path around the persistent v0.7
runtime control plane.

The central rule is:

```text
declared authority identity
!=
authenticated authority identity
```

v0.8 adds:

- Ed25519-authenticated activation grants;
- explicit local trust anchors;
- signed grant revocation;
- grant validity windows;
- automatic rejection of unsigned legacy live authority;
- cross-process runtime serialization;
- a deterministic control-plane fingerprint for compare-and-swap checks.

It does **not** widen the v0.6 routing-influence surface.

## Optional cryptographic dependency

Base PhiOS remains dependency-light.

Ed25519 verification is provided by the optional extra:

```bash
pip install "phios[reflex-authority]"
```

or from a checkout:

```bash
pip install -e ".[reflex-authority]"
```

The authority module can be imported without that extra. Operations requiring
Ed25519 verification fail closed if the cryptographic backend is unavailable.

PhiOS does not implement home-grown signature cryptography.

## Trust anchors

A v0.8 trust anchor uses schema:

```text
phios.reflex_authority_trust_anchor.v0.8
```

It binds:

- `issuer_id`;
- `key_id`;
- algorithm `ed25519`;
- raw 32-byte Ed25519 public key encoded as canonical base64;
- allowed purposes;
- deterministic anchor SHA-256.

Supported purposes are:

```text
activation_grant
grant_revocation
```

Trust-anchor installation is an explicit local root-of-trust operation.

The shell requires:

```text
--yes
```

before expanding that trust boundary.

### What the trust anchor means

If local configuration says:

```text
issuer_id = operator
key_id = key-1
public key = ...
```

and an artifact verifies under that key, v0.8 can establish:

> this artifact was signed by the holder of the private key corresponding to
> the locally trusted `operator/key-1` public key.

It does **not** establish a universal real-world identity.

The local trust-anchor store is the root of trust. If an attacker can replace
that trusted public key and also alter the local control plane, signature
verification will faithfully authenticate the attacker's newly installed key.

Protecting or remotely attesting the local trust-anchor store is outside v0.8.

## Private keys

PhiOS v0.8 does not generate, store, or consume authority private keys.

Signing is deliberately external to the runtime authority consumer.

The module exposes canonical signing helpers:

- `activation_grant_signature_payload(...)`;
- `grant_revocation_signature_payload(...)`;
- `canonical_authority_bytes(...)`.

This preserves:

```text
grant issuer
!=
grant consumer
```

The runtime cannot sign itself more authority.

## Signed activation grants

The signed envelope schema is:

```text
phios.reflex_signed_activation_grant.v0.8
```

The Ed25519 signature covers:

- schema;
- issuer ID;
- key ID;
- issued-at epoch;
- valid-from epoch;
- optional valid-until epoch;
- the complete v0.6 `ReflexActivationGrant` payload.

The envelope additionally records:

- signature base64;
- deterministic envelope SHA-256.

The exact grant remains bound to:

- policy-state SHA-256;
- current activation-state SHA-256;
- activation-request SHA-256;
- disposition.

v0.8 adds the requirement:

```text
grant.authority_source == authenticated issuer_id
```

A correctly signed envelope cannot claim to represent another authority-source
label.

## Validity windows

A signed grant may carry:

```text
valid_from_epoch
valid_until_epoch
```

Activation before `valid_from_epoch` is rejected.

At:

```text
evaluation_epoch >= valid_until_epoch
```

the grant is expired.

If an already-active runtime later reaches the signed-grant expiration
boundary, authenticated-authority enforcement collapses routing influence.

Evaluation epochs remain explicit inputs to the deterministic core.

## Signed revocation

Revocation schema:

```text
phios.reflex_grant_revocation.v0.8
```

A revocation binds:

- revocation ID;
- issuer ID;
- key ID;
- target v0.6 grant SHA-256;
- effective epoch;
- reason;
- Ed25519 signature;
- envelope SHA-256.

The revocation must be signed by a locally trusted key for the same issuer as
the target authenticated grant.

A future-dated revocation may be stored in advance.

When:

```text
evaluation_epoch >= effective_epoch
```

and the target grant backs the current active runtime:

```text
routing influence
→ DEACTIVATED
```

Privilege collapse does not require a new expansion grant.

## Legacy unsigned authority

The v0.7 storage API remains available internally for compatibility and tests,
but v0.8 changes the official live-authority path.

Normal dispatch now requires an active v0.6 grant to have a matching,
valid, authenticated v0.8 signed envelope.

Therefore:

```text
legacy unsigned activation
→ authenticated-authority enforcement
→ privilege collapse
```

The shell disables unsigned live expansion commands:

```text
phi agents reflex-runtime grant-ingest ...
phi agents reflex-runtime activate ...
```

and directs operators to the authenticated v0.8 authority surface.

This prevents the old v0.7 CLI path from bypassing signed provenance.

## Multi-process coordination

v0.8 places a shared host-OS advisory file lock beneath the v0.7 runtime
control plane:

```text
~/.phios/reflex/control.lock
```

Official control-plane public operations are serialized across processes.

Implementation:

- POSIX: `flock(LOCK_EX)`;
- Windows: `msvcrt.locking(..., LK_LOCK, ...)`.

The lock is re-entrant within one `ReflexRuntimeControlPlane` instance, so a
public operation may safely call recovery or another guarded operation.

Tests use two separate processes and verify that the second process cannot
enter the critical section until the first releases it.

The lock is advisory. Processes that deliberately ignore the PhiOS control
plane can still write directly to local files if the operating-system account
permits it.

## Compare-and-swap fingerprint

Authenticated-authority status returns:

```text
control_sha256
```

The fingerprint binds the observed control surface:

- policy-state SHA-256;
- activation-state SHA-256;
- lease SHA-256;
- runtime-ledger head SHA-256;
- trust-anchor SHA-256 set;
- authenticated grant-envelope SHA-256 set;
- revocation-envelope SHA-256 set.

Authority-changing shell operations may supply:

```text
--expect-control-sha <sha256>
```

If the current fingerprint differs:

```text
control-plane compare-and-swap precondition failed
```

and the requested mutation is rejected.

The OS lock prevents concurrent mutation during one operation; the fingerprint
prevents a caller from applying an authority decision based on stale observed
state.

## Fail-closed authority-store behavior

Authenticated authority is revalidated before live influence is used.

The runtime collapses live influence when:

- the active grant has no authenticated envelope;
- the envelope signature no longer verifies;
- the trusted issuer/key is missing or invalid;
- the grant is outside its validity window;
- an effective signed revocation exists;
- authority provenance metadata needed for the live path is corrupted.

A malformed authority artifact is never interpreted permissively.

If the authority store cannot be trusted, normal dispatch receives no live
PhiReflex routing signal.

## Persistence ordering

When a signed grant is ingested:

1. its complete v0.6 grant is validated and persisted into the existing v0.7
   inert grant store;
2. only then is the authenticated signed envelope persisted.

This ordering is intentionally fail closed.

If authenticated-envelope persistence fails after the inert grant write, the
underlying grant remains unusable by official v0.8 dispatch because no verified
signed envelope exists.

The reverse ordering could leave a signed envelope apparently authoritative
while its underlying v0.6 grant persistence failed; v0.8 avoids that state.

## Operator commands

### Effective authenticated-authority status

```bash
phi agents reflex-authority status
```

This returns the effective runtime status plus:

- trust anchors;
- authenticated signed grants;
- revocations;
- `control_sha256`.

### Install local trust anchor

```bash
phi agents reflex-authority trust-ingest anchor.json --yes
```

Optional stale-state guard:

```bash
phi agents reflex-authority trust-ingest anchor.json --yes \
  --expect-control-sha <sha256>
```

### Ingest signed activation grant

```bash
phi agents reflex-authority grant-ingest signed-grant.json
```

or:

```bash
phi agents reflex-authority grant-ingest signed-grant.json \
  --expect-control-sha <sha256>
```

### Activate authenticated authority

```bash
phi agents reflex-authority activate \
  --request activation-request.json \
  --grant-id grant-001 \
  --yes
```

An optional v0.7 lease may still narrow runtime lifetime:

```bash
phi agents reflex-authority activate \
  --request activation-request.json \
  --grant-id grant-001 \
  --lease-until-epoch 1800000000 \
  --yes
```

### Ingest authenticated revocation

```bash
phi agents reflex-authority revoke revocation.json
```

If effective immediately and currently active, routing privilege collapses
during the same operation.

### Manual collapse

```bash
phi agents reflex-authority deactivate \
  --reason operator-stop
```

No signature is required to reduce privilege.

## Interaction with normal dispatch

Normal:

```bash
phi dispatch ...
```

uses `ReflexAuthorityPlane` before restoring live routing influence.

The path is:

```text
v0.7 persisted control state
        ↓
v0.8 authenticated grant enforcement
        ↓
signature + issuer + validity + revocation checks
        ↓
v0.6 bounded runtime evaluation
        ↓
context.reflex_influence
```

If authenticated authority fails:

```text
no live signal
→ ordinary dispatch
```

The existing v0.2 live/shadow contamination firewall remains in force.

## Authority boundary

v0.8 authenticates **routing influence authority** only.

Even an authenticated, active grant cannot create:

```text
promotion_authority
action_authority
execution_authority
```

It cannot:

- issue itself a signature;
- create a trust anchor automatically;
- widen provider/model scope;
- increase adopted weight;
- add influence dimensions;
- authorize tools;
- execute tools;
- bypass CAPS;
- bypass Spine execution permission.

## Tests

v0.8 tests verify:

- valid Ed25519 grant authentication;
- forged signature rejection;
- issuer/authority-source binding;
- signed grant expiration;
- immediate signed revocation collapse;
- future-dated revocation enforcement at the effective epoch;
- legacy unsigned active grants collapse under v0.8 enforcement;
- stale `control_sha256` CAS rejection;
- conflicting trust anchors are rejected;
- authority-store corruption collapses persisted live influence;
- cross-process file locking serializes separate processes;
- file lock re-entrancy within one control-plane instance;
- signed shell grant/trust/request ingestion;
- unsigned shell expansion paths are disabled;
- ordinary dispatch restores only authenticated live influence;
- live authenticated influence still cannot be measured as clean shadow data.

## Next rung

The next rung should improve root-of-trust lifecycle and durable attestation
rather than widening routing influence.

Possible v0.9 work:

- signed trust-anchor rotation and disablement;
- hardware-backed or OS-keystore public-key pinning;
- signed ledger checkpoints;
- remote or offline ledger attestation;
- authenticated provider-adapter manifests;
- grant-use counters or one-shot grants;
- explicit signed lease-renewal authority;
- recovery tooling for operator-approved trust-store replacement.

The planner influence surface should remain exactly as narrow as v0.6 until
those guarantees are proven.
