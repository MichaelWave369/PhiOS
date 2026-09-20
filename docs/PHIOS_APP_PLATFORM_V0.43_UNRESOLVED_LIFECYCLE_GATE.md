# PhiOS App Platform v0.43 — Unresolved Lifecycle Transition Gate

## Status

Alpha contract.

Runtime surface:

- `phios.apps.lifecycle_gate`
- `phi-app observe-lifecycle-gate APP_ID`

## Purpose

v0.43 makes the v0.42 cleanup-reconciliation path mandatory before new governed
desktop lifecycle mutation can continue for an app with a stranded prepared v0.41
cleanup journal.

The central rule is:

> Recovery being available is not enough. Unresolved destructive evidence blocks new mutation.

v0.43 adds no lock file, active-transition pointer, or mutable lifecycle database.
Gate state is derived from the append-only evidence that already exists.

## Scope

The execution gate is checked before:

- desktop update;
- desktop rollback;
- retained-version cleanup.

Cleanup reconciliation is intentionally exempt because it is the operation that clears
an unresolved prepared journal.

The gate is app-scoped. An unresolved cleanup for one app does not block lifecycle
mutation for another app.

## Evidence sources

The gate reads only the configured lifecycle receipt root and recognizes bounded,
non-symlink JSON files matching:

```text
retained-cleanup-journal-*.json
retained-cleanup-*.json
retained-cleanup-reconciliation-*.json
```

The first pattern is parsed as a v0.41 `RetainedCleanupJournal`.

Ordinary cleanup receipts are parsed as v0.41 `RetainedCleanupReceipt`.

Reconciliation receipts are parsed as v0.42 `CleanupReconciliationReceipt`.

No arbitrary path is accepted from evidence contained inside those files.

## Unresolved definition

A valid prepared v0.41 journal is unresolved for its app when no valid resolving
evidence binds its exact canonical journal SHA-256.

Resolving evidence is one of:

1. a valid v0.41 cleanup receipt bound to the journal; or
2. a valid v0.42 cancellation receipt bound to the journal.

A completed/finalized v0.42 reconciliation does not independently clear the gate.
The v0.42 ordering contract writes the corresponding v0.41 cleanup receipt first, and
that cleanup receipt is the resolving evidence.

Therefore a dangling completed/finalized reconciliation receipt whose cleanup receipt is
missing does not magically make the journal safe.

## Why cleanup receipt alone clears the gate

v0.42 explicitly permits this failure ordering:

```text
persist v0.41 cleanup receipt
        ↓
v0.42 reconciliation receipt write fails
```

The valid cleanup receipt already proves completion of the destructive operation and
prevents duplicate reconciliation. v0.43 therefore treats that journal as resolved.

## Cancellation

A cancellation performs no cleanup and creates no v0.41 cleanup receipt.

Its valid v0.42 reconciliation receipt is therefore the direct resolving evidence for
the prepared journal.

## Invalid evidence

A malformed or digest-invalid cleanup/reconciliation receipt is ignored as resolution.

A malformed prepared cleanup journal fails the gate scan closed because the system
cannot safely determine which lifecycle state it represents.

Symlinked lifecycle receipt roots or journal files are rejected.

The scan is bounded by file count and per-file byte size.

## Mutation behavior

Each destructive service checks the gate before performing its ordinary current-state
revalidation or mutation.

If unresolved journals exist, execution fails before:

- staging a candidate bundle;
- replacing a desktop entry;
- removing a retention marker;
- deleting a retained desktop bundle;
- deleting a retained installed tree;
- creating another cleanup journal.

The error identifies the app and short prefixes of the unresolved journal digests so
the operator can inspect/reconcile the exact evidence.

## Read-only observation

Operators can inspect the gate without granting mutation or reconciliation authority:

```bash
phi-app observe-lifecycle-gate \
  phi.example-app \
  --receipt-root ~/.phios/apps/runtime-receipts
```

The observation reports:

- app ID;
- receipt root;
- clear/blocked status;
- unresolved journal IDs/digests;
- retained/active versions;
- cleanup scope;
- counts of valid cleanup/reconciliation receipts seen;
- `mutation_authority=false`;
- `reconciliation_authority=false`.

Observation does not create the receipt root when it does not already exist.

## Recovery path

When the gate is blocked, the operator uses the existing v0.42 workflow:

```text
observe-cleanup-reconciliation
        ↓
plan-cleanup-reconciliation
        ↓
review-cleanup-reconciliation
        ↓
execute-cleanup-reconciliation
```

After valid resolving evidence exists, the v0.43 observation becomes clear and ordinary
lifecycle mutation may be reviewed/executed again.

## CI verification model

v0.43 tests cover:

- absent receipt root is clear and remains uncreated;
- prepared journal blocks same-app mutation;
- valid v0.41 cleanup receipt resolves the journal;
- valid v0.42 cancellation resolves the journal;
- completed reconciliation without its v0.41 cleanup receipt does not resolve;
- unresolved journal for another app does not block the target app;
- malformed journal evidence fails closed;
- update checks the gate before other execution work;
- rollback checks the gate before other execution work;
- retained cleanup checks the gate before other execution work.

## Explicit non-capabilities

v0.43 does not:

- choose a reconciliation action;
- grant reconciliation authority;
- infer why a cleanup was interrupted;
- repair malformed evidence;
- restore deleted bytes;
- replace v0.42 reconciliation;
- create lifecycle lock files;
- serialize unrelated apps globally;
- bypass any existing update/rollback/cleanup approval.

## Planned next rung

With the local app lifecycle now closed from acquisition through cleanup recovery,
v0.44 should add a **Governed Release Discovery / Candidate Selection Contract**.

That rung can discover remote candidate releases without granting update authority,
bind exact repository/tag/commit evidence, keep version ordering policy separate from
mutation authority, and feed an explicitly selected candidate back into the existing
v0.26–v0.40 acquisition/build/install/update pipeline.
