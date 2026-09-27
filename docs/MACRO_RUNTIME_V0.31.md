# Macro Runtime v0.31 — Ghost-Walk AuthorityRequest

v0.31 introduces an immutable zero-authority `AuthorityRequest` artifact.

The request is created only from one exact current `ALLOW_REQUEST` policy
admission receipt.

Core rule:

```text
REQUESTING AUTHORITY
!=
HAVING AUTHORITY
```

## Architecture position

The governed chain is now:

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
future explicit authorization decision
    ↓
future ActionLease
    ↓
existing governed execution
```

v0.31 stops at the AuthorityRequest.

It does not create an authorization decision, EffectIntent, EnforcementProfile,
AuthorityEpoch, ActionLease, execution handoff, or desktop effect.

## Why semantic scope only

v0.31 does not ask the browser to invent:

- capability IDs
- executable payloads
- permissions
- effects
- ActionLease parameters

The evidence available at this layer proves what semantic intent the human
accepted and that current policy allows an authority request.

It does not yet prove how that semantic intent should map into an executable
PhiOS capability.

The request therefore asks for:

```text
requested_authority_kind = ACTION_AUTHORITY
requested_scope_kind     = ACCEPTED_INTENT
requested_scope_value    = <exact accepted intent code>
```

Example:

```text
requested_scope_value = OPEN_NETWORK_ADAPTER_PROPERTIES
```

A later authorization/effect-mapping rung may decide whether that semantic
scope has a valid executable representation.

## Preconditions

An AuthorityRequest can be created only when all of the following are true:

1. current policy projection is `ALLOW_REQUEST`
2. the current accepted-intent revision is unchanged
3. the current policy profile is unchanged
4. a persisted policy-admission receipt exists for that exact combination
5. the admission receipt itself is canonical and hash-valid
6. the admission receipt records `ALLOW_REQUEST`
7. no AuthorityRequest already exists for that exact admission receipt

If any condition fails, request creation fails closed.

## Readiness reasons

The read-only readiness projection reports:

```text
READY
POLICY_NOT_ALLOW_REQUEST
ADMISSION_RECEIPT_REQUIRED
ADMISSION_RECEIPT_STALE
REQUEST_ALREADY_EXISTS
```

`READY` is the only state in which request creation is available.

## One request per admission receipt

v0.31 fixes:

```text
one admission receipt
    -> at most one AuthorityRequest
```

This prevents repeated request creation from one policy decision.

If accepted intent or policy changes, a new policy-admission receipt is required
before another AuthorityRequest can be created.

## AuthorityRequest identity

Each immutable request binds:

- exact admission-receipt SHA-256
- transition-inference receipt SHA-256
- accepted-intent revision SHA-256
- policy-profile SHA-256
- intent family
- exact intent code
- server-owned requester identity
- requested authority kind
- requested semantic scope
- request state
- request timestamp

All fields participate in:

```text
authority_request_sha256
```

## Request state

v0.31 has exactly one request state:

```text
PENDING_AUTHORIZATION
```

The request asserts:

```text
authorization_granted = false
action_lease_created  = false
effect_performed      = false

policy_authority      = false
operational_authority = false
action_authority      = false
execution_authority   = false
```

The request object itself carries no grant.

## Provenance validation

When a persisted AuthorityRequest is read, PhiOS verifies:

```text
AuthorityRequest canonical hash
        ↓
bound admission receipt exists
        ↓
admission receipt canonical hash
        ↓
same transition target
        ↓
same accepted-intent revision
        ↓
same policy profile
        ↓
decision == ALLOW_REQUEST
        ↓
request_authority_eligible == true
```

A request cannot become a self-certified island detached from the evidence that
allowed it to exist.

## Server-owned identity and scope

The browser may submit only:

```json
{
  "target_inference_receipt_sha256": "...",
  "expected_admission_receipt_sha256": "..."
}
```

The browser cannot supply:

- requester ID
- requested intent code
- requested authority kind
- requested scope kind
- permissions
- effects
- capability IDs
- ActionLease data
- authority flags

The sidecar derives requester identity and semantic scope from governed state.

## Transport

Read request readiness/current request:

```http
GET /api/v1/ghostwalk/authority-request?target=<inference-sha256>
```

Create one request:

```http
POST /api/v1/ghostwalk/authority-request/requests
```

Creating the request performs a real ledger write, so the transport reports:

```text
requestCreated  = true
effectPerformed = true
```

while still fixing:

```text
desktopEffectPerformed = false
authorizationGranted   = false
actionLeaseCreated     = false

policyAuthority        = false
operationalAuthority   = false
actionAuthority        = false
executionAuthority     = false
```

The persisted AuthorityRequest artifact itself keeps:

```text
effect_performed = false
```

because the artifact describes the requested authority, not the filesystem
operation that persisted it.

## PhiShell

The Policy Admission card now nests an AuthorityRequest card.

Before an admission receipt exists:

```text
AUTHORITY REQUEST
ADMISSION_RECEIPT_REQUIRED
ACTION AUTH 0
```

After an `ALLOW_REQUEST` admission receipt is recorded:

```text
AUTHORITY REQUEST
READY
ACTION AUTH 0

[ CREATE AUTHORITY REQUEST ]
```

After creation:

```text
AUTHORITY REQUEST
PENDING_AUTHORIZATION
ACTION AUTH 0

scope  OPEN_NETWORK_ADAPTER_PROPERTIES
lease  NONE
authorization NOT GRANTED
```

There is deliberately no approve, lease, or execute control in v0.31.

## Fail-closed behavior

v0.31 rejects:

- policy decisions other than `ALLOW_REQUEST`
- missing admission receipts
- stale admission receipts
- tampered admission receipts
- duplicate requests for one admission receipt
- tampered AuthorityRequests
- mismatched request/admission provenance
- browser-supplied requester identity
- browser-supplied semantic scope
- browser-supplied authority fields

## Existing ActionLease boundary

PhiOS already defines `ActionLease` as a separate primitive carrying bounded
action authority:

```text
action_authority    = true
execution_authority = false
```

AuthorityRequest remains strictly earlier in the chain:

```text
AuthorityRequest
    action_authority = false

        !=

ActionLease
    action_authority = true
```

v0.31 never imports, constructs, issues, or evaluates an ActionLease.

## Next rung

v0.32 should introduce an immutable explicit **AuthorizationDecision** bound to
one exact AuthorityRequest.

That decision should support at least:

```text
APPROVE
DENY
HOLD
```

Even an APPROVE decision should not itself perform execution.

A later bridge should translate an approved request into exact executable
effect evidence and only then reach the existing ActionLease issuance path.

```text
AuthorityRequest
    ↓
AuthorizationDecision
    ↓
effect/capability binding
    ↓
ActionLease
    ↓
governed execution
```
