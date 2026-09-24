# PhiOS ActionLease Runtime Handoff v0.1

## Status

Runtime integration candidate.

Primary rule:

```text
LEASE ACCEPTED != EXECUTOR ENTERED != EFFECT CONFIRMED
```

## Purpose

This integration connects `ActionLease v0.1` to the existing
`GovernedExecutionHandoff` without weakening the existing plan, capability,
permission, effect, binding-replay, or executor checks.

The leased handoff performs four additional jobs before delegating to the
existing handoff:

1. verify that external lease-verification evidence matches the lease;
2. verify that the lease scope matches the current action binding;
3. re-evaluate the lease against the current AuthorityEpoch and time;
4. atomically reserve the single-use lease.

Only then does the existing governed execution handoff run.

## Runtime flow

```text
ActionLease
    +
external lease-verification evidence
    +
current AuthorityEpoch digest
    +
current binding/payload
          ↓
leased runtime gate
          ↓
single-use lease claim
          ↓
existing GovernedExecutionHandoff
          ↓
existing effect boundary
          ↓
existing permission gate
          ↓
executor
          ↓
RealityLedger receipt
```

The old handoff remains intact and continues to perform its existing checks.

## External lease verification

`LeaseVerificationEvidence` records the result of an external configured
verification step.

It binds:

- the exact ActionLease digest;
- the expected issuer ID;
- the exact authorization-receipt digest;
- the verifier identity;
- the verifier's receipt digest;
- whether the verification was accepted.

The runtime requires all bound values to match the lease before proceeding.

Important:

```text
LeaseVerificationEvidence != cryptographic verification implementation
```

This integration does not invent a cryptographic verifier. The evidence object
records the result supplied by one.

Because PhiOS is still running in one Python process in many configurations,
the object itself is not treated as a Linux security boundary.

## Scope validation

Before claiming the lease, the runtime requires the lease to match the current
action binding on:

- capability ID;
- capability version;
- exact payload digest;
- canonical declared effects;
- canonical permission scope.

A lease for one capability or payload cannot be replayed against another
binding.

## Authority currency

The leased handoff calls the existing pure
`evaluate_action_lease()` function using:

- the current time;
- the current AuthorityEpoch digest;
- durable lease-consumption state.

A changed AuthorityEpoch therefore invalidates a lease before execution even
when the lease wall-clock expiry has not been reached.

## Atomic single-use claim

The Reality Ledger now supports a dedicated ActionLease claim directory.

The claim uses create-exclusive filesystem semantics, matching the existing
binding-claim strategy:

```text
action-lease-claims/<lease_sha256>.claim
```

Two concurrent attempts cannot both reserve the same lease.

The lease claim is released only when the existing governed handoff proves that
the executor was not entered.

Examples where the lease remains reusable:

- Spine permission denial;
- capability drift held before execution;
- effect-boundary hold;
- other pre-executor HELD outcomes.

Examples where the lease is consumed:

- executor succeeded;
- executor failed after entry.

This mirrors the existing binding rule that an uncertain or failed effecting
attempt must not be blindly retried.

## Durable consumption

`ExecutionProvenance` now optionally carries:

- `action_lease_sha256`;
- `authority_epoch_sha256`;
- `authorization_receipt_sha256`;
- `lease_verification_sha256`.

The Reality Ledger considers a lease consumed when a matching provenance record
shows:

```text
permission_status = allowed
execution_status in {succeeded, failed}
```

Therefore single-use consumption survives process restart because it can be
reconstructed from the append-only execution ledger.

The claim file provides concurrency exclusion while the ledger provides the
durable consumed-state record.

## Existing checks remain authoritative

The lease does not bypass:

- current plan validation;
- action-binding validation;
- payload digest checks;
- capability registration;
- capability contract drift checks;
- executor effect-contract checks;
- EffectBoundaryPolicy;
- existing binding replay protection;
- the Spine PermissionGate.

This matters because:

```text
lease permission != runtime permission bypass
```

The lease adds a narrower authorization condition. It does not remove existing
ones.

## Runtime receipt

`LeasedExecutionHandoffReceipt` records:

- the ActionLease digest;
- the current AuthorityEpoch digest;
- lease-verification evidence digest;
- the pure lease evaluation;
- whether the lease was claimed;
- whether the lease was consumed;
- replay status;
- the complete existing inner handoff receipt.

The wrapper receipt itself carries no authority and makes no independent claim
that an effect occurred:

```text
action_authority = false
execution_authority = false
effect_performed = false
```

The actual execution result remains in the existing Spine and handoff receipts.

## Failure behavior

Fail-closed reasons introduced at this layer include:

```text
lease_authorization_not_verified
lease_verification_scope_mismatch
lease_issuer_verification_mismatch
lease_authorization_receipt_verification_mismatch
lease_capability_scope_mismatch
lease_capability_version_scope_mismatch
lease_payload_scope_mismatch
lease_effect_scope_mismatch
lease_permission_scope_mismatch
authority_epoch_changed
lease_not_yet_valid
lease_expired
lease_consumed
lease_execution_claim_unavailable
```

None of these conditions enter the executor.

## What v0.1 does not do

This integration does not:

- implement cryptographic lease issuer verification;
- change ActionBindingGrant;
- remove the existing binding claim;
- replace the Spine permission gate;
- replace the effect boundary;
- define multi-use leases;
- define distributed lease consumption;
- define external-system reconciliation;
- claim that successful executor return proves every external effect completed.

The next architecture rung should introduce an explicit execution-attempt /
outcome state model so PhiOS can distinguish:

```text
not attempted
attempt started
succeeded
failed
outcome unknown
reconciliation required
```

without collapsing those states into one Boolean.
