# Macro Runtime v0.10 — Persistent Schedule Service State

## Status

Persistent cursor and replay-safe polling around the merged v0.9 wall-clock
schedule producer and v0.8 run-start gate.

v0.10 still does not run continuously in the background.

It turns explicit poll calls into durable schedule-service history.

## Core boundary

~~~
SCHEDULE SERVICE != BACKGROUND WORKER
CURSOR != AUTHORITY
POLL RECEIPT != EXECUTION RECEIPT
CURSOR ADVANCE != MACRO SUCCESS
REPLAY != DUPLICATE START
HELD WINDOW != LOST WINDOW
~~~

The service owns schedule observation and start-admission delivery only.

It never executes macro operations.

## Persistent state

Reality Ledger now stores:

~~~
schedule-service-state.jsonl
schedule-service-poll-receipts.jsonl
~~~

Each schedule service has an explicit service_id.

The persistent state chain binds:

- service ID;
- sequence number;
- START / TRANSITION kind;
- schedule ID and SHA-256;
- macro ID/version and MacroPlan SHA-256;
- admission policy ID;
- exact policy SHA-256 used for that state;
- persistent UTC cursor;
- ACTIVE / HELD status;
- state reason;
- previous state-entry SHA-256;
- last poll-receipt SHA-256;
- zero authority flags.

The schedule and MacroPlan binding are immutable for one service.

The admission policy ID is also stable, but the policy hash may change between
polls. This allows an operator to revise or enable the same named admission
policy and retry a HELD occurrence window.

## Cursor semantics

The cursor represents the upper bound of the latest completely settled poll
window.

A poll evaluates:

~~~
cursor < occurrence <= through_inclusive
~~~

The cursor advances to through_inclusive only if every emitted occurrence has a
settled admission result.

If any occurrence is retryably HELD, the cursor remains unchanged.

## Admission outcomes

Each emitted ScheduleOccurrence is converted into a deterministic
RunStartRequest.

The request/run identity is derived from:

~~~
service_id
MacroPlan SHA-256
occurrence_id
TriggerObservation SHA-256
~~~

Therefore replaying the same service/window creates the same request and run
identity.

Each admission result records:

- occurrence ID;
- observation SHA-256;
- request SHA-256;
- RunStartReceipt SHA-256;
- STARTED / HELD / REJECTED;
- start reason.

## Settled versus retryable HELD

v0.10 distinguishes retryable holds from replay evidence.

Retryable HELD reasons currently include:

~~~
start_policy_disabled
run_id_claimed
~~~

These keep the service cursor fixed.

Replay-settled HELD reasons include:

~~~
trigger_already_admitted
run_id_exists
~~~

These are treated as evidence that the same deterministic occurrence was
already admitted during an earlier attempt.

That matters after a crash.

## Crash after partial admission

Consider a window with two occurrences:

~~~
Occurrence A -> STARTED
Occurrence B -> HELD(run_id_claimed)
~~~

The service does not advance the cursor.

After restart the same window is evaluated again.

Because occurrence identities and requests are deterministic:

~~~
Occurrence A -> HELD(run_id_exists)
Occurrence B -> STARTED
~~~

Now the entire window is settled and the cursor advances.

No duplicate run is created for occurrence A.

This is the core replay-safety property of v0.10.

## Poll receipt

Each ScheduleServicePollReceipt binds:

- service / schedule / macro / policy identity;
- exact poll window;
- candidate count;
- emitted count;
- every admission result;
- COMMITTED / HELD poll status;
- reason;
- cursor-advanced Boolean;
- exact next cursor;
- zero authority flags.

Mechanical invariants require:

~~~
candidate_count >= emitted_count
emitted_count == len(admissions)
COMMITTED cursor == through_inclusive
HELD cursor == after_exclusive
~~~

Contradictory receipts cannot be constructed.

## Empty windows

A poll with no due occurrences may still commit.

That means PhiOS has durably established:

