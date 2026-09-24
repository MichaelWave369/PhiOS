# PhiOS AuthorityEpoch v0.1

## Status

Architecture contract candidate.

Schema:

- `phios.authority_epoch.v0.1`

Primary rule:

```text
AUTHORITY STATE != ACTION LEASE != EXECUTION
```

## Purpose

`AuthorityEpoch` records one exact reconstructed authority state for one
principal under one policy and one known authoritative event set.

It answers:

> Under which exact authority state was a later decision, lease, or action
> evaluated?

It does not itself grant permission and cannot be presented as an execution
credential.

## Relationship to existing authority replay

PhiOS already has `AuthorityProjection`, which deterministically replays
authoritative grant and revoke events under a frozen permission ceiling.

`AuthorityEpoch` does not replace that logic.

It wraps one exact projection with the additional identity needed by later
governed-execution layers:

```text
authoritative grant/revoke events
          ↓
AuthorityProjection
          ↓
effective ceiling + grants
          ↓
AuthorityEpoch
```

The projection remains the authority-state reconstruction mechanism.

## Bound identity

The epoch binds:

- principal identity;
- canonical observation time;
- policy SHA-256;
- frozen authority ceiling;
- effective grants at the observation point;
- authority source identities;
- all known event IDs;
- applied event IDs;
- currently active grant event IDs;
- canonical source-event digest;
- grant-set digest;
- revocation-set digest;
- projection digest;
- canonical authority-context digest;
- the next transition already known from the supplied event set.

All fields participate in the final:

```text
authority_epoch_sha256
```

Changing the principal, policy, known grants, known revocations, projection, or
effective authority context therefore changes epoch identity.

## Known future authority changes

The underlying projection intentionally receives the complete supplied event
set, including future-scheduled events.

The epoch therefore records:

```text
next_known_transition_at
```

as the earliest known future point at which the authority state may change due
to:

- a future authoritative event becoming effective; or
- expiration of a currently active grant.

This is deliberately named **next known transition**, not `valid_until`.

A later event can always be added after the snapshot was created. Therefore:

```text
no known future transition != permanent authority
```

A future ActionLease must still re-check that the current authority epoch
matches the epoch to which the lease was bound.

## Grant and revocation set digests

`grant_set_sha256` and `revocation_set_sha256` cover the canonical supplied
grant and revoke event sets respectively.

These sets include known future-scheduled events because scheduled authority
changes are part of the authority context known at snapshot time.

The effective `grants` field remains present-tense and comes directly from
`AuthorityProjection`.

This distinguishes:

```text
known authority history / schedule
              !=
effective authority right now
```

## Principal binding

The same reconstructed grants under the same event history but for a different
principal produce a different epoch.

This is required so a later scoped lease cannot detach authority state from the
identity for whom that state was evaluated.

## Policy binding

`policy_sha256` is mandatory.

The same event set under a changed authority policy is a different epoch even
when the currently effective permission names happen to be identical.

This prevents a future lease from silently surviving a policy replacement just
because the visible grant tuple did not change.

## Zero delegated authority

The epoch fixes:

```text
effect_performed = false
operational_authority = false
action_authority = false
execution_authority = false
```

The `grants` field is reconstructed authority-state evidence.

The object itself is not a grant.

That distinction is intentional:

```text
AuthorityEpoch says:
"this was the authority state"

ActionLease will say:
"this exact action may proceed under that exact authority state"
```

## Expected next layer

The intended next relationship is:

```text
EvidenceRef(s)
      +
EffectIntent
      +
EnforcementProfile
      +
AuthorityEpoch
      ↓
ActionLease
```

The lease should be narrower than the epoch.

It should bind one exact intent, principal, authority epoch, enforcement
profile, scope, and lifetime rather than turning an authority snapshot into a
general bearer token.

## What v0.1 does not do

This PR does not:

- replace `AuthorityProjection`;
- change existing grant or revocation behavior;
- alter Reflex authenticated authority;
- change the Spine permission gate;
- change action binding;
- grant action authority;
- grant execution authority;
- create a bearer credential;
- create an ActionLease;
- execute any effect.

It only makes the authority state itself canonical and content-addressable so
later execution authority can be scoped against an exact snapshot rather than
an informal collection of current permissions.
