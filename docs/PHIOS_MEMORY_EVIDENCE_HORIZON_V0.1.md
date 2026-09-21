# PhiOS Memory Evidence Horizon v0.1

## Status

Research-hardening candidate.

Primary contracts:

```text
phios.memory.evidence_horizon_policy.v0.1
phios.memory.evidence_horizon_receipt.v0.1
phios.memory.reactivation_window_receipt.v0.1

EvidenceHorizonPolicy
MemoryEvidenceHorizon
ReconsolidationGate
EvidenceHorizonReceipt
ReactivationWindowReceipt
```

Primary distinction:

```text
RETRIEVABLE
!=
CURRENTLY ADMISSIBLE FOR THIS CONTEXT
```

Governed memory already separates canonical storage from derived retrieval and
permission from content. This contract adds a temporal context boundary.

A memory may still be retained, published, live, policy-readable, and semantically
retrievable while being too old to enter present reasoning without newer linked
evidence.

## Three independent clocks

PhiOS now keeps three questions separate:

1. **Retention / expiry:** should the canonical record still exist?
2. **Access policy:** may this principal read the record?
3. **Evidence horizon:** may this still-readable record enter the current reasoning
   context at this time?

The third question cannot widen either of the first two.

## EvidenceHorizonPolicy

The policy declares:

```text
policy_id
policy_version
active_window_seconds
reactivation_window_seconds
fresh_evidence_window_seconds
```

Validation requires:

```text
0 < fresh_evidence_window_seconds <= active_window_seconds
active_window_seconds < reactivation_window_seconds
```

Every evaluation binds the canonical policy SHA-256.

No global default is silently enabled. The operator must explicitly turn on evidence
horizons.

## Phases

### ACTIVE

The record age is inside the active-context window.

```text
context_admissible = true
reactivation_required = false
```

### REACTIVATION_REQUIRED

The record has left the active window but remains inside the reactivation window.

The canonical record remains unchanged and readable at the storage/policy layer, but the
governed consumption path refuses to return it as current context without acceptable
reconsolidation evidence.

### REACTIVATED

A newer canonical record passed the ReconsolidationGate.

The older record may enter this bounded context. Its content, timestamp, retention
policy, and canonical hash remain unchanged.

### REACTIVATION_HELD

Reactivation evidence was supplied but did not satisfy the gate.

Examples include:

- self-reactivation;
- evidence older than the target memory;
- stale evidence;
- scope/classification mismatch;
- missing exact provenance linkage;
- explicit contradiction.

### OUTSIDE_HORIZON

The record age exceeds the maximum reactivation window.

Fresh evidence cannot renew it through this contract.

The record may remain retained for audit/history, but it does not enter ordinary current
context.

## Exact reactivation linkage

A supporting canonical memory must include the exact immutable target reference:

```text
memory:<record_id>:<revision>:<record_sha256>
```

inside its `provenance_refs`.

A record ID alone is not enough because the record may have been revised.

A text similarity score is not enough because similarity is not provenance.

A newer timestamp alone is not enough because recency is not relationship.

## ReconsolidationGate

The gate receives two canonical records:

```text
target historical record
+
newer reactivation evidence record
```

The newer record must:

- be a different record;
- have a later creation time;
- remain inside the fresh-evidence window at evaluation;
- be readable under the same current caller policy;
- occupy the same scope and classification;
- carry the exact immutable target reference;
- not contradict the target record.

The gate emits a receipt only about **context reactivation**.

It does not edit either record.

## ReactivationWindowReceipt

An accepted receipt fixes:

```text
context_reactivated = true

canonical_record_mutated = false
retention_mutated = false

operational_authority = false
action_authority = false
execution_authority = false
```

It binds:

- target record ID/revision/hash;
- reactivation record ID/revision/hash;
- exact target reference;
- evaluation time;
- fresh-evidence age;
- evidence-horizon policy hash;
- decision and reason.

The receipt is evidence that a declared temporal gate passed. It is not evidence that
the old memory is objectively true.

## EvidenceHorizonReceipt

Each target evaluation binds:

```text
record ID / revision / SHA-256
record creation time
evaluation time
record age

policy ID / SHA-256
active window
reactivation window

phase / status
reason
reactivation required
reactivation receipt SHA-256

context admissible
retrievable record unchanged

operational authority = false
action authority = false
execution authority = false
```

## ReadAdmissibilityReceipt linkage

When a read succeeds under the horizon, the existing
`ReadAdmissibilityReceipt` also binds:

```text
evidence_horizon_receipt_sha256
evidence_horizon_status
reactivation_window_receipt_sha256
```

This prevents the final consumption receipt from forgetting the temporal basis that
made the record admissible.

## Semantic retrieval ordering

When evidence horizons are enabled, semantic search becomes:

```text
authority + memory policy
        ↓
live/published canonical versions
        ↓
evidence-horizon / reconsolidation prefilter
        ↓
authorized horizon-admissible allowlist
        ↓
query embedding
        ↓
derived sqlite-vec ranking
        ↓
canonical rehydration + policy recheck
        ↓
ReadAdmissibilityReceipt
```

This ordering matters.

If stale records were ranked first and filtered later, stale vectors could crowd current
records out of a bounded result set. v0.1 therefore removes context-inadmissible versions
before ranking.

## Operator configuration

The governed-memory config now supports:

```json
{
  "evidence_horizon_enabled": false,
  "active_context_window_seconds": 86400,
  "reactivation_window_seconds": 2592000,
  "fresh_evidence_window_seconds": 21600
}
```

The feature is disabled by default for backward compatibility.

Once enabled, a record outside the active window fails closed at the current-context
boundary.

### Explicit reactivation

For one direct read:

```bash
phi-memory --allow memory.read get old-record \
  --reactivate-with newer-linked-record
```

For semantic search:

```bash
phi-memory --allow memory.read search "topic" \
  --reactivate old-record=newer-linked-record
```

The newer record must already exist as canonical governed memory. The CLI does not
fabricate a reactivation assertion from free-form text.

## What does not change

v0.1 does not:

- delete old canonical records merely because they leave the evidence horizon;
- alter normal `expires_at` retention semantics;
- mutate the vector index into an authority source;
- treat similarity as reconsolidation evidence;
- let a newer record cross scope/classification boundaries;
- grant planning, action, or execution authority;
- claim that a linked fresh record is true;
- claim that two records are independent evidence paths.

## Design rule

The intended relationship is:

```text
history can remain durable
while context remains current
```

Humans call this "remembering without letting a 2009 opinion run the meeting." Software
apparently needed three hashes and a gate to arrive at the same insight.
