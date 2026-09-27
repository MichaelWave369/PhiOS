# Macro Runtime v0.28 — Governed Ghost-Walk OperatorLog Editor

v0.28 gives the human operator a real editing surface for Ghost-Walk's
machine-generated interpretation notes while preserving the underlying
transition inference as immutable evidence.

The central rule is:

```text
HUMAN INTERPRETATION
!=
MACHINE INFERENCE
```

Saving a correction appends a new OperatorLog revision. It never rewrites the
transition-inference receipt and never grants desktop execution authority.

## Existing foundation

Ghost-Walk already publishes one editable OperatorLog note after a successful
transition inference:

```text
immutable transition inference receipt
        |
        v
OperatorLog revision 1
machine-generated human-editable summary
```

The original OperatorLog contract already provides:

- append-only revisions
- revision SHA-256
- supersedes-revision linkage
- optimistic concurrency through expected-current revision hash
- ACTIVE / RETRACTED status
- zero operational/action/execution authority
- tamper detection for the revision chain

v0.28 exposes those semantics safely to PhiShell.

## Architecture

```text
Ghost-Walk transition inference
        |
        | immutable receipt SHA
        v
OperatorLog revision chain
        |
        v
GhostWalkOperatorEditor
        |
        | serialized edit transaction
        v
Ghost-Walk loopback sidecar :3973
        |
        | validated proxy
        v
PhiShell local transport :3969
        |
        v
typed browser client
        |
        v
System Inspector interpretation editor
```

## Exact target binding

Edits are bound to:

```text
target_inference_receipt_sha256
```

not UI row numbers, candidate labels, text descriptions, or current window
coordinates.

Before an edit is accepted, the editor:

1. looks up the exact transition inference receipt
2. recomputes its canonical SHA-256
3. rejects tampered inference evidence
4. locates exactly one OperatorLog chain targeting that receipt
5. validates the OperatorLog chain
6. checks the browser-supplied expected-current revision SHA
7. appends one new revision

The source inference is never modified.

## Concurrency

The sidecar uses a lock around:

```text
read current revision
        +
verify expected-current SHA
        +
append next revision
```

So two simultaneous edits based on the same revision cannot both become the
next revision.

Expected behavior:

```text
editor A: expected r1 -> APPLIED as r2
editor B: expected r1 -> 409 CONFLICT
```

The browser preserves the operator's unsaved draft on conflict and asks for an
explicit reload of the latest revision.

## Operator identity

The browser does not supply `author_id`.

The sidecar owns the configured local operator identity:

```text
operator:local
```

Browser attempts to add an `author_id` field fail request validation.

This prevents UI code from relabeling an annotation as another operator.

## Sidecar endpoints

Read current annotation:

```http
GET /api/v1/ghostwalk/operator-log?target=<transition-inference-sha256>
```

Append a revision:

```http
POST /api/v1/ghostwalk/operator-log/revisions
```

Request body:

```json
{
  "target_inference_receipt_sha256": "...",
  "expected_current_revision_sha256": "...",
  "body": "Correction: I opened network adapter properties.",
  "status": "ACTIVE"
}
```

Allowed status values:

```text
ACTIVE
RETRACTED
```

Retraction is another append-only revision. It does not erase prior text.

## Effect semantics

Reading a note:

```text
annotationMutation     = false
effectPerformed        = false
desktopEffectPerformed = false
```

Saving a revision:

```text
annotationMutation     = true
effectPerformed        = true
desktopEffectPerformed = false
```

The persistent OperatorLog append is a real filesystem effect, so v0.28 does
not pretend otherwise.

However, both read and write envelopes retain:

```text
operationalAuthority = false
actionAuthority      = false
executionAuthority   = false
```

An annotation write is not desktop automation authority.

## PhiShell UI

Each recent learned transition now exposes:

```text
EDIT NOTE rN
```

Selecting it opens a bounded editor showing:

- exact target inference digest
- current revision number
- current revision digest
- note author
- ACTIVE / RETRACTED state
- full current interpretation text

The operator may:

- append a new ACTIVE revision
- append a RETRACTED revision
- reload the current revision
- close without changing anything

The editor states explicitly:

```text
HUMAN INTERPRETATION != MACHINE INFERENCE
SAVE APPENDS
SOURCE RECEIPT IMMUTABLE
EXECUTION AUTHORITY FALSE
```

## Fail-closed behavior

v0.28 rejects:

- unknown inference receipt
- tampered inference receipt
- malformed OperatorLog identity
- ambiguous note chains
- tampered revision chain
- stale expected-current revision
- extra browser fields
- browser-controlled author identity
- malformed SHA-256 values
- oversized or invalid note bodies
- non-zero authority evidence returned through proxies

## Tests

Coverage includes:

- exact inference-to-note binding
- canonical inference hash verification
- append-only correction
- retraction as revision
- stale-edit rejection
- simultaneous-edit serialization
- unknown target rejection
- tampered inference rejection
- loopback GET projection
- loopback POST append
- browser author-injection rejection
- Node proxy validation
- 409 conflict preservation
- browser client envelope validation
- browser client omission of author identity

## Next rung

v0.29 should let the human classify a corrected interpretation into a small,
typed accepted-intent vocabulary without collapsing the distinction between:

```text
machine candidate
human annotation
accepted intent
execution policy
```

Those should remain separate governed layers rather than one increasingly
confident blob of text.
