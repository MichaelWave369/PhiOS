# Macro Runtime v0.33 — Ghost-Walk capability/effect binding

v0.33 introduces the deterministic bridge from one exact current
`AuthorizationDecision(APPROVE)` to one exact executable representation.

Core rule:

```text
SEMANTIC INTENT
!=
EXECUTABLE REPRESENTATION
!=
ACTION AUTHORITY
!=
EXECUTION
```

## Architecture position

```text
Ghost-Walk observation
        ↓
transition inference
        ↓
human annotation
        ↓
accepted intent
        ↓
policy admission
        ↓
AuthorityRequest
        ↓
AuthorizationDecision(APPROVE)
        ↓
server-owned capability mapping
        ↓
GhostWalkExecutableBinding
        ↓
EffectIntent
        ↓
future EnforcementProfile / AuthorityEpoch
        ↓
future ActionLease
        ↓
governed execution
```

v0.33 stops before enforcement evaluation, authority-state reconstruction,
ActionLease issuance, or execution.

## Why the demonstrated action is reused

An accepted semantic code such as:

```text
OPEN_NETWORK_ADAPTER_PROPERTIES
```

does not contain enough information to invent a safe executable payload.

v0.33 therefore resolves the exact transition-inference receipt bound by the
authorization chain, follows its exact `action_observation_sha256`, loads the
immutable demonstrated Ghost-Walk observation, and derives the executable
payload from that observation.

The semantic intent chooses **whether a mapping is allowed**.

The demonstrated action supplies **what was actually demonstrated**.

Neither is allowed to invent the other.

## Server-owned mapping registry

The mapping registry is supplied to the binding service by trusted local code.
The browser does not choose:

- capability ID
- capability version
- action kind
- target strategy
- permission scope
- effect scope
- payload

Each mapping binds:

```text
intent_code
action_kind
required_target_strategy
capability_id
capability_version
permissions_required
effects_declared
```

The complete mapping set has its own content digest:

```text
mapping_set_sha256
```

Binding creation uses optimistic concurrency against both the selected mapping
digest and the complete mapping-set digest.

## Bounded v0.33 capability

The first executable mapping is deliberately restricted to the already-governed
desktop click capability:

```text
capability_id      = desktop.interaction.click
capability_version = 0.19.0
permissions        = [ui.interact]
effects            = [display.control, filesystem.change]
action_kind        = CLICK
```

A mapping author must also choose the required replay strategy explicitly:

```text
SEMANTIC
or
WINDOW_RELATIVE_PIXEL
```

A demonstrated action using a different strategy does not silently fall back.
It produces `MAPPING_CONSTRAINT_MISMATCH`.

## Exact payload derivation

For a desktop click, v0.33 reconstructs the exact v0.18/v0.19 click request
shape from the immutable demonstration:

```text
observation_sha256
preferred_strategy
process_id
window_title_sha256
pixel_anchor
semantic_target
absolute_pixel_is_evidence_only = true
guard_required                  = true
```

The payload is then parsed by the real `DesktopClickRequest` contract before
a binding can be created.

The canonical payload digest becomes:

```text
payload_sha256
```

## EffectIntent

A successful binding also creates a canonical zero-authority `EffectIntent`
using the exact:

```text
capability ID
capability version
payload SHA-256
declared effects
binding timestamp
```

The EffectIntent does not grant permission and does not claim execution.

## Binding identity

`GhostWalkExecutableBinding` binds:

- exact AuthorizationDecision
- exact AuthorityRequest
- exact transition-inference receipt
- exact action observation
- semantic intent code
- selected mapping and complete mapping-set identity
- exact capability ID/version
- full canonical payload and payload digest
- exact permission requirements
- exact declared effects
- exact EffectIntent
- binding timestamp
- explicit zero authority

All fields participate in:

```text
executable_binding_sha256
```

## Readiness states

```text
READY
AUTHORIZATION_DECISION_REQUIRED
AUTHORIZATION_NOT_APPROVED
AUTHORIZATION_STALE
NO_MAPPING
AMBIGUOUS_MAPPING
ACTION_EVIDENCE_MISSING
MAPPING_CONSTRAINT_MISMATCH
BINDING_ALREADY_EXISTS
```

Only `READY` can create a binding.

## Fail-closed behavior

v0.33 rejects or holds when:

- no authorization decision exists
- the latest decision is HOLD or DENY
- the approval became stale
- no mapping exists
- more than one mapping exists for the semantic intent
- the bound transition receipt is missing
- the transition receipt was tampered with
- the demonstrated action is missing
- the demonstrated action was tampered with
- the action kind differs from the mapping
- the demonstrated replay strategy differs from the mapping
- the derived desktop payload fails the real click contract
- the mapping or mapping set changes before creation
- more than one binding exists for one authorization decision
- a persisted binding was tampered with

## Authority boundary

A successful binding fixes:

```text
effect_performed      = false
policy_authority      = false
operational_authority = false
action_authority      = false
execution_authority   = false
```

The embedded EffectIntent is also zero-authority.

So:

```text
BINDING CREATED != ACTION AUTHORITY
EFFECT DECLARED != EFFECT PERFORMED
CAPABILITY SELECTED != EXECUTION
```

## Next rung

v0.34 should take one exact current executable binding and construct the
remaining pre-lease trust state:

```text
GhostWalkExecutableBinding
        ↓
EnforcementProfile
        ↓
current AuthorityEpoch
        ↓
lease-readiness evaluation
        ↓
ActionLease
```

That rung should fail closed when enforcement mapping is incomplete, required
permissions exceed the current AuthorityEpoch, authorization/binding evidence
is stale, or accepted unenforced effects are not explicitly acknowledged.
