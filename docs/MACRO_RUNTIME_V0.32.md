# Macro Runtime v0.32 — Ghost-Walk AuthorizationDecision

v0.32 adds an immutable, append-only explicit authorization-decision artifact
between one exact current `AuthorityRequest` and any future executable binding.

Core rule:

```text
APPROVAL DECISION
!=
CAPABILITY BINDING
!=
ACTIONLEASE
!=
EXECUTION
```

## Architecture position

```text
machine candidate
    ↓
human annotation
    ↓
accepted intent
    ↓
policy admission
    ↓
AuthorityRequest
    ↓
AuthorizationDecision
    ↓
future effect/capability binding
    ↓
ActionLease
    ↓
governed execution
```

v0.32 stops at `AuthorizationDecision`.

It does not create an `EffectIntent`, `EnforcementProfile`,
`AuthorityEpoch`, capability binding, `ActionLease`, execution handoff, or
desktop effect.

## Decisions

The decision vocabulary is deliberately small:

```text
APPROVE
DENY
HOLD
```

`APPROVE` records that the exact semantic authority request was explicitly
approved.

It fixes:

```text
authorization_granted      = true
request_resolved           = true
capability_binding_created = false
action_lease_created       = false
effect_performed           = false

policy_authority           = false
operational_authority      = false
action_authority           = false
execution_authority        = false
```

Approval is therefore evidence for a later authority-construction step, not a
bearer credential.

`DENY` is terminal for that exact request and records no authorization.

`HOLD` is non-terminal. A later decision may be appended for the same request
if the underlying request is still current.

## Currentness gate

An AuthorityRequest is authorizable only while the v0.31 request service still
projects that exact request as the current request for the current accepted
intent, policy profile, and `ALLOW_REQUEST` admission evidence.

If human interpretation, accepted intent, policy, or admission state changes so
that the request is no longer current, v0.32 reports:

```text
AUTHORITY_REQUEST_STALE
```

and refuses to record another decision.

This prevents an old approval flow from being applied to newer human or policy
state.

## Append-only history

Authorization decisions form one immutable chain per AuthorityRequest:

```text
decision_sequence = 0
previous_decision_sha256 = null

decision_sequence = 1
previous_decision_sha256 = <decision 0 hash>
...
```

A HOLD may be followed by another HOLD, APPROVE, or DENY.

No decision may follow terminal APPROVE or DENY.

## Bound identity

Each decision binds:

- exact AuthorityRequest SHA-256
- exact transition-inference receipt SHA-256
- exact admission receipt SHA-256
- exact accepted-intent revision SHA-256
- exact policy-profile SHA-256
- exact semantic intent code
- server-owned authorizer identity
- decision kind
- contiguous sequence
- previous-decision digest
- decision timestamp
- optional operator note
- explicit zero capability/action/execution authority

All fields participate in:

```text
authorization_decision_sha256
```

## Optimistic concurrency

Recording a decision requires the caller to provide:

```text
expected_authority_request_sha256
expected_previous_decision_sha256
```

Both must still match at commit time.

This makes two simultaneous decisions fail closed instead of silently creating
a forked authorization history.

## Ledger

Decisions are persisted append-only in:

```text
ghostwalk-authorization-decisions.jsonl
```

The v0.31 AuthorityRequest is never rewritten.

## Readiness states

```text
READY
AUTHORITY_REQUEST_REQUIRED
AUTHORITY_REQUEST_STALE
DECISION_FINAL
```

`READY` is the only state in which another decision may be recorded.

## Boundary

v0.32 intentionally does not answer:

```text
Which capability should execute this intent?
What exact payload should it receive?
What effects will that payload declare?
Which permissions are needed?
Which enforcement profile applies?
Which AuthorityEpoch is current?
Can an ActionLease be issued?
```

Those questions belong to the next governed bridge.

## Next rung

v0.33 should introduce a deterministic **effect/capability binding** from an
APPROVE AuthorizationDecision to one exact executable representation.

That rung should reuse the existing PhiOS primitives:

```text
AuthorizationDecision(APPROVE)
    ↓
capability mapping
    ↓
EffectIntent
    ↓
EnforcementProfile
    ↓
AuthorityEpoch
    ↓
ActionLease issuance
```

and should fail closed when:

- no approved mapping exists for the semantic intent
- payload construction is ambiguous
- declared effects are incomplete
- enforcement mapping is incomplete
- required permissions exceed the current AuthorityEpoch
- the authorization decision or any upstream evidence is stale

The law remains:

```text
CAPABILITY != AUTHORITY
APPROVAL != LEASE
LEASE != EXECUTION
```
