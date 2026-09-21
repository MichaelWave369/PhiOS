# PhiOS Memory Evidence Horizon v0.1

## Status

Research-hardening candidate.

Primary contracts:

```text
phios.evidence_horizon_policy.v0.1
phios.evidence_horizon_receipt.v0.1
phios.reactivation_window_receipt.v0.1
phios.reconsolidation_gate.v0.1
```

Primary rule:

```text
RETRIEVABLE
!=
CURRENTLY ADMISSIBLE FOR THIS CONTEXT
```

Canonical retention and present-tense context admission are separate decisions.

## EvidenceHorizonPolicy

The policy declares:

```text
policy_id
version
max_context_age_seconds
reactivation_window_seconds
```

The normalized policy is SHA-256 bound.

The context horizon does not delete a record and does not modify its canonical revision.

## EvidenceHorizonReceipt

At a supplied evaluation time, one exact memory revision is classified as:

```text
ADMISSIBLE
REACTIVATION_REQUIRED
OUTSIDE_HORIZON
```

The receipt binds:

- record ID, revision, and canonical SHA-256;
- record creation time;
- evaluation time;
- age in seconds;
- horizon policy ID/hash;
- direct-context admissibility;
- zero operational/action/execution authority.

At the exact age boundary:

```text
age == max_context_age_seconds
```

the record remains directly admissible.

After that boundary, the record is no longer returned as active context on a hardened
memory service.

## ReactivationWindowReceipt

A stale record receives an explicit reactivation-window receipt.

The window begins when direct context admission expires and closes after:

```text
reactivation_window_seconds
```

The receipt deliberately fixes:

```text
reactivation_authorized = false
reactivation_completed  = false

operational_authority   = false
action_authority        = false
execution_authority     = false
```

The receipt answers only:

> Is this stale revision still inside the configured window where a fresh
> reconsolidation attempt may be considered?

It does not perform that reconsolidation. Once the window closes, the hardened
`GovernedMemoryService` refuses in-place reconsolidation of that stale head even when
new provenance is supplied. A caller must create a new memory identity rather than
renewing an arbitrarily old canonical head.

## ReconsolidationGate

When a published canonical head has already crossed the direct context horizon, a new
revision on the hardened service must demonstrate fresh provenance.

The candidate must:

- preserve the same record ID;
- advance exactly one revision;
- have a later creation timestamp;
- bind explicit reconsolidation evidence in candidate provenance;
- introduce at least one provenance reference not already present on the stale head.

This blocks the cheap refresh pattern:

```text
old memory
→ copy unchanged
→ assign new timestamp
→ pretend current
```

A successful gate still carries:

```text
promotion_status       = not_promoted
operational_authority  = false
action_authority       = false
execution_authority    = false
```

Fresh provenance is not the same thing as verified truth.

## GovernedMemoryService integration

The evidence horizon is optional.

Legacy callers that do not configure an `EvidenceHorizonController` retain the existing
memory behavior.

When a controller is configured:

### Direct get

`get()` first performs the existing authority and memory-policy checks.

Then the exact canonical record is evaluated against the horizon.

If directly admissible:

```text
MemoryResult.status = ok
record returned
ReadAdmissibilityReceipt returned
EvidenceHorizonReceipt returned
```

If stale:

```text
MemoryResult.status = degraded
record not returned as context
EvidenceHorizonReceipt returned
ReactivationWindowReceipt returned
```

The canonical record remains in storage.

### Semantic retrieval

Horizon filtering occurs before vector ranking.

This prevents stale records from occupying the top-k candidate budget and displacing
currently admissible records.

The order becomes:

```text
authority / memory policy
→ canonical eligible versions
→ evidence-horizon filter
→ embedding / vector ranking
→ canonical rehydration
→ policy recheck
→ ReadAdmissibilityReceipt
```

The semantic operation identity also binds the horizon-policy SHA-256.

## What the horizon does not mean

`ADMISSIBLE` does not mean:

- true;
- verified;
- authoritative;
- complete;
- relevant to every task.

`OUTSIDE_HORIZON` does not mean:

- false;
- deleted;
- historically invalid;
- safe to forget.

It means only that the hardened context-consumption policy will not admit that revision
without a newer provenance-bearing revision.

## Design rule

```text
history may remain durable
context admission may expire
authority remains separate
```

Humans have managed to confuse "I still have the note" with "the note is still current"
for a very long time. PhiOS now has fewer excuses.
