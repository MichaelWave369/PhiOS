# PhiOS App Platform v0.42 — Cleanup Journal Reconciliation / Recovery Contract

## Status

Alpha contract.

Schemas:

- `phios.cleanup_reconciliation_observation.v0.1`
- `phios.cleanup_reconciliation_plan.v0.1`
- `phios.cleanup_reconciliation_review.v0.1`
- `phios.cleanup_reconciliation_receipt.v0.1`

## Purpose

v0.42 reconciles a v0.41 `prepared` retained-cleanup journal when no authoritative final cleanup receipt can be relied upon.

The central rule is:

> A stranded journal is evidence that destructive authority existed, not evidence that cleanup completed.

v0.42 therefore performs a fresh filesystem observation before any recovery action is planned.

## Inputs

Reconciliation requires:

- one valid v0.41 `RetainedCleanupJournal`;
- the exact original v0.41 `RetainedCleanupPlan` bound by that journal;
- configured install root;
- configured desktop-bundle root;
- configured XDG applications root;
- configured receipt root.

The journal and plan must agree on:

- plan SHA;
- app ID;
- retained and active versions;
- cleanup scope;
- retained bundle path;
- retained install path;
- retention-marker path;
- retained grant SHA;
- active grant SHA;
- retention-marker SHA;
- originally approved cleanup permissions.

Mismatch fails before observation.

## Observation is non-authoritative

`observe_cleanup_reconciliation` does not grant cleanup, rollback, or reconciliation authority.

It records:

```text
reconciliation_authority = false
cleanup_authority        = false
rollback_authority       = false
```

If the receipt root does not exist, observation treats it as empty and does not create it.

Planning uses the same read-only observation path.

## Observed state

The observation records four current state surfaces.

### Active state

Active state is either:

```text
verified
invalid
```

Verification reloads the active governed desktop bundle and reruns the existing v0.40 current-bundle proof, including:

- v0.38 bundle structure;
- desktop/browser/static/install/grant binding;
- current installed ancestry;
- governed desktop-entry path;
- active desktop-entry SHA.

The observed active plan/grant/entry must still match the original v0.41 cleanup plan.

Any active-state drift makes reconciliation `invalid`.

### Retention marker state

Marker state is:

```text
present_verified
absent
present_invalid
```

If present, the marker must:

- remain contained under the desktop root;
- parse as the exact v0.40 retention marker type;
- match the original marker SHA;
- bind the planned retained bundle/grant;
- bind the planned active bundle/grant.

### Retained desktop bundle state

Bundle state is:

```text
present_verified
absent
present_invalid
```

If present, it is reloaded through the v0.38/v0.40 bundle path and must match:

- retained desktop-plan SHA;
- retained grant SHA;
- retained install-receipt SHA;
- current installed ancestry.

### Retained install-tree state

Install state is:

```text
present_verified
absent
present_invalid
```

If present, its complete current tree digest must still match the v0.41 cleanup plan.

## Existing receipt detection

Observation also checks for valid receipts already bound to the stranded journal.

It counts:

- valid v0.41 cleanup receipts whose `retained_cleanup_journal_sha256` matches;
- valid v0.42 reconciliation receipts whose `retained_cleanup_journal_sha256` matches.

If either count is nonzero, the journal is not considered unresolved and classification is `invalid` for new reconciliation.

This prevents duplicate authoritative evidence.

## Classifications

Classification is exactly:

```text
untouched
partial
effectively_complete
invalid
```

### untouched

For either cleanup scope:

- active state is verified;
- marker is present and verified;
- retained bundle is present and verified;
- retained install tree is present and verified;
- no bound cleanup receipt exists;
- no bound reconciliation receipt exists.

This means the journal was prepared, but no intended deletion is visible.

Allowed actions:

```text
cancel
complete
```

### partial

`partial` means:

- active state is still verified;
- no observed retained target is invalid;
- no previous authoritative receipt resolves the journal;
- some, but not all, authorized cleanup targets are already absent.

For `desktop_bundle_and_install`, examples include:

- marker absent, bundle present, install present;
- marker absent, bundle absent, install present;
- marker present, bundle absent, install present.

Allowed action:

```text
complete
```

### effectively_complete

For `desktop_bundle_only`:

```text
marker = absent
retained bundle = absent
retained install = present_verified
```

For `desktop_bundle_and_install`:

```text
marker = absent
retained bundle = absent
retained install = absent
```

Active state must remain verified and no authoritative receipt may already resolve the journal.

