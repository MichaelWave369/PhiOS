# PhiOS App Platform v0.41

PhiOS App Platform v0.41 adds the **Retained Version Cleanup / Lifecycle Contract**.

v0.40 can preserve the previous governed desktop version for rollback. v0.41 defines when that retained version may be deliberately retired and what evidence must exist before destructive cleanup begins.

## Core rule

```text
retained
≠ disposable

inactive
≠ cleanup approved

cleanup approved
≠ install tree may also be deleted
```

Cleanup and rollback remain separate authorities.

## Cleanup scopes

v0.41 supports two explicit scopes:

```text
desktop_bundle_only
desktop_bundle_and_install
```

`desktop_bundle_only` removes the retained v0.38 desktop bundle and its retention marker while leaving the v0.33 installed artifact tree intact.

`desktop_bundle_and_install` also removes the retained installed artifact tree.

## Permissions

Desktop-only cleanup requires:

```text
desktop.cleanup.retained
```

Cleanup that also removes the installed artifact tree requires both:

```text
desktop.cleanup.retained
install.cleanup.retained
```

The cleanup plan itself records:

```text
cleanup_authority  = false
rollback_authority = false
```

## Eligibility proof

Planning independently verifies:

- retention marker path and canonical digest;
- exactly one valid marker for the retained bundle;
- retained and active bundles belong to the same app;
- retained and active plan/grant identities match the marker;
- retained bundle is not the active bundle;
- current active desktop entry still matches the active grant;
- retained grant points to the same governed desktop entry;
- current desktop-entry digest does **not** match the retained grant;
- retained installed ancestry still matches its install receipt.

This proves the target is a specific retained inactive version, not merely an old-looking directory.

## Pre-deletion journal

Destructive cleanup starts only after PhiOS persists:

```text
phios.retained_cleanup_journal.v0.1
```

The journal binds the exact reviewed cleanup plan, target paths, retained/active grants, retention marker, scope, and approved cleanup permissions.

Only after that durable journal exists does PhiOS re-run the complete cleanup proof and begin deletion.

## Why the journal matters

Deletion cannot honestly promise automatic rollback after bytes are gone.

If a process or filesystem failure occurs after the journal is persisted but before the final cleanup receipt, the journal remains evidence that:

- exact destructive authority was granted;
- cleanup may be partial;
- the operator should reconcile filesystem state before another lifecycle transition.

v0.41 does not disguise a partial destructive transition as success.

## Successful cleanup

Desktop-only cleanup removes:

```text
retained desktop bundle
retention marker
```

Full cleanup additionally removes:

```text
retained installed artifact tree
```

The active bundle, active desktop entry, and active installed version are not modified.

## Final receipt

A completed cleanup emits:

```text
phios.retained_cleanup_receipt.v0.1
```

It records:

- cleanup plan SHA;
- pre-deletion journal SHA;
- retained and active versions;
- cleanup scope;
- removed bundle path;
- retired marker path/digest;
- active bundle/grant identity;
- optional removed install path/receipt/tree digest;
- `cleanup_authority=true`;
- `rollback_authority=false`;
- status `cleaned`.

## CLI

Plan desktop-only cleanup:

```bash
phi-app plan-retained-cleanup \
  RETENTION_MARKER_PATH \
  --scope desktop_bundle_only \
  > retained-cleanup-plan.json
```

Or include the installed artifact tree:

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

Execute only after exact approvals:

```bash
phi-app execute-retained-cleanup \
  retained-cleanup-plan.json \
  --approve-cleanup-plan-sha EXACT_CLEANUP_PLAN_SHA256 \
  --approve-retained-grant-sha EXACT_RETAINED_GRANT_SHA256 \
  --approve-active-grant-sha EXACT_ACTIVE_GRANT_SHA256 \
  --approve-retention-marker-sha EXACT_RETENTION_MARKER_SHA256 \
  --allow-cleanup-permission desktop.cleanup.retained
```

For `desktop_bundle_and_install`, also approve:

```text
install.cleanup.retained
```

See `docs/PHIOS_APP_PLATFORM_V0.41_RETAINED_CLEANUP.md`.
