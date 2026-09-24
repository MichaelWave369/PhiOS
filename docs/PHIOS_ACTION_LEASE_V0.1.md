# PhiOS ActionLease v0.1

## Status

Architecture contract candidate.

Schemas:

- `phios.action_lease.v0.1`
- `phios.action_lease_evaluation.v0.1`

Primary rule:

```text
BOUNDED ACTION AUTHORITY != EXECUTION AUTHORITY
```

## Purpose

`ActionLease` is the first PhiOS primitive in this architecture sequence that
carries affirmative action authority.

It binds one explicit authorization decision to:

- one principal;
- one exact `EffectIntent`;
- one exact `EnforcementProfile`;
- one exact `AuthorityEpoch`;
- one bounded permission set;
- one bounded time window;
- one single use in v0.1.

It does not execute the action.

## Architecture position

The intended chain is now:

```text
EvidenceRef(s)
      ↓
EffectIntent
      ↓
EnforcementProfile
      ↓
AuthorityEpoch
      ↓
explicit authorization decision
      ↓
ActionLease
      ↓
future governed execution handoff
      ↓
ExecutionOutcome
```

The lease is narrower than every authority source above it.

## Bound identity

The lease binds:

- `principal_id`;
- `issuer_id`;
- `authorization_receipt_sha256`;
- `effect_intent_sha256`;
- `enforcement_profile_sha256`;
- `authority_epoch_sha256`;
- capability ID and version;
- exact payload SHA-256;
- declared effects;
- explicitly authorized permissions;
- explicitly accepted unenforced effects;
- issue time;
- validity start;
- validity end;
- use count ceiling.

All fields participate in:

```text
action_lease_sha256
```

Changing the payload, authority epoch, enforcement map, issuer decision, time
window, or permission scope therefore changes lease identity.

## Authority semantics

The v0.1 lease fixes:

```text
operational_authority = false
action_authority = true
execution_authority = false
effect_performed = false
```

This is deliberate.

The lease says:

> This exact action is authorized within this exact bounded scope.

It does not say:

> The runtime has executed it.

Execution authority remains a later runtime decision that must re-check the
lease and all current execution boundaries.

## Explicit issuance decision

The lease requires:

```text
issuer_id
authorization_receipt_sha256
```

The authorization receipt is the external evidence that a decision to issue the
lease occurred.

The v0.1 contract binds that receipt digest but does **not** define a
cryptographic issuer-verification protocol. Merely parsing a structurally valid
lease is therefore not sufficient for a future executor to trust it.

A runtime integration must verify the configured issuer and authorization
receipt before treating the lease as accepted authority.

This distinction matters because the Python object itself is not a security
boundary.

## EffectIntent binding

The supplied `EnforcementProfile` must bind the exact supplied
`EffectIntent`.

A lease cannot be issued when the enforcement profile contains unmapped
effects.

This prevents an action lease from authorizing an effect that has never even
been classified against the current trust map.

## Unenforced effects

A complete enforcement map can still contain effects that have no enforced
rule.

PhiOS therefore does **not** silently equate:

```text
mapping_complete == all_effects_enforced
```

If an effect is mapped but not enforced, lease issuance requires that effect to
appear in:

```text
accepted_unenforced_effects
```

and the acknowledged set must exactly match the profile's
`effects_without_enforced_rule`.

Example:

```text
filesystem.change    enforced
network.request      not_enforced
```

A lease may only be issued if the authorization decision explicitly accepts:

```text
accepted_unenforced_effects = ["network.request"]
```

This does not upgrade network enforcement. It records that the authority
issuer knowingly accepted the mapped gap for this lease.

## Permission ceiling

`permissions_authorized` must be non-empty and must remain a subset of the
effective grants recorded by the bound `AuthorityEpoch`.

Therefore:

```text
lease permissions <= epoch grants <= frozen authority ceiling
```

The lease cannot widen authority beyond the reconstructed epoch.

## Time bounds

The lease requires:

```text
issued_at <= valid_from < valid_until
```

The lease cannot be issued before the bound AuthorityEpoch was observed.

If the epoch has a:

```text
next_known_transition_at
```

the lease cannot extend beyond that transition.

This prevents a lease from knowingly surviving a scheduled grant expiry,
scheduled revocation-equivalent transition, or other already-known authority
change.

A later, previously unknown authority change still requires runtime epoch
revalidation.

## Single-use semantics

ActionLease v0.1 requires:

```text
max_uses = 1
```

Multi-use leases are intentionally deferred.

The lease object itself does not mutate when consumed. Consumption state is
external runtime state and will belong to the governed execution integration.

This keeps the lease immutable and content-addressed.

## Pure evaluation

`evaluate_action_lease()` performs a side-effect-free currency check using:

- current time;
- current AuthorityEpoch digest;
- externally supplied uses-consumed count.

The evaluation can return:

```text
lease_current
authority_epoch_changed
lease_not_yet_valid
lease_expired
lease_consumed
```

A usable evaluation carries bounded action authority but still fixes:

```text
execution_authority = false
effect_performed = false
```

The evaluator cannot execute anything.

## Why the current AuthorityEpoch digest is required

A lease is scoped to one exact authority snapshot.

Even if its wall-clock expiry has not arrived, the lease becomes unusable when:

```text
current_authority_epoch_sha256
    !=
lease.authority_epoch_sha256
```

This gives future revocation and policy changes a clean invalidation path
without editing the immutable lease.

## What v0.1 does not do

This PR does not:

- change existing `ActionBindingGrant` behavior;
- replace governed action binding;
- modify the Spine permission gate;
- modify the governed execution handoff;
- persist lease consumption;
- authenticate lease issuers;
- verify authorization receipts cryptographically;
- create multi-use leases;
- grant execution authority;
- execute effects.

The next integration rung should connect this lease to the existing governed
execution handoff and consumption ledger while preserving the current
fail-closed effect and permission checks.
