# Macro Runtime v0.8 — Run Start Request / Trigger Contract

## Status

Zero-authority admission contract for turning an external observation into a
request to start one already-defined MacroPlan.

v0.8 does not add a scheduler, webhook listener, filesystem watcher, message
consumer, or background worker.

It defines the boundary those systems must use later.

## Core boundary

~~~
TRIGGER != AUTHORITY
OBSERVATION != COMMAND
RUN START REQUEST != EXECUTION AUTHORITY
START ADMISSION != DO AUTHORITY
ADMISSION POLICY != CAPABILITY GRANT
STARTED RUN != AUTHORIZED EFFECT
~~~

A successful run start creates control-flow state only.

Real DO operations still require the merged governed execution path.

## Three separate objects

v0.8 separates:

~~~
TriggerObservation
        ↓
RunStartRequest
        ↓
RunStartAdmissionPolicy
        ↓
MacroRunStartGate
        ↓
MacroRunCoordinator.start_run()
~~~

None of those objects can carry operational, action, or execution authority.

## TriggerObservation

A TriggerObservation represents one external fact that some source claims to
have observed.

It binds:

- observation ID;
- trigger type;
- source ID;
- source event ID;
- timezone-aware observed timestamp;
- payload SHA-256;
- optional sorted evidence-reference SHA-256 values;
- zero authority flags.

The raw trigger payload is not required by this contract.

The observation binds the payload by hash.

Example future trigger types may include:

- manual;
- schedule;
- webhook;
- filesystem;
- message;
- model suggestion;
- external event.

v0.8 does not implement any of those producers.

## RunStartRequest

A RunStartRequest pins one observation to one exact macro plan and one explicit
run ID.

It binds:

- request ID;
- run ID;
- macro ID and version;
- exact MacroPlan SHA-256;
- TriggerObservation SHA-256;
- trigger type;
- source ID;
- source event ID;
- deterministic dedupe SHA-256;
- timezone-aware request timestamp;
- zero authority flags.

The caller supplies the run ID explicitly.

The gate does not invent a random run identity.

## Dedupe identity

The dedupe SHA-256 is derived from:

~~~
TriggerObservation SHA-256
macro ID
macro version
MacroPlan SHA-256
~~~

The run ID and request ID are deliberately excluded.

Therefore the same observed source event cannot start the same pinned macro plan
twice merely by changing request or run IDs.

A different macro plan may independently process the same observation.

## RunStartAdmissionPolicy

The start admission policy is a non-authority allowlist.

It contains:

- policy ID;
- sorted allowed trigger types;
- sorted allowed source IDs;
- enabled state;
- zero authority flags;
- deterministic policy SHA-256.

The policy answers only:

> may this kind of source request creation of a macro run?

It does not answer:

> may the macro perform its operations?

Those decisions remain downstream.

## Exact scope validation

Before any claim or run creation, MacroRunStartGate verifies:

~~~
request.trigger_observation_sha256
    == observation.observation_sha256

request.trigger_type
    == observation.trigger_type

request.source_id
    == observation.source_id

request.source_event_id
    == observation.source_event_id

request.macro_id
request.macro_version
request.plan_sha256
    == supplied MacroPlan identity

request.dedupe_sha256
    == recomputed dedupe identity
~~~

A mismatch produces a REJECTED start receipt.

No run is created.

## Atomic start claims

Reality Ledger now provides two atomic claim classes:

~~~
macro-start-dedupe-claims/
macro-run-id-claims/
~~~

The first reserves one observation/macro-plan dedupe identity.

The second reserves one requested run identity.

Both use exclusive file creation.

The gate therefore cannot admit two identical start requests concurrently under
normal single-host ledger semantics.

If the run-ID claim fails after the dedupe claim succeeds, the dedupe claim is
released because no run was admitted.

If coordination fails before a run is created, both claims are released.

Successful admission keeps the claims as durable reservations.

## Start outcomes

RunStartReceipt uses:

~~~
STARTED
HELD
REJECTED
~~~

### STARTED

The request passed exact scope, policy, dedupe, run-ID claim, and coordinator
start checks.

