# Macro Runtime v0.29 — Typed Accepted Intent

v0.29 introduces a distinct append-only layer for human-confirmed intent.

It sits between editable human interpretation and any future execution policy:

```text
machine candidate
    !=
human annotation
    !=
accepted intent
    !=
execution policy
```

The purpose of accepted intent is to record what the human says a demonstrated
transition *means* without converting that declaration into permission to act.

## Evidence chain

An accepted-intent revision binds:

```text
immutable transition inference receipt
        +
exact OperatorLog revision SHA-256
        +
typed intent family
        +
canonical intent code
        +
human acceptance identity/time
```

Example:

```text
inference:
  semantic appeared / window changed

OperatorLog:
  "Correction: I opened network adapter properties."

accepted intent:
  family = OPEN
  code   = OPEN_NETWORK_ADAPTER_PROPERTIES
```

The accepted intent does not modify either source artifact.

## Typed vocabulary

v0.29 defines a small stable intent-family vocabulary:

```text
NAVIGATE
OPEN
CLOSE
SELECT
TOGGLE
ENTER_TEXT
SUBMIT
CONFIRM
CANCEL
OTHER
```

Application-specific meaning is carried by a canonical uppercase
`intent_code`.

Except for `OTHER`, the code must match its family prefix:

```text
OPEN
  -> OPEN_NETWORK_ADAPTER_PROPERTIES

TOGGLE
  -> TOGGLE_WIFI_ENABLED

SELECT
  -> SELECT_PRIMARY_ADAPTER
```

This gives PhiOS typed semantics without requiring one giant enum containing
every possible action in every application.

## Accepted-intent revision contract

Each revision contains:

- target transition-inference receipt SHA-256
- exact source OperatorLog revision SHA-256
- revision number
- intent family
- intent code
- ACTIVE / REVOKED status
- server-owned accepting operator identity
- acceptance timestamp
- previous revision SHA-256
- canonical revision SHA-256

It also asserts:

```text
human_intent_confirmed = true
causation_proven       = false

policy_authority       = false
operational_authority  = false
action_authority       = false
execution_authority    = false
```

Human confirmation of meaning is not proof that the observed UI change was
caused solely by the demonstrated action.

## OperatorLog binding

A new or replacement ACTIVE intent can be accepted only from the exact current
ACTIVE OperatorLog revision.

The registry rejects:

- a stale OperatorLog revision SHA
- a retracted OperatorLog revision
- a tampered OperatorLog revision
- a missing or ambiguous source revision
- an OperatorLog revision targeting another inference

If the OperatorLog is edited after intent acceptance, the existing accepted
intent remains intact as historical evidence.

PhiShell labels that condition:

```text
STALE BINDING
```

The operator can then append a new accepted-intent revision bound to the newer
human interpretation.

## Append-only updates and revocation

Intent classification changes append revisions:

```text
r1 OPEN_NETWORK_ADAPTER_PROPERTIES
        ↓
r2 NAVIGATE_NETWORK_ADAPTER_PROPERTIES
```

Revocation also appends:

```text
r2 ACTIVE
        ↓
r3 REVOKED
```

Nothing is deleted or rewritten.

All updates use:

```text
expected_current_revision_sha256
```

to reject stale concurrent mutations.

## Transport

The Ghost-Walk sidecar exposes:

```http
GET  /api/v1/ghostwalk/accepted-intent?target=<inference-sha256>
POST /api/v1/ghostwalk/accepted-intent/revisions
```

An ACCEPT payload contains only:

```json
{
  "operation": "ACCEPT",
  "target_inference_receipt_sha256": "...",
  "source_operator_note_revision_sha256": "...",
  "intent_family": "OPEN",
  "intent_code": "OPEN_NETWORK_ADAPTER_PROPERTIES",
  "expected_current_revision_sha256": null
}
```

A REVOKE payload contains only:

```json
{
  "operation": "REVOKE",
  "target_inference_receipt_sha256": "...",
  "expected_current_revision_sha256": "..."
}
```

The browser cannot supply:

- `accepted_by`
- policy authority
- action authority
- execution authority

Those fields are controlled by the governed runtime contract.

## Effect semantics

Reading accepted intent:

```text
intentMutation         = false
effectPerformed        = false
desktopEffectPerformed = false
```

Appending or revoking:

```text
intentMutation         = true
effectPerformed        = true
desktopEffectPerformed = false
```

The ledger append is a real persistent effect.

It is not a desktop effect and does not grant execution policy.

## PhiShell

The OperatorLog editor now contains an Accepted Intent section showing:

- current intent revision
- ACTIVE / REVOKED status
- canonical intent code
- intent family
- accepted-intent revision digest
- exact bound OperatorLog revision digest
- stale-binding warning

The operator can:

- accept the first typed intent
- append a reclassification
- revoke the current intent
- reload governed state

## Fail-closed rules

v0.29 rejects:

- unknown or malformed target hashes
- stale current-intent hashes
- stale source OperatorLog hashes
- retracted human interpretation
- tampered accepted-intent history
- tampered source OperatorLog history
- mismatched intent family/code prefix
- browser-provided authority fields
- browser-provided acceptance identity
- malformed transport envelopes

## Architectural boundary

```text
ACCEPTED INTENT
!=
EXECUTION POLICY

HUMAN INTENT CONFIRMED
!=
CAUSATION PROVEN

KNOWN MEANING
!=
PERMISSION TO ACT
```

## Next rung

v0.30 should introduce a separate policy-admission layer that can answer whether
an accepted intent is eligible to *request* execution under a bounded policy.

That layer should still not perform the action itself:

```text
accepted intent
    ↓
policy admission
    ↓
authority request
    ↓
existing governed execution path
```