> this interval was evaluated and contained no selected schedule occurrence.

The cursor can safely advance across the empty interval.

## Policy revisions

The service keeps policy_id stable while allowing policy_sha256 to evolve.

Example:

~~~
policy disabled
→ occurrence HELD
→ cursor unchanged
→ same policy_id enabled with a new policy hash
→ same window replayed
→ occurrence STARTED
→ cursor advances
~~~

The exact policy hash used for every attempt remains visible in both state and
poll receipts.

## Restart reconstruction

ScheduleService.current() validates the complete service-state chain before
returning the head.

Validation includes:

- entry hash;
- contiguous sequence;
- stable service ID;
- stable schedule identity/hash;
- stable macro identity/plan hash;
- stable policy ID;
- monotonic UTC cursor;
- previous-entry hash chain.

A modified history fails closed.

A new ScheduleService instance over the same Reality Ledger can continue from
the reconstructed cursor.

## v0.10 acceptance gates

### SERVICE-001 — initial cursor persistence

Starting a service creates sequence zero with the explicit UTC cursor and zero
authority.

### SERVICE-002 — due occurrence commit

A due occurrence enters the v0.8 start gate, starts persistent macro control
flow, and advances the schedule cursor when settled.

The resulting macro may still be WAITING_OPERATION and no Spine effect need
exist.

### SERVICE-003 — policy hold / revision retry

A disabled admission policy keeps the cursor fixed.

Revising the same policy ID to an enabled policy allows the same window to be
retried and committed.

### SERVICE-004 — crash-after-admission replay

If a run was admitted before the service cursor was persisted, replay produces
the same run identity, observes run_id_exists, and safely advances without
creating a duplicate run.

### SERVICE-005 — all-or-nothing multi-occurrence window

If one occurrence in a multi-occurrence window is retryably HELD, the entire
cursor remains fixed.

After the hold clears, already-started occurrences collapse through deterministic
replay and the cursor advances only when all occurrences are settled.

### SERVICE-006 — restart continuation

A fresh ScheduleService instance reconstructs the persisted cursor and continues
from that exact point.

### SERVICE-007 — tamper detection

Modified state history fails reconstruction.

### SERVICE-008 — configuration pinning

A different schedule or MacroPlan cannot continue an existing service ID.

### SERVICE-009 — zero-authority persistence

Schedule-service states and poll receipts carry no operational, action, or
execution authority.

## What is now complete

The wall-clock path is now restart-safe without a continuously running process:

~~~
WallClockSchedule
→ persistent cursor
→ bounded poll
→ deterministic occurrence
→ deterministic RunStartRequest
→ v0.8 start admission
→ persistent poll receipt
→ cursor commit or hold
→ restart
→ reconstruct
→ replay safely
~~~

The service knows what time range has been completely processed.

It still has no authority over the macro effects started in that range.

## Single-writer boundary

v0.10 assumes one caller polls a given service at a time.

The append-only hash chain detects malformed/forked persistent history, but this
rung does not yet provide a crash-recoverable multi-process poll lock.

That belongs with the actual scheduler worker lifecycle, where ownership and
lease expiry can be specified explicitly instead of pretending an abandoned
lock file is a distributed systems solution.

## Deliberate non-goals

v0.10 does not add:

- a continuously running worker;
- sleep loops;
- process supervision;
- multi-process schedule leases;
- distributed locking;
- cron parsing;
- webhook / filesystem / message triggers;
- automatic ActionLease acquisition;
- automatic macro operation execution.

## Next rung

v0.11 should add the first continuously running Schedule Worker contract.

The worker should:

~~~
acquire one schedule-service ownership lease
→ reconstruct persistent cursor
→ choose a bounded through_inclusive instant
→ call ScheduleService.poll()
→ persist state through v0.10
→ release / renew ownership lease
~~~

The worker must be stoppable and restartable without changing occurrence
identity, duplicating admitted runs, or gaining authority over downstream macro
operations.
