# PhiOS App Platform v0.42

PhiOS App Platform v0.42 adds the **Cleanup Journal Reconciliation / Recovery Contract**.

v0.41 deliberately leaves a durable `prepared` journal if destructive retained-version cleanup begins but does not reach a final receipt. v0.42 turns that ambiguous state into a deterministic observation and a separately approved recovery action.

## Core rule

```text
journal exists
≠ cleanup completed

some targets are missing
≠ cleanup may continue automatically

filesystem matches final state
≠ a missing receipt may be fabricated silently
```

Reconciliation observes first, classifies second, and acts only under new explicit authority.

## Classifications

v0.42 classifies one journal + original cleanup plan as:

```text
untouched
partial
effectively_complete
invalid
```

The classification is derived from the current:

- active governed app state;
- retained desktop bundle state;
- retained install-tree state;
- retention-marker state;
- presence of any already valid cleanup receipt;
- presence of any already valid reconciliation receipt.

Observation itself grants no authority and does not create the receipt directory if it is absent.

## Allowed actions

```text
untouched
  → cancel
  → complete

partial
  → complete

effectively_complete
  → finalize

invalid
  → no action
```

### Cancel

`cancel` closes an untouched stranded journal without deleting anything.

Permission:

```text
cleanup.reconcile.cancel
```

No v0.41 cleanup receipt is created because cleanup did not occur.

### Complete

`complete` resumes an untouched or partial cleanup.

It requires:

```text
cleanup.reconcile.complete
+ the original v0.41 destructive permissions again
```

For desktop-only cleanup that means:

```text
cleanup.reconcile.complete
desktop.cleanup.retained
```

For desktop + install cleanup:

```text
cleanup.reconcile.complete
desktop.cleanup.retained
install.cleanup.retained
```

A stranded journal is therefore not reusable deletion authority.

### Finalize

`finalize` is available only when the filesystem already matches the intended final cleanup state but the v0.41 cleanup receipt is missing.

Permission:

```text
cleanup.reconcile.finalize
```

It performs no deletion. It writes the missing v0.41 cleanup receipt, then writes the v0.42 reconciliation receipt.

## Duplicate-evidence protection

If a valid v0.41 cleanup receipt already binds the journal, reconciliation becomes `invalid`.

If a valid v0.42 reconciliation receipt already binds the journal, reconciliation also becomes `invalid`.

This prevents retries from minting multiple authoritative receipts for the same stranded transition.

## CLI

Observe:

```bash
phi-app observe-cleanup-reconciliation \
  cleanup-journal.json \
  retained-cleanup-plan.json
```

Plan one allowed action:

```bash
phi-app plan-cleanup-reconciliation \
  cleanup-journal.json \
  retained-cleanup-plan.json \
  --action complete \
  > cleanup-reconciliation-plan.json
```

Review:

```bash
phi-app review-cleanup-reconciliation cleanup-reconciliation-plan.json
```

Execute only after exact approval of the reconciliation plan, observation, journal, original cleanup plan, and action permissions.

See `docs/PHIOS_APP_PLATFORM_V0.42_CLEANUP_RECONCILIATION.md`.
