# PhiOS App Platform v0.41 — Retained Version Cleanup / Lifecycle Contract

## Status

Alpha contract.

Schemas:

- `phios.retained_cleanup_plan.v0.1`
- `phios.retained_cleanup_review.v0.1`
- `phios.retained_cleanup_journal.v0.1`
- `phios.retained_cleanup_receipt.v0.1`

## Purpose

v0.41 governs destruction of one retained inactive desktop version created by the v0.40 update/rollback lifecycle.

The central rule is:

> Retention evidence proves why a version is inactive; it does not make that version disposable.

Cleanup is a separate destructive authority with its own exact review and approval.

## Relationship to v0.40

v0.40 leaves two governed versions after update or rollback:

```text
active version
retained inactive version
```

The retained version remains a valid rollback target until v0.41 cleanup retires that evidence and removes the approved retained state.

v0.41 never treats the active bundle as a cleanup candidate.

## Cleanup scopes

The cleanup scope is explicit and canonical.

### desktop_bundle_only

Removes:

- retained v0.38 desktop bundle;
- associated v0.40 retention marker.

Preserves:

- retained v0.33 installed artifact tree.

Permission:

```text
desktop.cleanup.retained
```

### desktop_bundle_and_install

Removes:

- retained v0.38 desktop bundle;
- associated v0.40 retention marker;
- retained v0.33 installed artifact tree.

Permissions:

```text
desktop.cleanup.retained
install.cleanup.retained
```

An install-tree removal is therefore never implied merely by desktop-bundle cleanup.

## Cleanup planning inputs

Planning starts from the exact retained-marker path and configured:

- desktop bundle root;
- installed app root;
- XDG applications root;
- requested cleanup scope.

Planning does not consume a stale v0.39 catalog snapshot.

## Retention marker validation

The selected marker must:

- be a contained regular non-symlink file under the desktop root;
- parse as `DesktopRetentionMarker`;
- have the deterministic retained-plan filename;
- live beside the retained bundle;
- bind the retained app/version/plan/grant;
- bind the active app/version/plan/grant.

v0.41 also scans the app directory and requires exactly one valid retention marker targeting that retained bundle.

Duplicate valid markers for the same retained bundle make cleanup ambiguous and fail closed.

## Active-version proof

Planning reloads the active governed bundle and runs the v0.40 current-bundle verification path.

This verifies:

- active five-file v0.38 bundle structure;
- grant/plan/browser/static/install digest bindings;
- current installed ancestry;
- current XDG desktop-entry path;
- current desktop-entry SHA matching the active grant.

The current desktop-entry digest is recorded in the cleanup plan.

## Retained-version proof

Planning separately reloads the retained governed bundle and verifies:

- retained bundle structure and digest bindings;
- current retained installed ancestry;
- retained grant points to the same governed desktop-entry path as the active grant;
- current desktop-entry digest does not equal the retained grant's desktop-entry digest.

That last check establishes that the retained version is not currently selected by the authoritative desktop-entry bytes.

## Installed-tree proof

The retained install receipt is reconstructed from the retained bundle.

The retained install path must remain under the configured install root.

The complete installed tree is snapshotted again and must match the retained install receipt.

This proof is required even for desktop-only cleanup because the retained bundle's ancestry must still be coherent at the moment cleanup is authorized.

## Cleanup plan

`phios.retained_cleanup_plan.v0.1` binds:

- app ID;
- retained version;
- active version;
- cleanup scope;
- retained bundle path;
- active bundle path;
- retention marker path;
- governed desktop-entry path;
- retained desktop-plan SHA;
- retained grant SHA;
- retained install-receipt SHA;
- retained installed-tree SHA;
- retained install path;
- active desktop-plan SHA;
- active grant SHA;
- active desktop-entry SHA;
- retention marker SHA;
- exact requested cleanup permissions;
- cleanup authority false;
- rollback authority false;
- canonical cleanup-plan SHA.

## Cleanup review

The review surface reconstructs and validates the canonical plan and exposes:

- cleanup-plan SHA;
- app/version transition context;
- scope;
- retained bundle/install paths;
- retained and active grant digests;
- retention-marker digest;
- exact requested permissions;
- cleanup authority false;
- rollback authority false.

Reviewing cleanup does not authorize deletion.

## Explicit approvals

Execution requires exact approval of:

1. cleanup-plan SHA;
2. retained grant SHA;
3. active grant SHA;
4. retention-marker SHA;
5. exact cleanup permission set.

Extra or missing permissions fail closed.

## Pre-deletion journal

Before deleting any retained bytes, v0.41 persists:

```text
phios.retained_cleanup_journal.v0.1
```

The journal records:

- UUID/time;
- cleanup-plan SHA;
- app ID;
- retained/active versions;
- cleanup scope;
- retained bundle path;
- retained install path;
- retention marker path;
- retained grant SHA;
- active grant SHA;
- retention marker SHA;
- exact approved cleanup permissions;
- status `prepared`;
- canonical journal SHA.

The journal is durable evidence that destructive authority existed before deletion began.