The receipt binds the resulting:

- journal head SHA-256;
- MacroRunState SHA-256;
- runner status.

For a simple DO macro the expected start state remains:

~~~
WAITING_OPERATION
~~~

No real effect is implied.

### HELD

The request is structurally valid but cannot currently be admitted.

Examples:

- policy disabled;
- run ID already exists;
- trigger already admitted;
- run ID currently claimed.

### REJECTED

The request does not satisfy the declared start-admission contract.

Examples:

- trigger type not allowed;
- source not allowed;
- observation/request mismatch;
- plan mismatch;
- invalid dedupe scope.

## Run-start receipts

Reality Ledger adds:

~~~
macro-run-start-receipts.jsonl
~~~

Every admission attempt records:

- status and reason;
- request ID and hash;
- run ID and run-ID hash;
- macro identity;
- plan hash;
- observation hash;
- source/type/event identity;
- dedupe hash;
- admission-policy identity and hash;
- resulting journal head/state/status when STARTED;
- zero authority flags.

A start receipt proves the admission decision was recorded.

It does not prove that any macro operation executed.

## Coordinator integration

A STARTED admission calls:

~~~
MacroRunCoordinator.start_run()
~~~

That means the normal v0.7 lifecycle immediately owns:

- START persistence;
- first runner advance;
- first pause persistence;
- later reconstruct/advance/resume behavior.

The start gate does not duplicate runner or journal logic.

## v0.8 acceptance gates

### START-001 — allowed source starts only control flow

A valid observation/request/policy creates a run and reaches the normal first
runner boundary.

For a DO macro:

~~~
RunStartReceipt.status == STARTED
MacroRunState.status == WAITING_OPERATION
Spine execution receipts == 0
~~~

### START-002 — trigger dedupe

The same TriggerObservation cannot start the same pinned MacroPlan twice, even
with a different request ID or run ID.

The second admission is HELD with:

~~~
reason = trigger_already_admitted
~~~

### START-003 — run-ID uniqueness

A different trigger cannot start another run using an existing run ID.

### START-004 — source admission

A source outside the policy allowlist is REJECTED and creates no run.

### START-005 — exact plan scope

A RunStartRequest pinned to a different MacroPlan is REJECTED.

### START-006 — disabled policy is retryable

A disabled admission policy produces HELD before claims are consumed.

A later retry under an enabled policy may still start the run.

### START-007 — failed run-ID claim releases dedupe

If the run-ID atomic claim is unavailable, the request is HELD and its trigger
dedupe claim is released because no run was created.

After the run-ID claim becomes available, the same request may retry.

### START-008 — zero-authority start chain

TriggerObservation, RunStartRequest, RunStartAdmissionPolicy, and
RunStartReceipt all retain zero authority.

A STARTED DO macro still pauses at WAITING_OPERATION.

## What is now complete

PhiOS now has a governed boundary from external observation to persistent macro
control flow:

~~~
external event
→ TriggerObservation
→ RunStartRequest
→ admission policy
→ atomic dedupe / run-ID claims
→ MacroRunCoordinator
→ persistent MacroRun
→ WAITING_* boundary
~~~

The event can start control flow.

It cannot authorize the work inside that control flow.

## Deliberate non-goals

v0.8 does not add:

- real timers;
- cron;
- webhook servers;
- filesystem watchers;
- message subscriptions;
- model-trigger listeners;
- background workers;
- recurring scheduling;
- automatic ActionLease acquisition;
- automatic approval;
- automatic condition evaluation;
- external adapter execution.

## Next rung

v0.9 may safely add the first concrete trigger producer.

The smallest useful producer should be a wall-clock schedule contract that emits
TriggerObservation objects into the v0.8 gate.

The scheduler must still be unable to bypass start admission or downstream
operation authority.

A safe path is:

~~~
ScheduleDefinition
→ due-time observation
→ TriggerObservation
→ RunStartRequest
→ MacroRunStartGate
→ MacroRunCoordinator
~~~

Only after that works should webhooks, filesystem events, message events, or
model-generated trigger observations be connected.
