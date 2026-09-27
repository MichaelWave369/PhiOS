# Macro Runtime v0.22 — Ghost-Walk Demonstration Transition Coordinator

## Status

v0.22 adds the host-side timing and orchestration layer that turns the merged
v0.21 semantic-state observer plus v0.20 transition inference into an automatic
before/action/after learning loop.

The low-level Windows mouse hook remains fast and non-blocking.

## Core boundary

~~~
BASELINE != ACTION
BASELINE != AUTHORITY
STALE BASELINE != VALID BEFORE STATE
PROCESS/WINDOW DRIFT != SAME DEMONSTRATION
INJECTED EVENT != HUMAN DEMONSTRATION
CAPTURED CLICK != VALID TRANSITION PAIR
AFTER OBSERVATION FAILURE != NO CHANGE
COORDINATION != HUMAN INTENT
~~~

## Architecture

~~~
background/host refresh
-> fresh WindowFrame
-> v0.21 BEFORE UIA state
-> arm one single-use baseline

human click
-> v0.15 listener
-> v0.14 capture
-> v0.13 Ghost-Walk observation
-> v0.22 validates baseline freshness/scope
-> bounded post-action delay
-> fresh WindowFrame
-> v0.21 AFTER UIA state
-> v0.20 transition inference
-> editable v0.12 OperatorLog note
~~~

## Baseline lifecycle

GhostWalkTransitionBaseline binds:

- session ID;
- deterministic baseline-binding SHA-256;
- exact WindowFrame;
- v0.21 state-observer receipt SHA-256;
- complete BEFORE GhostWalkUiStateSnapshot;
- baseline capture timestamp;
- zero authority flags.

The baseline is single-use.

Any listener outcome consumes the currently armed baseline, including injected
events and capture failures.

This prevents an old BEFORE state from bleeding into a later click cycle.

## Freshness

Default maximum baseline age:

~~~
1500 ms
~~~

Hard maximum configuration:

~~~
5000 ms
~~~

If the click timestamp occurs before the baseline timestamp:

~~~
HELD: BASELINE_TIME_INVALID
~~~

If the baseline age exceeds the configured bound:

~~~
HELD: BASELINE_STALE
~~~

Stale evidence is consumed and must be refreshed before another transition can
be inferred.

## Scope drift

The baseline frame and click frame must have identical stable state:

- process ID;
- window-title SHA-256;
- left/top position;
- width/height;
- display scale;
- foreground state.

Captured timestamps are intentionally excluded from stable frame identity.

Any mismatch yields:

~~~
HELD: BASELINE_SCOPE_DRIFT
~~~

## Action binding

The v0.21 baseline snapshot is initially captured before the action exists, so
its internal action_observation_sha256 binds a deterministic baseline token.

After a real Ghost-Walk click is recorded, v0.22 creates an immutable rebound
BEFORE snapshot:

~~~
same semantic state
same frame evidence
same BEFORE timestamp
new action_observation_sha256 = exact recorded click observation hash
~~~

This lets the v0.20 inference pair bind the original pre-action state to the
exact demonstrated action without rewriting the original baseline evidence.

## Injected events

Injected mouse events are ignored as demonstrations:

~~~
IGNORED: INJECTED_EVENT
~~~

The armed baseline is still consumed.

This prevents a PhiOS-generated click from leaving a stale human baseline armed
for the next real operator click.

## Post-action state

After a valid human click, v0.22 waits a bounded configurable delay:

~~~
default = 75 ms
maximum = 2000 ms
~~~

Then it observes a fresh current frame and asks v0.21 for a complete AFTER state.

If no current frame is available:

~~~
HELD: AFTER_FRAME_UNAVAILABLE
~~~

If v0.21 cannot produce a complete AFTER snapshot:

~~~
HELD: AFTER_STATE_HELD
~~~

No v0.20 inference is attempted from partial after-state evidence.

## Completed transition

When BEFORE, action, and AFTER all validate:

~~~
rebound BEFORE snapshot
+ AFTER snapshot
-> v0.20 TransitionInferenceReceipt
-> editable OperatorLog candidate summary
-> COMPLETED: INFERENCE_RECORDED
~~~

The editable note remains human context only.

It does not confirm human intent, prove causation, or create authority.

## Coordinator receipt

Reality Ledger persists:

~~~
ghostwalk-transition-coordinator-receipts.jsonl
~~~

Each TransitionCoordinatorReceipt binds:

- coordinator ID;
- session ID;
- listener receipt SHA-256;
- pointer-event SHA-256;
- action-observation SHA-256 when recorded;
- baseline SHA-256;
- baseline v0.21 state-observer receipt SHA-256;
- baseline age;
- rebound BEFORE snapshot SHA-256;
- AFTER state-observer receipt SHA-256;
- AFTER snapshot SHA-256;
- v0.20 inference receipt SHA-256;
- editable OperatorLog revision SHA-256;
- COMPLETED / HELD / IGNORED;
- exact reason;
- baseline-consumed flag;
- coordination timestamp;
- zero authority flags.

## Listener compatibility

v0.22 extends listener/capture outcomes with observation context needed by the
coordinator, but it does not perform UIA tree enumeration inside WH_MOUSE_LL.

The listener callback remains responsible only for bounded event capture and
handoff.

## Acceptance gates

### COORD-001 — full before/action/after learning

A fresh matching baseline plus a real recorded click and complete AFTER state
produces v0.20 inference, an editable OperatorLog note, and a COMPLETED receipt.

### COORD-002 — stale baseline

A baseline older than the configured maximum HOLDs and is consumed.

### COORD-003 — scope drift

Window geometry/process/title/DPI/foreground drift HOLDs before AFTER capture.

### COORD-004 — injected click

Injected input is IGNORED as a demonstration and invalidates the armed baseline.

### COORD-005 — unrecordable click

A human event that v0.14 cannot record consumes the baseline and HOLDs.

### COORD-006 — no baseline

A recorded click without a currently armed baseline HOLDs with no inference.

### COORD-007 — missing AFTER frame

Failure to observe the post-action frame HOLDs after the bounded delay.

### COORD-008 — incomplete AFTER state

A v0.21 AFTER HOLD prevents v0.20 inference.

### COORD-009 — failed baseline capture

A failed v0.21 BEFORE observation does not arm a baseline.

### COORD-010 — temporal inversion

A click timestamp before the baseline timestamp HOLDs.

### COORD-011 — anti-bleed across cycles

After one baseline is consumed, the next click cannot reuse it. A new baseline
must be explicitly refreshed before another transition can complete.

### COORD-012 — session mismatch

A baseline from one Ghost-Walk session cannot be used for a click from another.

## Deliberate non-goals

v0.22 does not yet:

- continuously refresh baselines on its own thread;
- choose an optimal baseline refresh cadence;
- automatically adopt inferred postconditions;
- infer keyboard transitions;
- read UI values or secrets;
- create execution authority;
- prove causation.

## Next rung

v0.23 should add the baseline refresh service.

That service should keep one fresh semantic baseline available while Ghost-Walk
is armed, refresh it outside the Windows hook at a bounded cadence, invalidate
it immediately on scope changes, and expose health/age metrics so long-running
demonstrations cannot silently drift into stale-state learning.