Allowed action:

```text
finalize
```

### invalid

Examples include:

- active app or launcher drift;
- present but malformed/tampered retained target;
- marker digest/binding mismatch;
- valid cleanup receipt already exists;
- valid reconciliation receipt already exists;
- desktop-only cleanup finds the retained install tree missing;
- unsupported or internally inconsistent state.

Allowed actions:

```text
none
```

## Why desktop-only missing install is invalid

A v0.41 `desktop_bundle_only` plan never authorized deletion of the retained install tree.

If that tree is missing during reconciliation, v0.42 does not call the state merely `partial` because the disappearance lies outside the intended destructive transition.

It is classified `invalid` and requires external investigation rather than cleanup continuation.

## Deterministic observation

`phios.cleanup_reconciliation_observation.v0.1` binds:

- journal SHA;
- original cleanup-plan SHA;
- app/version context;
- cleanup scope;
- marker state;
- retained bundle state;
- retained install state;
- active state;
- count of bound cleanup receipts;
- count of bound reconciliation receipts;
- classification;
- deterministic sorted issue codes;
- allowed actions;
- zero action authority;
- canonical observation SHA.

Repeated observation of unchanged state produces the same observation SHA.

## Reconciliation planning

A reconciliation plan can request exactly one action:

```text
cancel
complete
finalize
```

The requested action must be allowed by the current observation classification.

The plan binds:

- action;
- classification;
- observation SHA;
- stranded journal SHA;
- original cleanup-plan SHA;
- app/version context;
- cleanup scope;
- retained bundle/install/marker paths;
- active bundle path;
- active grant SHA;
- exact requested reconciliation permissions;
- zero authority;
- canonical reconciliation-plan SHA.

## Action authority

### cancel

Legal only from `untouched`.

Permission:

```text
cleanup.reconcile.cancel
```

`cancel` performs no deletion and creates no v0.41 cleanup receipt.

It writes only a v0.42 reconciliation receipt recording that the untouched attempt was closed.

### complete

Legal from:

```text
untouched
partial
```

Permissions require both fresh recovery authority and the original destructive scope authority again.

For desktop-only:

```text
cleanup.reconcile.complete
desktop.cleanup.retained
```

For desktop + install:

```text
cleanup.reconcile.complete
desktop.cleanup.retained
install.cleanup.retained
```

The prepared v0.41 journal is not reusable deletion authority.

### finalize

Legal only from `effectively_complete`.

Permission:

```text
cleanup.reconcile.finalize
```

`finalize` deletes nothing.

It creates the missing v0.41 cleanup receipt from the already verified final filesystem state, then records the v0.42 reconciliation.

## Review

`review_cleanup_reconciliation` reconstructs the canonical plan and exposes:

- reconciliation-plan SHA;
- requested action;
- observed classification;
- observation SHA;
- journal SHA;
- original cleanup-plan SHA;
- app/version/scope context;
- exact requested reconciliation permissions;
- zero reconciliation/cleanup/rollback authority.

Reviewing a recovery action is not approval.

## Execution approvals

Execution requires exact approval of:

1. reconciliation-plan SHA;
2. observation SHA;
3. stranded cleanup-journal SHA;
4. original cleanup-plan SHA;
5. exact reconciliation/action permission set.

Missing or extra permissions fail closed.

## Re-observation before action

Immediately before mutation, execution performs a new observation.

The new observation SHA must equal the reviewed observation SHA.

The requested action must still be legal for that classification.

If state changed after review, execution stops.

## Complete execution

`complete` removes only remaining authorized targets:

1. retention marker if still present;
2. retained desktop bundle if still present;
3. retained install tree if scope authorizes it and it is still present.

Present targets reached this point only after observation classified them as verified rather than invalid.

After deletion, v0.42 re-observes the filesystem.

The resulting classification must be `effectively_complete` before any final cleanup receipt is written.

## Finalize execution

`finalize` performs no target deletion.

It re-observes and requires the reviewed `effectively_complete` state to remain unchanged.

It then emits the missing v0.41 cleanup receipt.

## Synthesized v0.41 cleanup receipt

For `complete` and `finalize`, v0.42 uses the original v0.41 plan and journal to construct a standard `RetainedCleanupReceipt`.

This keeps downstream evidence on the existing v0.41 cleanup schema rather than inventing a second meaning for completed cleanup.

The synthesized receipt binds:

