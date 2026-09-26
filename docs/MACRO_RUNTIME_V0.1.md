# Macro Runtime v0.1 — Governed Reference Core

## Status

Reference implementation for the Macro Looper / Executor runtime-semantics freeze candidate.

This rung is intentionally small and in-memory. It proves governance and execution invariants before PhiOS connects macros to real files, shell commands, browsers, APIs, repositories, models, or network infrastructure.

## Core rule

```text
CAPABILITY != AUTHORITY
OPTIMIZATION != AUTHORITY
RECEIPT != VALIDATION
DRY_RUN != LIVE
UNKNOWN != SAFE
REPLAY != REEXECUTION
ROLLBACK != ERASURE
```

## What v0.1 implements

`phios.macro_runtime` defines:

- explicit execution modes: `LIVE`, `DRY_RUN`, `REPLAY`;
- runtime lifecycle states;
- operation contracts;
- capability grants and fail-closed authority decisions;
- idempotency, replay, rollback, and side-effect classifications;
- pre-state, post-state, input, operation, and result hashes;
- execution receipts bound to the grants used for authority;
- reversible checkpoints;
- deterministic replay checks;
- an in-memory deterministic adapter used only as a reference proving ground.

## Authority

An operation can execute only when every declared required capability is represented by an explicit, non-revoked grant for the requesting principal.

A denied authority decision does not enter the adapter and commits no side effect.

This reference implementation deliberately does not infer grants from:

- prior success;
- optimization;
- model confidence;
- repeated user behavior;
- availability of an adapter.

## Dry run

`DRY_RUN` uses adapter simulation.

The runtime rejects a dry-run adapter result that claims any committed side effect.

Dry-run receipts remain distinguishable from live receipts.

## Idempotency

Idempotency is an operation property, not an execution mode.

`IDEMPOTENT` and `CONDITIONAL` operations require an idempotency key. A second live execution of the same operation identity returns `ALREADY_APPLIED` and does not commit another effect.

No automatic retry behavior is added for `NON_IDEMPOTENT` or `UNKNOWN` operations in this rung.

## Rollback

Only operations declared `REVERSIBLE` receive runtime checkpoints.

Rollback restores the checkpoint snapshot and verifies the restored state hash.

This is a reference proof only. It does not claim that arbitrary external systems are reversible.

## Replay

Only operations declared `DETERMINISTIC` can use deterministic replay.

Replay uses simulation rather than committing a second live effect, binds to the original operation hash, and requires the replay result hash to equal the original result hash.

## Receipts

Each receipt records:

- execution and operation identity;
- principal and matched grant IDs;
- execution mode and state;
- input hash;
- operation hash;
- pre-state hash;
- post-state hash;
- result hash;
- side-effect count;
- checkpoint reference;
- adapter identity and version;
- timestamps;
- parent receipt when applicable.

A receipt records execution evidence. It does not establish that a result is scientifically true, useful, or externally verified.

## Frozen v0.1 acceptance gates

The initial reference tests map directly to the frozen contract:

| Gate | Assertion |
| --- | --- |
| AUTH-001 | Valid explicit grant produces `GRANTED` |
| AUTH-002 | Missing grant produces `DENIED` and the adapter is not entered |
| DRY-001 | Dry run commits zero effects |
| IDEM-001 | Same idempotent operation identity commits once |
| ROLL-001 | Rollback restores the checkpoint state hash |
| REPLAY-001 | Deterministic replay reproduces the original result hash without a new effect |
| RECEIPT-001 | Receipt binds operation, input, result, and authority-grant evidence |

## Deliberate non-goals

v0.1 does not yet implement:

- real filesystem, shell, browser, API, GitHub, model, or network adapters;
- persistent idempotency records;
- persistent macro receipts in the Reality Ledger;
- schedules or triggers;
- branching or parallel macro graphs;
- retry orchestration;
- compensation for external effects;
- the five-module higher-order optimization layer;
- automatic macro learning;
- optimization-based parameter changes.

Those belong to later rungs only after this reference core remains green.

## Next rung

The next safe rung is integration with the existing PhiOS authority / Reality Ledger spine while preserving the same tests. The reference adapter should remain in the suite permanently as a deterministic conformance target.
