# PhiReflex v0.9 — Trust Lifecycle and Attestation

## Status

PhiReflex v0.9 governs the lifetime of authenticated routing authority.

The central rule is:

```text
authenticated once
!=
trusted forever
```

v0.9 composes on top of v0.8. It does not widen the v0.6 routing surface and it does not add action or execution authority.

## New signed authority purposes

v0.9 adds five purpose-scoped signed artifacts:

```text
trust_transition
ledger_checkpoint
grant_use_policy
provider_manifest
lease_renewal
```

A trusted key may authorize only purposes explicitly listed in its trust anchor.

## Signed trust transitions

A `ReflexTrustTransition` may:

```text
ROTATE
DISABLE
```

It binds:

- transition ID;
- issuer ID;
- signing key ID;
- issue epoch;
- effective epoch;
- reason;
- optional replacement trust anchor;
- Ed25519 signature;
- envelope SHA-256.

### Rotation

`ROTATE` requires a replacement key for the same issuer.

When the transition becomes effective:

```text
old key
→ retired for live authority

replacement key
→ materialized as trusted successor
```

Historical receipts remain historical evidence. Live grants signed by the retired key no longer satisfy runtime authority.

If the retired key backs the current live activation, routing influence collapses.

### Disablement

`DISABLE` retires a key without installing a successor.

Privilege may collapse immediately; no replacement authority is inferred.

## Authenticated provider manifests

Live routing now requires a signed `ReflexProviderManifest` matching:

- authenticated grant issuer;
- provider;
- exact model set;
- adapter ID;
- adapter version;
- effective epoch;
- optional expiration epoch.

The Jev runtime adapter identifies itself as:

```text
adapter_id = phios.reflex.providers.jev:JevReflexProvider
adapter_version = 0.9
```

A provider name alone is no longer sufficient for v0.9 live activation.

If a previously valid manifest expires or no longer matches the runtime adapter, live influence collapses.

## Grant-use limits

v0.9 requires an authenticated `ReflexGrantUsePolicy` before lifecycle-governed activation.

The policy binds an exact authenticated grant SHA and a positive:

```text
max_activations
```

Each successful activation increments a deterministic persisted usage counter.

Therefore a one-shot grant is simply:

```text
max_activations = 1
```

A second activation attempt is rejected before the lower activation layer mutates state.

A later use policy may reduce the maximum but may not increase it.

## Signed lease renewal

v0.7 allowed leases to shorten but not extend.

v0.9 adds the only supported lease-extension path:

```text
signed ReflexLeaseRenewal
```

The renewal binds:

- issuer/key;
- exact active grant SHA;
- exact activation-state SHA;
- exact current lease SHA;
- new deadline;
- issue epoch;
- Ed25519 signature.

The renewal must come from the same authenticated issuer as the active grant.

Only after verification does v0.9 call the v0.7 authorized-renewal seam.

This preserves:

```text
ordinary lease operation
→ may only reduce privilege duration

signed lease-renewal authority
→ may explicitly extend it
```

## Signed runtime-ledger checkpoints

A `ReflexLedgerCheckpoint` binds:

- checkpoint ID;
- issuer/key;
- creation epoch;
- exact ledger entry count;
- exact ledger-head SHA;
- exact v0.8 `control_sha256`;
- Ed25519 signature.

Checkpoint ingestion succeeds only when the signed view exactly matches current runtime state.

The checkpoint is an attestation of a specific observed state, not permission to mutate that state.

## Lifecycle-gated activation

Direct v0.8 activation is no longer the official live path.

The lifecycle activation path requires:

1. valid v0.8 signed activation grant;
2. live signing key under v0.9 trust lifecycle;
3. effective authenticated grant-use policy;
4. remaining activation use;
5. effective authenticated provider manifest matching provider/model/adapter;
6. all existing v0.8 policy, signature, validity, revocation, and CAS checks.

Only then may the existing bounded v0.6 routing surface become live.

## Normal dispatch

Normal:

```bash
phi dispatch ...
```

now evaluates live Reflex authority through:

```text
v0.7 persisted runtime
↓
v0.8 authenticated grant / revocation
↓
v0.9 key lifecycle
↓
v0.9 provider manifest
↓
v0.6 bounded planner influence
```

If lifecycle enforcement fails, no Reflex influence signal reaches the planner.

The ordinary dispatch path remains the fallback.

## Operator commands

Status:

```bash
phi agents reflex-lifecycle status
```

Ingest signed trust transition:

```bash
phi agents reflex-lifecycle trust-transition transition.json
```

Ingest signed grant-use policy:

```bash
phi agents reflex-lifecycle use-policy policy.json
```

Ingest signed provider manifest:

```bash
phi agents reflex-lifecycle provider-manifest manifest.json
```

Activate under v0.9 lifecycle governance:

```bash
phi agents reflex-lifecycle activate \
  --request request.json \
  --grant-id grant-001 \
  --yes
```

Ingest signed runtime-ledger checkpoint:

```bash
phi agents reflex-lifecycle checkpoint checkpoint.json
```

Apply signed lease renewal:

```bash
phi agents reflex-lifecycle lease-renew renewal.json
```

Privilege collapse remains available through the existing authority/runtime deactivation commands and never requires an expansion signature.

## Authority boundary

v0.9 can govern authenticated routing influence only.

Even when every lifecycle artifact validates:

```text
routing_influence_authority = true
action_authority = false
execution_authority = false
promotion_authority = false
```

v0.9 cannot:

- sign its own authority;
- create private keys;
- increase a grant-use limit through a replacement policy;
- accept a retired signing key for live authority;
- infer a provider adapter from provider name alone;
- renew a lease without an exact signed renewal artifact;
- grant tools;
- execute tools;
- bypass CAPS;
- bypass Spine execution permission.

## Tests

v0.9 tests verify:

- activation requires both authenticated provider manifest and grant-use policy;
- one-shot grant limits reject a second activation before lower-layer mutation;
- effective key rotation collapses live authority from the retired key;
- expired provider manifests collapse live influence;
- signed ledger checkpoints must match exact ledger head and control fingerprint;
- signed lease renewal binds exact active activation and current lease;
- wrong adapter manifests cannot authorize activation;
- normal shell dispatch uses the v0.9 lifecycle plane;
- direct v0.8 activation is disabled in favor of lifecycle-governed activation.

## Next rung

The next useful rung should focus on stronger durable trust storage and external attestation rather than broader routing influence.

Candidates for v0.10:

- OS-keystore or hardware-backed trust-anchor pinning;
- signed trust-transition chains with explicit recovery roots;
- checkpoint export / offline verification;
- one-shot nonce grants;
- provider package or binary digests inside manifests;
- signed revocation/rotation recovery bundles;
- cross-machine authority replication with conflict receipts.

The live routing surface should remain narrow until those roots of trust are hardened.
