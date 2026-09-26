# Macro Runtime v0.9 — Deterministic Wall-Clock Schedule Producer

## Status

Pure wall-clock schedule evaluation that emits stable TriggerObservation objects
into the merged v0.8 Run Start / Trigger Contract.

v0.9 is intentionally not a background scheduler service.

It evaluates due occurrences only when called.

## Core boundary

~~~
SCHEDULE != AUTHORITY
DUE != AUTHORIZED
OCCURRENCE != RUN
TRIGGER OBSERVATION != COMMAND
POLL != BACKGROUND WORKER
MISFIRE POLICY != RETRY POLICY
~~~

A schedule may emit a due observation.

That observation must still pass:

~~~
TriggerObservation
→ RunStartRequest
→ MacroRunStartGate
→ MacroRunCoordinator
~~~

and any later DO still requires the existing governed ActionLease / Spine path.

## Schedule definition

WallClockSchedule binds:

- schedule ID;
- source ID;
- cadence;
- IANA timezone;
- local wall-clock time;
- start date;
- optional end date;
- optional weekly weekday set;
- misfire policy;
- ambiguous-time policy;
- nonexistent-time policy;
- maximum occurrences per poll;
- zero authority flags;
- deterministic schedule SHA-256.

Supported cadences:

~~~
ONCE
DAILY
WEEKLY
~~~

WEEKLY schedules require an explicit Monday-to-Sunday ordered weekday tuple.

## Wall-clock semantics

The schedule is interpreted in its declared IANA timezone.

For example:

~~~
timezone = America/Los_Angeles
local_time = 16:00:00
~~~

means 4:00 PM local wall-clock time, not a fixed UTC offset.

This distinction matters across daylight-saving transitions.

## DST ambiguity

Some local wall-clock times occur twice when clocks move backward.

v0.9 requires an explicit policy:

~~~
EARLIER
LATER
~~~

For an ambiguous local time such as 01:30 during fall-back:

- EARLIER selects the first UTC instant;
- LATER selects the second UTC instant.

The chosen UTC instant becomes part of the occurrence identity.

Therefore changing the ambiguity policy changes the schedule hash and occurrence
identity.

## DST nonexistent times

Some local times do not exist when clocks move forward.

v0.9 currently supports:

~~~
NonexistentTimePolicy.SKIP
~~~

A nonexistent local time produces no occurrence for that date.

The producer does not silently move the event forward or backward.

Future policies may be added only as explicit contract changes.

## Poll window

WallClockScheduleProducer.poll() takes:

~~~
after_exclusive
through_inclusive
~~~

Both must be timezone-aware datetimes.

The producer emits due occurrences satisfying:

~~~
after_exclusive < occurrence <= through_inclusive
~~~

The poll window is bounded to at most 366 days.

This protects a pure evaluator from accidentally becoming an unbounded history
scanner.

## Misfire policy

v0.9 supports:

~~~
CATCH_UP
LATEST_ONLY
~~~

### CATCH_UP

Emit every due occurrence in the poll window.

If the number of selected occurrences exceeds max_occurrences_per_poll, the
poll fails closed.

It does not truncate silently.

### LATEST_ONLY

If multiple occurrences were missed in the poll window, emit only the latest.

candidate_count still records how many due occurrences existed.

## Occurrence identity

Each ScheduleOccurrence binds:

- schedule ID;
- schedule SHA-256;
- resolved local due timestamp with offset;
- exact UTC due timestamp;
- deterministic occurrence ID;
- zero authority flags.

The occurrence ID is derived from:

~~~
schedule SHA-256
local resolved due timestamp
UTC due timestamp
~~~

Re-evaluating an overlapping poll window therefore reproduces the exact same
occurrence identity.

## Stable trigger observations

Each occurrence emits one TriggerObservation:

~~~
trigger_type = schedule
source_id = schedule.source_id
source_event_id = occurrence.occurrence_id
observed_at = occurrence.due_at_utc
payload_sha256 = occurrence.occurrence_sha256
evidence_ref_sha256s = (schedule.schedule_sha256,)
~~~

The observation timestamp is the semantic due instant, not the wall-clock time
at which a polling process happened to notice it.

This is deliberate.

If the same occurrence is discovered again after restart, it produces the same
TriggerObservation hash.

The merged v0.8 trigger dedupe contract can therefore block duplicate run starts.

## v0.9 acceptance gates

### SCHEDULE-001 — deterministic daily occurrence

Overlapping polls that include the same due occurrence must produce identical:

- occurrence ID;
- occurrence hash;
- TriggerObservation hash.

### SCHEDULE-002 — weekly weekday scope

A WEEKLY schedule emits only the declared weekdays.

### SCHEDULE-003 — latest-only misfire

A poll spanning multiple missed daily occurrences with LATEST_ONLY emits exactly
one trigger for the latest occurrence while retaining the candidate count.

### SCHEDULE-004 — spring-forward skip

A nonexistent local wall-clock time emits no occurrence.

### SCHEDULE-005 — fall-back ambiguity policy

The same ambiguous local time under EARLIER versus LATER resolves to different
UTC instants and different occurrence identities.

### SCHEDULE-006 — catch-up bound

CATCH_UP fails closed if due occurrences exceed max_occurrences_per_poll.

### SCHEDULE-007 — bounded polling

A poll window greater than 366 days is rejected.

### SCHEDULE-008 — v0.8 integration

A schedule occurrence may enter the merged Run Start gate and create persistent
macro control flow.

For a DO macro:

~~~
RunStartReceipt.status == STARTED
MacroRunState.status == WAITING_OPERATION
Spine execution receipts == 0
~~~

### SCHEDULE-009 — zero-authority chain

WallClockSchedule, ScheduleOccurrence, and TriggerObservation all remain
zero-authority objects.

## What is now complete

The macro stack can now move from a deterministic wall-clock definition to
persistent governed control flow:

~~~
WallClockSchedule
→ due occurrence
→ deterministic TriggerObservation
→ RunStartRequest
→ MacroRunStartGate
→ MacroRunCoordinator
→ persistent MacroRun
→ WAITING_* boundary
~~~

A due schedule starts procedure state.

It does not authorize effects.

## Deliberate non-goals

v0.9 does not add:

- a background process;
- sleep loops;
- cron parsing;
- persisted schedule cursors;
- automatic polling;
- distributed scheduler locks;
- webhook triggers;
- filesystem triggers;
- message triggers;
- model-generated triggers;
- automatic ActionLease acquisition;
- automatic retries.

## Next rung

v0.10 should add a Schedule Service state contract around the pure producer.

Its initial job should be:

~~~
persist schedule cursor
→ poll bounded window
→ emit deterministic occurrences
→ submit each through v0.8
→ persist resulting cursor / receipts
→ reconstruct safely after restart
~~~

The service must not perform macro operations itself.

Only after persistent cursor ownership and restart-safe polling are proven
should PhiOS gain a continuously running scheduler worker.
