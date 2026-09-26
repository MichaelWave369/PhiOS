# Macro Runtime v0.7 — Run Coordinator

## Status

Lifecycle orchestration over the merged MacroRunner and persistent MacroRun
journal.

v0.7 removes manual runner/journal plumbing from normal callers while preserving
the same zero-authority boundaries.

## Core boundary

~~~
COORDINATOR != SCHEDULER
COORDINATOR != EXECUTOR
COORDINATOR != AUTHORITY BROKER
ADVANCE != AUTHORIZE
PERSIST != VERIFY REALITY
RESUME != REAUTHORIZE
~~~

The coordinator owns orchestration only.

## Owned lifecycle

~~~
create run ID
→ persist START
→ advance runner
→ persist resulting pause or terminal state
→ accept external resolution evidence
→ reconstruct latest valid state
→ advance runner
→ persist next state
→ resume after restart
~~~

Callers no longer need to manually:

- call MacroRunner.start();
- append START;
- remember the current journal head;
- reconstruct before every transition;
- extract resolution evidence hashes;
- append the next state;
- create resume receipts.

## Start

start_run() requires an explicit run_id and MacroPlan.

The coordinator:

1. rejects duplicate run IDs;
2. creates READY through MacroRunner;
3. persists the START entry;
4. advances until the first unresolved boundary or terminal state;
5. persists that state when meaningful progress occurred.

A one-step DO macro therefore starts as:

~~~
READY
→ WAITING_OPERATION
~~~

with both snapshots already journaled.

The coordinator does not invent a random run ID in v0.7. Run identity remains
explicit at the call boundary so external systems can bind their own request or
job identity without hidden nondeterminism.

## Advance

advance_run() reconstructs the entire validated chain first.

It never trusts a caller-supplied prior MacroRunState or journal head.

It then supplies RunnerInputs to the MacroRunner.

If the runner makes meaningful progress, the coordinator appends the new state
against the reconstructed current head.

If no meaningful control-flow progress occurred, no new journal line is added.

This avoids journal noise such as repeatedly supplying an irrelevant condition
while a run is waiting for an operation.

## Automatic evidence linkage

The coordinator extracts evidence hashes from RunnerInputs automatically.

Supported inputs:

- ConditionResolution.evidence_ref_sha256;
- OperationResolution.receipt_sha256;
- ApprovalResolution.evidence_ref_sha256;
- CallResolution.receipt_sha256;
- CheckpointResolution.receipt_sha256;
- CollectionResolution.evidence_ref_sha256.

The resulting set is sorted and deduplicated before it is attached to the next
journal entry.

The evidence links establish provenance only.

They do not grant authority or establish the truth of the referenced evidence.

## Current state

current_run() performs full journal reconstruction and returns the latest valid:

- MacroRunState;
- journal head hash;
- entry count.

It emits no resume receipt because it is observation only.

## Resume

resume_run() performs the same validated reconstruction but also emits the
existing MacroRunResumeReceipt.

The returned state still carries zero authority.

A resumed WAITING_OPERATION state must use the same governed v0.5 dispatcher
path before the runner can advance.

## Abort

abort_run() reconstructs the current state, uses MacroRunner.abort(), and
persists the resulting ABORTED state.

A terminal run is not extended and a repeated abort becomes a no-op view of the
existing terminal state.

## Meaningful progress

The coordinator persists a runner result only when control semantics changed.

The comparison includes:

- cursor;
- status;
- reason;
- loop counters;
- foreach indices;
- variables;
- waiting boundary;
- last instruction path.

Transition-counter changes alone do not create a new persistent state.

This prevents unresolved boundary polling from rewriting the run history with
semantically identical snapshots.

## v0.7 acceptance gates

### COORD-001 — start ownership

start_run() must persist START and the first resulting pause automatically.

### COORD-002 — resolution ownership

Supplying an OperationResolution must reconstruct, advance, persist, and attach
the resolution receipt hash without manual journal calls.

### COORD-003 — no journal noise

Irrelevant inputs that produce no meaningful control-flow progress must not
append another state.

### COORD-004 — restart ownership

A fresh coordinator instance must resume a persisted run, emit a resume
receipt, continue through later resolution boundaries, and expose the same
validated state through another fresh instance.

### COORD-005 — duplicate run protection

An existing run_id cannot be started again.

### COORD-006 — abort persistence

Abort must become an append-only terminal state, and repeated abort attempts
must not extend the journal.

### COORD-007 — held-state persistence

A HELD external resolution must become a persisted HELD MacroRunState and remain
reconstructable.

## What is now complete

The normal macro lifecycle now looks like:

~~~
MacroDefinition
→ MacroPlan
→ MacroRunCoordinator.start_run()
→ persisted pause
→ external governed resolution
→ MacroRunCoordinator.advance_run()
→ persisted next state
→ restart
→ MacroRunCoordinator.resume_run()
→ continue
~~~

The coordinator sits above:

~~~
MacroRunner
MacroRunJournal
GovernedDoDispatcher
~~~

but does not absorb their responsibilities.

## Deliberate non-goals

v0.7 does not add:

- timers;
- cron;
- event triggers;
- background workers;
- queues;
- automatic lease acquisition;
- automatic condition evaluation;
- automatic approval;
- recursive CALL execution;
- browser / shell / API / model adapters;
- workflow learning;
- higher-order optimization;
- atomic multi-process run locking.

## Next rung

v0.8 should add a **Run Start Request / Trigger Contract**, not a scheduler yet.

The goal is to define how an external event may request that one already-defined
macro be started without allowing the event source to smuggle execution
authority into the run.

A safe next boundary is:

~~~
TriggerObservation
→ zero-authority RunStartRequest
→ policy / dedupe checks
→ explicit run ID
→ MacroRunCoordinator.start_run()
~~~

Only after the start-request contract is stable should wall-clock schedules,
webhooks, filesystem events, or recurring automation workers be connected.
