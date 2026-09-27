# Macro Runtime v0.30 — Ghost-Walk Policy Admission

v0.30 introduces a distinct fail-closed policy-admission layer between typed
accepted intent and any future authority request.

Core rule:

```text
ACCEPTED INTENT
!=
POLICY ADMISSION
!=
AUTHORITY REQUEST
!=
ACTIONLEASE
!=
EXECUTION
```

## Purpose

v0.29 can prove what the human says a demonstration means.

v0.30 answers a different question:

> Under the currently loaded server-side policy, is this exact accepted intent
> eligible to proceed to a later authority-request step?

It does not create authority.

## Decisions

Policy admission has exactly three decisions:

```text
ALLOW_REQUEST
HOLD
DENY
```

Semantics:

- `ALLOW_REQUEST`: eligible to create a later authority request
- `HOLD`: insufficient/currently stale/unmapped evidence
- `DENY`: policy explicitly denies this intent code

`ALLOW_REQUEST` is intentionally named narrowly.

It does not mean:

```text
AUTHORIZED
LEASED
EXECUTABLE
EXECUTED
```

## Server-owned policy

The browser cannot edit policy.

The Ghost-Walk sidecar loads policy from server/runtime configuration:

```text
PHIOS_GHOSTWALK_POLICY_ALLOW_REQUEST
PHIOS_GHOSTWALK_POLICY_DENY
```

Both values are optional comma-separated canonical intent codes.

Example:

```powershell
$env:PHIOS_GHOSTWALK_POLICY_ALLOW_REQUEST="OPEN_NETWORK_ADAPTER_PROPERTIES,OPEN_NETWORK_SETTINGS"
$env:PHIOS_GHOSTWALK_POLICY_DENY="TOGGLE_AIRPLANE_MODE"
```

The default for any unmapped intent is always:

```text
HOLD
```

An empty policy therefore permits no authority requests.

## Policy profile

`GhostWalkPolicyProfile` binds:

- profile identity
- sorted unique allow-request intent-code set
- sorted unique deny intent-code set
- default HOLD decision
- zero authority flags

The allow and deny sets may not overlap.

Its canonical identity is:

```text
profile_sha256
```

Policy configuration therefore becomes explicit evidence rather than invisible
application state.

## Admission evidence

The read-only projection binds:

- transition-inference receipt SHA-256
- current accepted-intent revision SHA-256
- accepted intent family/code/status
- exact OperatorLog revision originally used for acceptance
- exact current OperatorLog revision
- whether the OperatorLog binding is current
- exact policy profile SHA-256
- decision
- reason
- authority-request eligibility

Its identity is:

```text
projection_sha256
```

The projection always asserts:

```text
effect_performed       = false
policy_authority       = false
operational_authority  = false
action_authority       = false
execution_authority    = false
```

## Decision precedence

v0.30 evaluates in this order:

```text
accepted intent REVOKED
    -> HOLD

current OperatorLog RETRACTED
    -> HOLD

accepted intent bound to older OperatorLog revision
    -> HOLD

intent explicitly denied
    -> DENY

intent explicitly allow-request listed
    -> ALLOW_REQUEST

otherwise
    -> HOLD
```

This means an allow-listed code cannot bypass stale or retracted human evidence.

## Recorded admission receipt

PhiShell can explicitly record the current admission result.

The request binds:

```text
target_inference_receipt_sha256
expected_accepted_intent_revision_sha256
expected_policy_profile_sha256
```

Before persistence, the runtime recomputes the projection and rejects changes to
the accepted intent or policy profile.

The persisted receipt records:

- projection SHA-256
- exact accepted-intent revision SHA-256
- exact policy profile SHA-256
- decision
- reason
- request-authority eligibility
- evaluation time
- receipt SHA-256

Recording the receipt is a real ledger effect:

```text
effect_performed = true
```

but it explicitly asserts:

```text
desktop_effect_performed = false
authority_request_created = false
action_lease_created = false

policy_authority = false
operational_authority = false
action_authority = false
execution_authority = false
```

## Transport

Read current projection:

```http
GET /api/v1/ghostwalk/policy-admission?target=<inference-sha256>
```

Record current admission evidence:

```http
POST /api/v1/ghostwalk/policy-admission/evaluations
```

Body:

```json
{
  "target_inference_receipt_sha256": "...",
  "expected_accepted_intent_revision_sha256": "...",
  "expected_policy_profile_sha256": "..."
}
```

The browser cannot supply:

- decision
- reason
- policy contents
- policy authority
- action authority
- execution authority
- authority-request payloads
- ActionLease data

## PhiShell

The Accepted Intent editor now contains a Policy Admission card.

It displays:

- ALLOW_REQUEST / HOLD / DENY
- exact reason
- request-authority eligibility
- current/stale OperatorLog binding
- policy profile digest
- allow/deny rule counts
- default HOLD behavior

The only mutation available is:

```text
RECORD ADMISSION EVIDENCE
```

There is deliberately no:

```text
REQUEST AUTHORITY
CREATE ACTIONLEASE
EXECUTE
```

button in v0.30.

## Existing ActionLease boundary

PhiOS already defines `ActionLease` as the first primitive in the wider
architecture that carries affirmative bounded action authority.

v0.30 does not call or construct it.

The intended future chain is:

```text
Ghost-Walk accepted intent
        ↓
v0.30 policy admission
        ↓
future authority request
        ↓
explicit authorization decision
        ↓
existing EffectIntent / EnforcementProfile / AuthorityEpoch gates
        ↓
ActionLease
        ↓
existing governed execution handoff
```

## Acceptance rules

Tests cover:

- unmapped intent defaults to HOLD
- explicit allow produces ALLOW_REQUEST only
- explicit deny produces DENY
- stale OperatorLog binding HOLDs before allow rules
- persisted admission creates no authority request
- persisted admission creates no ActionLease
- stale accepted-intent expectation conflicts
- policy profile defaults fail closed
- overlapping allow/deny configuration fails closed
- browser cannot inject authority into admission requests
- Node and browser contracts independently verify zero-authority envelopes
- PhiShell transport preserves projection and recorded receipt semantics

## Next rung

v0.31 should create an immutable **AuthorityRequest** artifact from an
`ALLOW_REQUEST` admission receipt.

That artifact should still carry zero action authority:

```text
policy admission
    ↓
AuthorityRequest
    ↓
explicit authorization decision
    ↓
ActionLease
```

A request is evidence that authority was asked for.

It is not evidence that authority was granted.