- original cleanup-plan SHA;
- original journal SHA;
- cleanup scope;
- removed/retired target identities;
- active bundle/grant;
- optional retained-install removal evidence;
- cleanup authority true;
- rollback authority false;
- status `cleaned`.

## Reconciliation receipt

`phios.cleanup_reconciliation_receipt.v0.1` records:

- UUID/time;
- reconciliation-plan SHA;
- reviewed observation SHA;
- stranded journal SHA;
- original cleanup-plan SHA;
- app ID;
- action;
- classification before;
- classification after;
- optional synthesized cleanup-receipt SHA;
- exact reconciliation permissions;
- reconciliation authority true;
- action-specific cleanup authority;
- rollback authority false;
- status.

Statuses are:

```text
cancelled
completed
finalized
```

Status/action/classification combinations are strictly validated.

## Receipt ordering

For `complete` and `finalize`, receipt ordering is:

```text
verify effectively_complete state
        ↓
persist v0.41 cleanup receipt
        ↓
persist v0.42 reconciliation receipt
```

If the cleanup receipt succeeds but the reconciliation receipt fails, the valid cleanup receipt remains.

On a later observation, that bound cleanup receipt makes the journal `invalid` for another reconciliation attempt.

This prevents duplicate cleanup receipts from being minted merely because the second receipt write failed.

## Cancel ordering

For `cancel`, no cleanup receipt is created.

The v0.42 reconciliation receipt itself resolves the journal.

Subsequent observation finds the bound reconciliation receipt and blocks duplicate reconciliation.

## CLI

Observe:

```bash
phi-app observe-cleanup-reconciliation \
  cleanup-journal.json \
  retained-cleanup-plan.json
```

Plan cancellation:

```bash
phi-app plan-cleanup-reconciliation \
  cleanup-journal.json \
  retained-cleanup-plan.json \
  --action cancel \
  > cleanup-reconciliation-plan.json
```

Plan completion:

```bash
phi-app plan-cleanup-reconciliation \
  cleanup-journal.json \
  retained-cleanup-plan.json \
  --action complete \
  > cleanup-reconciliation-plan.json
```

Plan finalization:

```bash
phi-app plan-cleanup-reconciliation \
  cleanup-journal.json \
  retained-cleanup-plan.json \
  --action finalize \
  > cleanup-reconciliation-plan.json
```

Review:

```bash
phi-app review-cleanup-reconciliation cleanup-reconciliation-plan.json
```

Execute:

```bash
phi-app execute-cleanup-reconciliation \
  cleanup-reconciliation-plan.json \
  cleanup-journal.json \
  retained-cleanup-plan.json \
  --approve-reconciliation-plan-sha EXACT_RECONCILIATION_PLAN_SHA256 \
  --approve-observation-sha EXACT_OBSERVATION_SHA256 \
  --approve-journal-sha EXACT_JOURNAL_SHA256 \
  --approve-cleanup-plan-sha EXACT_ORIGINAL_CLEANUP_PLAN_SHA256 \
  --allow-reconciliation-permission ACTION_PERMISSION
```

`complete` additionally requires the exact original destructive cleanup permissions.

## CI verification model

v0.42 tests cover:

- untouched classification;
- partial classification;
- effectively-complete classification;
- invalid classification;
- cancel and duplicate-resolution blocking;
- complete from partial;
- complete from untouched with fresh destructive permissions;
- finalize without additional deletion;
- desktop-only unauthorized install disappearance becoming invalid;
- active launcher drift becoming invalid;
- retained target tamper becoming invalid;
- pre-existing v0.41 cleanup receipt blocking reconciliation;
- exact observation/plan/journal approval requirements;
- illegal action/classification combinations;
- cleanup-receipt success followed by reconciliation-receipt failure preventing duplicate retry;
- observation/plan/receipt digest-tamper rejection;
- read-only observation not creating a missing receipt root.

## Explicit non-capabilities

v0.42 does not:

- infer why an invalid target changed;
- restore deleted bytes;
- override active-state drift;
- auto-select a recovery action;
- reuse old cleanup authority implicitly;
- repair malformed retained bundles;
- delete outside the original v0.41 cleanup scope;
- bypass the original cleanup plan;
- treat a prepared journal as successful cleanup evidence.

## Planned next rung

v0.43 should add an **Unresolved Lifecycle Transition Gate**.

That rung should make update, rollback, retained cleanup, and related lifecycle mutation check for unresolved prepared journals before acting, so a v0.42 reconciliation is not merely available but becomes required before new mutation can proceed.
