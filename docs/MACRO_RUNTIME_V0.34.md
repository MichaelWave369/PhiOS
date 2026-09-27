# Macro Runtime v0.34 — Ghost-Walk ActionLease Boundary

Macro Runtime v0.34 advances the Ghost-Walk chain from an exact executable
binding into a bounded, current `ActionLease` without adding execution.

The hard boundary is:

```text
EXECUTABLE BINDING
!= ENFORCEMENT PROFILE
!= CURRENT AUTHORITY EPOCH
!= ACTION LEASE
!= EXECUTION
```

## Purpose

v0.33 produced a content-addressed `GhostWalkExecutableBinding` with an exact
capability, payload, required permission set, declared effects, and
`EffectIntent`. That object deliberately carried zero action or execution
authority.

v0.34 answers the next question:

> Under the current locally reconstructed authority state and an explicit
> server-owned enforcement policy, is this exact binding eligible to receive
> one bounded action-authority lease?

If every precondition passes, PhiOS may issue one single-use `ActionLease`.
The lease still carries **no execution authority** and performs no effect.

## New contracts

### GhostWalkLeasePolicy

A `GhostWalkLeasePolicy` is server-owned configuration for one exact
capability/version/effect/permission shape.

It binds:

- principal identity;
- lease issuer identity;
- exact capability ID/version;
- exact authorized permission set;
- exact declared effects;
- explicit `EnforcementRule` set;
- exact acknowledgement of effects lacking an enforced rule;
- a bounded maximum lease lifetime.

It carries no action authority, execution authority, or performed effect.

There is intentionally **no permissive default policy**. A capability with no
matching policy is held at `LEASE_POLICY_MISSING`.

### EnforcementProfile

The lease service builds the canonical `EnforcementProfile` from the binding's
exact `EffectIntent` and the server-owned policy rules.

Issuance is held when:

- any declared effect is unmapped;
- the profile cannot be constructed;
- the policy's acknowledged unenforced effects differ from the profile's exact
  `effects_without_enforced_rule` set.

`mapping_complete` means every declared effect has an explicit rule. It does
not imply every effect is enforced.

### Current AuthorityEpoch

The service consumes a trusted local `AuthorityEpoch` provider.

The epoch must:

- exist;
- describe the policy principal;
- not claim an observation from the future;
- remain before its next known authority transition;
- contain every permission required by the executable binding.

The AuthorityEpoch's own `policy_sha256` remains the identity of the authority
projection policy. It is **not** conflated with the Ghost-Walk lease-policy
digest.

### GhostWalkLeaseReadiness

Readiness is a zero-authority descriptive receipt.

Possible reasons include:

- `READY`
- `EXECUTABLE_BINDING_REQUIRED`
- `EXECUTABLE_BINDING_STALE`
- `LEASE_POLICY_MISSING`
- `ENFORCEMENT_PROFILE_INCOMPLETE`
- `UNENFORCED_EFFECT_ACK_REQUIRED`
- `AUTHORITY_EPOCH_UNAVAILABLE`
- `AUTHORITY_EPOCH_STALE`
- `AUTHORITY_PRINCIPAL_MISMATCH`
- `AUTHORITY_PERMISSION_MISSING`
- `LEASE_ALREADY_EXISTS`

Readiness never performs an effect and never carries action or execution
authority.

### GhostWalkActionLeaseRecord

Successful issuance persists an immutable custody record binding:

- the Ghost-Walk target inference;
- the exact executable-binding digest;
- the exact server-owned lease-policy digest;
- the full canonical EnforcementProfile;
- the full canonical AuthorityEpoch;
- the full canonical ActionLease;
- issuance time.

The nested `ActionLease` carries bounded action authority. The custody record
itself carries no execution authority and cannot claim an effect occurred.

Persisted records are parsed and hash-verified before use. Tampering fails
closed.

## Issuance boundary

The caller does **not** provide:

- a new action payload;
- permission names;
- effects;
- enforcement rules;
- accepted unenforced effects;
- principal identity;
- issuer identity;
- lease duration;
- authority state.

The issuance request may only echo current content-addressed identities for
optimistic concurrency:

```text
target_inference_receipt_sha256
expected_executable_binding_sha256
expected_policy_sha256
expected_policy_set_sha256
expected_enforcement_profile_sha256
expected_authority_epoch_sha256
```

PhiOS recomputes the trusted state under the lock before issuing the lease.

## Lease lifetime

v0.34 uses the existing `ActionLease v0.1` contract:

- single use only;
- bounded validity interval;
- cannot outlive the next known authority transition;
- action authority only;
- `execution_authority = false`;
- `effect_performed = false`.

The server-owned policy additionally limits the requested lifetime to at most
300 seconds. A shorter known authority transition wins.

## Ledger custody

Reality Ledger gains:

- `append_ghostwalk_action_lease_record(...)`
- `ghostwalk_action_lease_records(...)`

Records are stored in append-only
`ghostwalk-action-lease-records.jsonl`.

One executable binding may produce at most one ActionLease record. Historical
records for a Ghost-Walk target may coexist across later bindings.

## What v0.34 does not do

This release does **not**:

- click the desktop;
- dispatch the bound capability;
- consume a lease;
- mint execution authority;
- expose a browser/model lease policy;
- allow a caller to rebind a lease to a fresh action;
- add a PhiVessel execute endpoint.

That last boundary is deliberate.

## Relationship to Vessie

PhiVessel can eventually use a very small client surface:

```text
observe(...)                          -> ObservationReceipt
propose(workId, packetRefs, type)     -> ProposalPacket
execute(leaseId)                      -> ExecutionReceipt
```

But `execute(leaseId)` must not exist until PhiOS has a governed execution
handoff that:

1. accepts only the existing lease identity, never a fresh action;
2. re-evaluates lease currency against the current AuthorityEpoch;
3. verifies the lease has not been consumed;
4. resolves the exact bound capability/payload from PhiOS custody;
5. executes only through the capability's enforcement boundary;
6. records consumption and post-action evidence.

Vessie may never mint, expand, renew, infer, rebind, or transfer a lease.

## Next rung

The next Macro Runtime rung should be the **lease-consuming execution handoff**,
not another planning or UI layer.

That handoff should implement the invariant:

```text
ACTION LEASE != EXECUTION
EXECUTION REQUIRES CURRENT LEASE VALIDATION + EXACT BINDING REPLAY
```

Only after that boundary is green should the Vessie ↔ PhiOS bridge expose
`execute(leaseId)`.