## Revalidation after journal persistence

After the journal is written, v0.41 reruns the complete cleanup plan from current filesystem state.

The newly computed plan must have the same canonical SHA as the reviewed plan.

If anything changed between review/journal persistence and deletion, cleanup stops before destructive operations.

## Destructive sequence

After final revalidation:

1. the retention marker is removed;
2. the retained desktop bundle is removed;
3. if scope is `desktop_bundle_and_install`, the retained installed tree is removed;
4. the final cleanup receipt is persisted.

The active desktop bundle, active installed tree, and active XDG desktop entry are not modified.

## Why the marker is removed first

Once destructive cleanup begins, the retained bundle is no longer a valid rollback target.

Removing the marker first prevents subsequent catalog discovery from continuing to classify that target as intentionally retained while its bytes are being removed.

## Partial failure semantics

Deletion is irreversible in the general case.

v0.41 therefore does not promise automatic restoration after the first destructive operation.

If failure occurs after journal persistence and before the final receipt:

- the `prepared` journal remains;
- some approved targets may already be gone;
- no `cleaned` receipt is emitted;
- the operator must reconcile actual filesystem state before another lifecycle transition.

This is deliberately different from v0.40's pre-receipt launcher-switch recovery, where the old bytes still existed and could be restored.

## Successful cleanup receipt

`phios.retained_cleanup_receipt.v0.1` records:

- UUID/time;
- cleanup-plan SHA;
- pre-deletion journal SHA;
- app ID;
- retained/active versions;
- cleanup scope;
- removed desktop-bundle path;
- optional removed install path;
- optional removed install-receipt SHA;
- optional removed installed-tree SHA;
- retired marker path/SHA;
- still-active bundle path;
- still-active grant SHA;
- cleanup authority true;
- rollback authority false;
- status `cleaned`;
- canonical receipt SHA.

Desktop-only receipts are forbidden from claiming that install bytes were removed.

Full-scope receipts must bind the removed install receipt and installed-tree digest.

## Catalog result after cleanup

Successful cleanup removes the retained desktop bundle and its retention marker.

The v0.39/v0.40 catalog therefore sees only the active governed desktop bundle.

For desktop-only cleanup, the old installed artifact tree can remain on disk but is no longer represented as a desktop app because its governed desktop bundle is gone.

## Authority boundaries

v0.41 preserves:

```text
retained evidence exists
≠ cleanup authorized

desktop cleanup authorized
≠ install cleanup authorized

cleanup authorized
≠ rollback authorized

prepared journal exists
≠ cleanup completed

cleanup receipt exists
→ reviewed cleanup completed
```

## CLI

Plan desktop-only cleanup:

```bash
phi-app plan-retained-cleanup \
  RETENTION_MARKER_PATH \
  --scope desktop_bundle_only \
  > retained-cleanup-plan.json
```

Plan desktop + installed-tree cleanup:

```bash
phi-app plan-retained-cleanup \
  RETENTION_MARKER_PATH \
  --scope desktop_bundle_and_install \
  > retained-cleanup-plan.json
```

Review:

```bash
phi-app review-retained-cleanup retained-cleanup-plan.json
```

Execute desktop-only cleanup:

```bash
phi-app execute-retained-cleanup \
  retained-cleanup-plan.json \
  --approve-cleanup-plan-sha EXACT_CLEANUP_PLAN_SHA256 \
  --approve-retained-grant-sha EXACT_RETAINED_GRANT_SHA256 \
  --approve-active-grant-sha EXACT_ACTIVE_GRANT_SHA256 \
  --approve-retention-marker-sha EXACT_RETENTION_MARKER_SHA256 \
  --allow-cleanup-permission desktop.cleanup.retained
```

Full cleanup additionally requires:

```text
--allow-cleanup-permission install.cleanup.retained
```

## CI verification model

v0.41 tests cover:

- retained/inactive proof;
- non-authoritative cleanup review;
- scope-dependent permission sets;
- exact approval requirements;
- desktop-only cleanup;
- desktop + install cleanup;
- active-bundle misidentification rejection;
- retention-marker tamper rejection;
- duplicate-marker ambiguity rejection;
- retained installed-tree drift rejection;
- active launcher drift rejection;
- journal persistence before destructive operations;
- partial destructive failure leaving the journal;
- plan digest-tamper rejection;
- final receipt digest-tamper rejection;
- catalog visibility after successful cleanup.

## Explicit non-capabilities

v0.41 does not:

- discover which remote versions are obsolete;
- decide retention policy automatically;
- select cleanup targets by age;
- delete the active version;
- infer install cleanup from desktop cleanup;
- grant rollback authority;
- restore deleted bytes after destructive failure;
- reconcile a partial cleanup journal automatically;
- garbage-collect unrelated install trees.

## Planned next rung

v0.42 should add a **Cleanup Journal Reconciliation / Recovery Contract**.

That rung can inspect a `prepared` journal without a final receipt, compare expected targets with actual filesystem state, classify the transition as untouched / partial / effectively complete, and require an explicit reconciliation action before the lifecycle proceeds.
