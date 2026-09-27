# Macro Runtime v0.36 — Human Authorization + Lease Console

Macro Runtime v0.36 exposes the already-governed v0.32-v0.34 trust chain to
the local human operator.

It does not add a new executor.

The completed operator path is:

```text
AuthorityRequest
    ↓
human APPROVE / HOLD / DENY
    ↓
AuthorizationDecision
    ↓
deterministic capability/effect binding
    ↓
lease-readiness projection
    ↓
single-use ActionLease
```

Execution remains a separate v0.35 / PhiVessel bridge concern.

## Core boundary

```text
HUMAN DECISION != EXECUTABLE BINDING
EXECUTABLE BINDING != ACTION LEASE
ACTION LEASE != EXECUTION
VESSEL MAY REFERENCE A LEASE
VESSEL MAY NOT MINT A LEASE
```

## Human-only authorization surface

The console is mounted under the existing PhiShell AuthorityRequest card.

The browser may submit one explicit human decision:

```text
APPROVE
HOLD
DENY
```

The decision request contains only:

```text
target_inference_receipt_sha256
expected_authority_request_sha256
expected_previous_decision_sha256
decision
decision_note
```

Authorizer identity remains server-owned.

An APPROVE decision records authorization for the exact semantic request but
still carries no action authority and creates no lease.

HOLD remains non-terminal.

DENY and APPROVE remain terminal under the v0.32 contract.

## Binding stage

After an APPROVE decision, the console can request creation of the existing
v0.33 executable binding.

The browser may echo only current optimistic-concurrency identities:

```text
target_inference_receipt_sha256
expected_authorization_decision_sha256
expected_mapping_sha256
expected_mapping_set_sha256
```

The browser cannot supply:

- capability ID or version;
- action payload;
- target;
- permission set;
- effects;
- mapping contents;
- binding timestamp.

PhiOS derives those from trusted local mapping configuration and immutable
Ghost-Walk evidence.

The console displays only a bounded binding summary, including capability,
payload hash, permissions, effects, mapping ID, and binding digest. The full
executable payload is not projected into the operator card.

## Lease stage

The console can issue the existing v0.34 ActionLease only when lease readiness
is `READY`.

The browser may echo only:

```text
target_inference_receipt_sha256
expected_executable_binding_sha256
expected_policy_sha256
expected_policy_set_sha256
expected_enforcement_profile_sha256
expected_authority_epoch_sha256
```

It cannot submit:

- payload;
- permission names;
- effect names;
- lease duration;
- principal;
- issuer;
- policy rules;
- AuthorityEpoch contents;
- accepted enforcement gaps.

The server recomputes trusted state under the existing v0.34 lock.

The resulting lease remains single-use and bounded by the server-owned policy
and current AuthorityEpoch.

## Console projection authority

The console snapshot and transport remain zero-authority:

```text
policy_authority      = false
operational_authority = false
action_authority      = false
execution_authority   = false
effect_performed      = false
```

A nested lease summary may report:

```text
lease_action_authority = true
```

as a fact about the existing ActionLease.

That does not transfer the lease's authority to the console transport.

## Trusted execution manifest behavior

Human authorization is available whenever the v0.31 AuthorityRequest service
is available.

The binding and lease stages require the trusted local execution mount.

Therefore:

```text
no execution manifest
    → human APPROVE / HOLD / DENY still available
    → binding unavailable
    → lease unavailable
    → execution unavailable
```

With a valid enabled manifest:

```text
human decision
    ↓
binding
    ↓
ActionLease
    ↓
Vessie may later call execute(leaseId)
```

The local execution mount now reuses the same
`GhostWalkAuthorizationDecisionService` instance as the human console, so
authorization mutation and downstream binding do not depend on separate
process-local decision locks.

## Transport

The Python loopback sidecar adds:

```text
GET  /api/v1/ghostwalk/authorization-console
POST /api/v1/ghostwalk/authorization-console/decisions
POST /api/v1/ghostwalk/authorization-console/bindings
POST /api/v1/ghostwalk/authorization-console/leases
```

PhiShell's Node local transport independently validates and proxies those
contracts.

The browser client validates them again before rendering.

No permissive CORS is added.

## Mutation semantics

Decision, binding, and lease creation are local Ledger mutations, so their
transport envelopes report:

```text
effectPerformed = true
desktopEffectPerformed = false
```

The read-only console status reports:

```text
effectPerformed = false
```

No v0.36 endpoint enters the desktop executor.

## UI stages

The PhiShell console is intentionally split into three visible stages:

1. **Human Decision**
   - APPROVE
   - HOLD
   - DENY
   - optional human note

2. **Executable Binding**
   - trusted mapping readiness
   - capability/version
   - payload digest
   - permissions/effects
   - explicit create action

3. **Single-Use ActionLease**
   - lease-policy digest
   - EnforcementProfile digest
   - AuthorityEpoch digest
   - missing-permission visibility
   - explicit issue action
   - exact lease identity and validity window

There is intentionally no Execute button in this console.

## PhiVessel boundary

PhiVessel continues to expose only:

```text
observe(...)
propose(...)
execute(leaseId)
```

v0.36 does not add:

```text
authorize(...)
bind(...)
issueLease(...)
```

to Vessie.

That asymmetry is intentional.

```text
VESSEL MAY PROPOSE
HUMAN MAY AUTHORIZE
PHIOS MAY LEASE
VESSEL MAY REFERENCE LEASE
PHIOS MAY EXECUTE
REALITY LEDGER RECORDS RESULT
```

## Next rung

After v0.36 is green, the next useful work should be operational rather than
another authority layer:

1. trusted manifest / AuthorityEpoch operator tooling;
2. native/local Vessie host handshake;
3. one controlled Windows end-to-end Ghost-Walk acceptance scenario;
4. confirmation that the issued lease is consumed exactly once and that
   post-action verification lands in the Reality Ledger.

The authority architecture itself should remain unchanged unless that real
acceptance run reveals a concrete gap.
