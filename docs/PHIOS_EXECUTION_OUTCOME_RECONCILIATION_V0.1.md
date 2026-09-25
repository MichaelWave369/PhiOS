# PhiOS Execution Outcome + Reconciliation v0.1

## Status

Runtime integration candidate.

## Core law

```text
EXECUTOR RETURN != EFFECT TRUTH
EXECUTOR ERROR != EFFECT ABSENCE
OUTCOME UNKNOWN != SAFE TO RETRY
RETRY SAFE != RETRY AUTHORIZED
```

PhiOS already distinguishes capability, permission, binding, and leased
authority. This rung adds a separate distinction between an execution attempt
and what can actually be proven about the resulting external state.

## Problem

A remote or external action can cross the effect boundary successfully and then
lose its acknowledgement.

Examples include:

- a switch accepting a configuration command before SSH disconnects;
- an API committing a mutation before a client timeout;
- a cloud job being created before the response is lost;
- a remote agent applying a change before its transport dies.

In those cases, recording `failed` as if it proved that no effect occurred is
not sound. Blind retry is also unsafe because the first attempt may already have
committed.

## Runtime state

PhiOS v0.1 preserves existing ordinary outcomes and adds one explicit uncertain
outcome:

```text
not_executed
succeeded
failed
outcome_unknown
```

Every execution receipt also records:

```text
executor_entered
reconciliation_status
effect_confirmed
reconciliation_receipt_sha256
```

An executor that has actually entered an effecting operation but cannot know
whether the final effect committed raises `OutcomeUnknownError`.

The Spine then records:

```text
execution_status = outcome_unknown
executor_entered = true
reconciliation_status = required
effect_confirmed = null
```

This state consumes the governed binding and any single-use ActionLease. It is
therefore replay-blocking until a new authority path is established.

## Reconciliation

`reconcile_execution_outcome()` accepts the exact outcome-unknown
`ExecutionReceipt`, one or more canonical `EvidenceRef` records, a
reconciler identity, timestamp, and one disposition:

```text
effect_confirmed
no_effect_confirmed
inconclusive
```

The resulting `ExecutionReconciliationReceipt` binds:

- the execution receipt ID;
- a deterministic digest of the exact execution receipt;
- the reconciliation disposition;
- canonical EvidenceRef digests;
- effect confirmation state;
- semantic retry-safety state;
- whether more reconciliation is required.

## Retry semantics

```text
effect_confirmed
  -> retry_safe = false

no_effect_confirmed
  -> retry_safe = true

inconclusive
  -> retry_safe = false
  -> reconciliation_required = true
```

Critically:

```text
retry_safe = true
DOES NOT mean
retry_authorized = true
```

A retry still requires the normal PhiOS plan, binding, permission, current
AuthorityEpoch, and ActionLease path. Reconciliation never mints authority.

## Ledger behavior

Outcome-unknown execution counts as a consumed execution attempt for both:

- governed action bindings;
- single-use ActionLeases.

Reconciliation receipts are append-only records stored separately from the
original execution receipt. The original observation is never rewritten to make
history look cleaner than it was.

## Compatibility

Existing executors do not need to change.

- successful handlers remain `succeeded`;
- ordinary raised exceptions remain `failed`;
- only handlers that explicitly raise `OutcomeUnknownError` enter the
  reconciliation-required path.

This prevents PhiOS from converting every software error into epistemic
uncertainty while still giving remote and external executors a truthful state.

## Scope

v0.1 intentionally does not:

- automatically infer whether a generic exception is outcome-unknown;
- grant retry authority from reconciliation;
- mutate historical execution receipts;
- define distributed reconciliation consensus;
- automatically issue a replacement ActionLease;
- claim that executor success independently proves every external effect.

The next rung can bind capability-specific reconciliation policies to declared
effect scopes and Reality Verification providers.
