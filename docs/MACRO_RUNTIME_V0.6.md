# Macro Runtime v0.6 — Persistent MacroRun Journal + Resume Reconstruction

## Status

Append-only persistence and restart-safe reconstruction for deterministic
MacroRunState snapshots.

v0.6 does not execute work and does not add authority. It makes the v0.4 runner
state durable enough to survive process restart without replacing history with
a mutable latest-state file.

## Core boundary

~~~
JOURNAL != AUTHORITY
PERSISTED STATE != REALITY PROOF
LATEST LINE != VALID LATEST STATE
RESUME != REEXECUTION
HISTORY != MUTABLE
RESUME RECEIPT != EXECUTION RECEIPT
~~~

## Persistent path

Reality Ledger now stores:

~~~
macro-run-journal.jsonl
macro-run-resume-receipts.jsonl
~~~

The journal is append-only.

Each entry includes the complete deterministic MacroRunState snapshot plus
hashes binding it to the prior journal head and prior state.

## MacroRun journal entry

Each MacroRunJournalEntry binds:

- stable run ID;
- contiguous sequence number;
- START or TRANSITION kind;
- macro ID and version;
- exact MacroPlan SHA-256;
- previous journal-entry SHA-256;
- previous MacroRunState SHA-256;
- current MacroRunState SHA-256;
- complete current state snapshot;
- sorted unique evidence-reference SHA-256 values;
- zero authority flags.

Sequence zero is always:

~~~
kind = START
previous_entry_sha256 = null
previous_state_sha256 = null
~~~

All later entries are:

~~~
kind = TRANSITION
previous_entry_sha256 = exact prior entry hash
previous_state_sha256 = exact prior state hash
~~~

## Hash chain

For a run:

~~~
Entry 0
  state S0
      ↓
Entry 1
  previous_entry = hash(Entry 0)
  previous_state = hash(S0)
  state S1
      ↓
Entry 2
  previous_entry = hash(Entry 1)
  previous_state = hash(S1)
  state S2
~~~

Reconstruction validates every persisted entry before considering the final
snapshot resumable.

It verifies:

- entry hash;
- persisted state hash;
- contiguous sequence numbers;
- stable run ID;
- stable macro ID/version;
- stable plan hash;
- previous-entry chain;
- previous-state chain;
- nondecreasing runner transition count;
- no continuation after a terminal state.

A malformed or tampered chain fails closed.

## Optimistic append guard

Every transition after START requires:

~~~
expected_head_sha256
~~~

The supplied expected head must equal the currently validated journal head.

This prevents a caller holding stale run state from silently appending a new
transition onto a newer history.

Concurrent writes may still create an invalid fork if they race after the same
head check. Such a fork is not accepted during reconstruction because sequence
or hash-chain validation fails.

A later rung may add atomic per-run append claims if multi-writer unattended
execution requires them.

## Evidence references

A transition may include sorted unique SHA-256 references to evidence that
caused the new state.

Examples include:

- DoDispatchReceipt;
- condition evidence;
- approval evidence;
- callee receipt;
- checkpoint receipt.

The journal does not reinterpret those referenced artifacts.

Their presence establishes provenance linkage, not truth or authority.

## Reconstruction

MacroRunJournal.reconstruct() scans the complete history for one run ID and
returns only after the entire chain validates.

The reconstructed state must still match the supplied MacroPlan:

~~~
macro_id
macro_version
plan_sha256
~~~

A different plan cannot resume the stored run.

## Resume receipt

MacroRunJournal.resume() creates an append-only MacroRunResumeReceipt
containing:

- run ID;
- macro identity;
- plan SHA-256;
- validated entry count;
- validated journal-head SHA-256;
- resumed MacroRunState SHA-256;
- resumed runner status;
- caller-supplied timezone-aware resume timestamp;
- zero authority flags.

The receipt means the exact persisted chain was validated and the exact state
was recovered.

It does not mean the recovered workflow is authorized to continue.

Any subsequent real DO still returns to the existing:

~~~
MacroRunner
→ GovernedDoDispatcher
→ MacroSpineBridge
→ ActionLease
→ GovernedLeasedExecutionHandoff
→ PhiOS Spine
~~~

authority path.

## Terminal states

The journal cannot append a state after:

~~~
COMPLETED
FAILED
ABORTED
~~~

HELD remains resumable because held workflows may later receive the missing
evidence or authority required to continue.

## v0.6 acceptance gates

### JOURNAL-001 — chained persistence

START and TRANSITION entries must form an exact entry-hash and state-hash chain,
and reconstruction returns the latest state.

### JOURNAL-002 — restart-safe resume

A new MacroRunJournal instance over the same Reality Ledger must reconstruct the
waiting state, emit a resume receipt, accept later operation evidence through
the MacroRunner, append the completed state, and reconstruct COMPLETED after a
second restart.

### JOURNAL-003 — stale writer rejection

A transition using an old expected_head_sha256 must be rejected without
appending another journal line.

### JOURNAL-004 — tamper detection

Modified persistent history must fail reconstruction.

### JOURNAL-005 — plan pinning

A persisted run cannot reconstruct against a MacroPlan with a different plan
hash.

### JOURNAL-006 — terminal history freeze

No state may be appended after a terminal MacroRunState.

### JOURNAL-007 — run isolation

Multiple run IDs may share the same journal file while reconstructing
independently.

## What is now complete

The governed macro path now supports:

~~~
describe
→ plan
→ run
→ pause
→ persist
→ restart
→ reconstruct
→ resume
→ dispatch governed effect
→ receipt
→ persist new state
→ complete
~~~

This is the minimum persistence layer needed before unattended starts become
credible.

## Deliberate non-goals

v0.6 does not add:

- schedules;
- triggers;
- background workers;
- automatic ActionLease acquisition;
- atomic multi-writer journal locking;
- parameter substitution;
- recursive CALL execution;
- automatic condition resolution;
- browser / shell / API / model adapters;
- workflow learning;
- higher-order optimization.

## Next rung

v0.7 should add a Run Coordinator around the journal and runner.

Its initial responsibility should be orchestration, not scheduling:

~~~
create run ID
→ persist START
→ advance runner
→ persist pause
→ accept external resolution
→ advance
→ persist next state
→ reconstruct after restart
~~~

Only once one coordinator owns the transition/journal lifecycle should a later
scheduler or trigger system be allowed to start unattended runs.
