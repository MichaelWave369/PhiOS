# PhiOS App Platform v0.40 — Governed App Update / Rollback Contract

## Status

Alpha contract.

Schemas:

- `phios.desktop_update_plan.v0.1`
- `phios.desktop_update_review.v0.1`
- `phios.desktop_update_receipt.v0.1`
- `phios.desktop_rollback_plan.v0.1`
- `phios.desktop_rollback_review.v0.1`
- `phios.desktop_rollback_receipt.v0.1`
- `phios.desktop_retention_marker.v0.1`

## Purpose

v0.40 adds governed desktop-version transitions above the merged v0.38 persistent-launch and v0.39 catalog contracts.

The central rule is:

> Update authority and rollback authority are separate capabilities.

An update may install and activate one reviewed candidate while retaining the previous governed bundle. That does not grant permission to roll back later.

## Active-version authority

The XDG desktop-entry bytes remain the authoritative active-version switch.

PhiOS does not add a second mutable `active-version.json` pointer that could disagree with the launcher.

The active version is the version whose valid v0.38 grant matches the current governed desktop-entry bytes.

## Preconditions

An update starts from:

- one active v0.38 governed desktop bundle;
- its current matching XDG desktop entry;
- one already installed candidate version;
- one candidate v0.35 static-web plan;
- one candidate v0.36 browser-session plan;
- one candidate v0.38 desktop plan derivable from current installed state.

The candidate is not installed by v0.40. It must already have passed the earlier acquisition/build/install pipeline.

## Independent revalidation

Update planning does not trust a prior v0.39 catalog snapshot.

It independently reconstructs the active bundle and verifies:

- exact five-file v0.38 bundle layout;
- desktop/browser/static/install/grant parsing;
- bundle parent app ID;
- bundle digest-prefix name;
- grant-to-plan bindings;
- browser-to-static binding;
- current installed ancestry;
- current XDG desktop-entry path;
- current desktop-entry SHA-256 matching the active grant.

The candidate plan is then recomputed from the candidate installed state.

## Candidate identity

The candidate must:

- have the same app ID as the active version;
- have a different version string;
- request the same persistent v0.38 desktop permission set as the active grant;
- produce a different governed desktop-bundle destination.

v0.40 does not interpret version ordering.

## Version strings are opaque

v0.40 accepts any candidate version string already valid under the app-manifest contract as long as it differs from the active version.

It does not enforce SemVer or claim that one string is newer than another.

That means a transition from `1.0.0` to `0.9.0` can be planned if the operator explicitly chooses it.

Ordering policy belongs in a later release-discovery policy, not in the authority primitive.

## Update plan

`phios.desktop_update_plan.v0.1` binds:

- app ID;
- from-version;
- to-version;
- active bundle path;
- candidate bundle path;
- desktop-entry path;
- active desktop-plan SHA-256;
- active grant SHA-256;
- active desktop-entry SHA-256;
- candidate desktop-plan SHA-256;
- candidate browser-plan SHA-256;
- candidate static-plan SHA-256;
- candidate install-receipt SHA-256;
- candidate installed-tree SHA-256;
- candidate desktop-entry SHA-256;
- candidate persistent desktop permissions;
- requested update permissions;
- previous-version retention requirement;
- update authority false;
- rollback authority false;
- canonical update-plan SHA-256.

## Update permission

The v0.40 update permission set is exactly:

```text
desktop.update.switch
```

Execution requires exact approval of:

1. update-plan SHA-256;
2. active grant SHA-256;
3. candidate desktop-plan SHA-256;
4. exact update permission set.

Extra or missing update permissions fail closed.

## Update execution

Immediately before mutation, execution recomputes the complete update plan and requires the same canonical digest.

It then:

1. revalidates the active bundle and current launcher;
2. revalidates the candidate installed ancestry;
3. renders the exact canonical candidate XDG desktop entry;
4. creates a new candidate persistent v0.38 launch grant;
5. stages the five-file candidate desktop bundle;
6. atomically promotes the candidate bundle beside the previous bundle;
7. atomically replaces the governed XDG desktop entry;
8. verifies the new desktop-entry digest;
9. writes a retention marker for the previous version;
10. writes the update receipt.

The previous bundle is not edited or deleted.

## Candidate grant

The candidate launch grant is a normal v0.38 `DesktopLaunchGrant`.

It binds:

- candidate desktop plan;
- candidate browser/static/install ancestry;
- candidate bundle path;
- the same governed desktop-entry path;
- the candidate desktop-entry digest;
- the same fixed v0.38 persistent launch permission set.

Thus v0.40 does not invent a parallel launch model.

## Atomic desktop-entry switch

The active launcher is switched using an atomic same-path file replacement.

The candidate bundle is prepared before the launcher is switched.

The active launcher bytes are captured and verified before replacement so failure recovery can restore exactly the previous governed entry.

## Retention marker

`phios.desktop_retention_marker.v0.1` is deterministic transition evidence.

It binds:

- app ID;
- retained bundle path/version/desktop-plan SHA/grant SHA;
- active bundle path/version/desktop-plan SHA/grant SHA;
- transition kind (`update` or `rollback`);
- transition-plan SHA-256;
- canonical marker SHA-256.

Marker filename:

```text
.retained-RETAINED_PLAN_SHA_PREFIX.json
```

The marker lives in the app's desktop-bundle directory beside version bundles, not inside either five-file bundle.

## Retention marker is not authority

A retention marker does not activate or deactivate a version by itself.

The desktop-entry bytes remain authoritative for active launch selection.

The marker explains why another otherwise valid bundle's launch-entry digest no longer matches the current desktop entry.

## Update receipt

`phios.desktop_update_receipt.v0.1` records:

- UUID/time;
- update-plan SHA-256;
- app ID and version transition;
- previous bundle/plan/grant/entry digest;
- active candidate bundle/plan/grant/entry digest;
- retention marker path/digest;
- `update_switch_authority=true`;
- `rollback_authority=false`;
- status `updated`;
- canonical receipt SHA-256.

The receipt has strict reconstruction and digest-tamper rejection.

## Update failure recovery

If any post-switch step fails before the update receipt is persisted, PhiOS attempts to restore the pre-update state.

Specifically:

- retention marker is removed if created;
- previous desktop-entry bytes are restored if switching occurred;
- candidate desktop bundle is removed;
- the error is propagated.

A switch without a persisted update receipt is not treated as a successful update.

## Rollback planning

Rollback begins from one exact v0.40 update receipt.

Planning revalidates:

- current active candidate bundle;
- retained previous bundle;
- current installed ancestry for both versions;
- current active desktop-entry digest;
- retention marker digest;
- marker-to-active/retained grant bindings;
- retained target launcher bytes;
- retained target grant points to the same governed desktop-entry path;
- retained target uses the same deterministic desktop-entry filename.

Rollback therefore cannot redirect the operation to another launcher path.

## Rollback plan

`phios.desktop_rollback_plan.v0.1` binds:

- originating update-receipt SHA-256;
- app ID;
- current from-version;
- retained target to-version;
- active and target bundle paths;
- governed desktop-entry path;
- active grant SHA-256;
- target retained grant SHA-256;
- active entry SHA-256;
- rollback target entry SHA-256;
- current retention marker path/digest;
- planned post-rollback retention-marker path;
- requested rollback permissions;
- rollback authority false;
- canonical rollback-plan SHA-256.

## Rollback permission

The rollback permission set is exactly:

```text
desktop.rollback.switch
```

Rollback execution requires exact approval of:

1. rollback-plan SHA-256;
2. current active grant SHA-256;
3. retained target grant SHA-256;
4. exact rollback permission set.

An update receipt does not satisfy these approvals.

## Rollback execution

Immediately before switching, rollback recomputes the entire rollback plan and requires the same digest.

It then:

1. revalidates current active and retained bundles;
2. revalidates current active launcher bytes;
3. revalidates the current retention marker;
4. renders the exact retained target desktop entry;
5. atomically switches the desktop entry back;
6. removes the old retention marker;
7. creates a new marker identifying the formerly active candidate as retained;
8. writes the rollback receipt.

Neither version bundle is deleted.

## Rollback receipt

`phios.desktop_rollback_receipt.v0.1` records:

- UUID/time;
- rollback-plan SHA-256;
- originating update-receipt SHA-256;
- app/version transition;
- newly active bundle/grant/entry digest;
- newly retained bundle/grant;
- new retention marker path/digest;
- `rollback_switch_authority=true`;
- `update_authority=false`;
- status `rolled_back`;
- canonical receipt SHA-256.

## Rollback failure recovery

If rollback switches the launcher but cannot persist the final rollback receipt, PhiOS attempts to restore the updated state:

- new post-rollback marker is removed;
- original retention marker is restored;
- newer desktop-entry bytes are restored;
- the error is propagated.

## Catalog extension

v0.40 extends v0.39 catalog interpretation without making the catalog authoritative.

Two new evidence codes are recognized:

```text
retained_inactive
invalid_retention_marker
```

A retained bundle is labeled `retained_inactive` only when:

- its marker parses and validates;
- the marker binds that retained plan and grant;
- the marker's active bundle is a sibling governed bundle;
- the marker's active grant validates;
- the current XDG desktop-entry digest matches the marker's active grant.

If those conditions fail, the ordinary digest/binding failure remains visible instead of being disguised as retention.

## Catalog lifecycle behavior

After update:

```text
candidate version  → ready
previous version   → blocked / retained_inactive
```

After rollback:

```text
previous version   → ready
candidate version  → blocked / retained_inactive
```

PhiLauncher therefore continues to expose only the currently active ready version.

## Receipt and marker tampering

Update receipts, rollback receipts, update plans, rollback plans, and retention markers all use canonical SHA-256 reconstruction checks.

Tampered payloads are rejected before transition use.

These local hashes are integrity structures, not cryptographic signatures or remote trust attestations.

## CLI

Plan update:

```bash
phi-app plan-desktop-update \
  ACTIVE_BUNDLE_PATH \
  candidate-browser-plan.json \
  candidate-static-plan.json \
  candidate-install-receipt.json \
  > desktop-update-plan.json
```

Review update:

```bash
phi-app review-desktop-update desktop-update-plan.json
```

Execute update:

```bash
phi-app execute-desktop-update \
  desktop-update-plan.json \
  candidate-browser-plan.json \
  candidate-static-plan.json \
  candidate-install-receipt.json \
  --approve-update-plan-sha EXACT_UPDATE_PLAN_SHA256 \
  --approve-active-grant-sha EXACT_ACTIVE_GRANT_SHA256 \
  --approve-candidate-desktop-plan-sha EXACT_CANDIDATE_DESKTOP_PLAN_SHA256 \
  --allow-update-permission desktop.update.switch
```

Plan rollback:

```bash
phi-app plan-desktop-rollback desktop-update-receipt.json > desktop-rollback-plan.json
```

Review rollback:

```bash
phi-app review-desktop-rollback desktop-rollback-plan.json
```

Execute rollback:

```bash
phi-app execute-desktop-rollback \
  desktop-rollback-plan.json \
  desktop-update-receipt.json \
  --approve-rollback-plan-sha EXACT_ROLLBACK_PLAN_SHA256 \
  --approve-active-grant-sha EXACT_CURRENT_GRANT_SHA256 \
  --approve-target-grant-sha EXACT_RETAINED_GRANT_SHA256 \
  --allow-rollback-permission desktop.rollback.switch
```

## CI verification model

v0.40 tests cover:

- deterministic update plan binding;
- explicit non-authoritative review surface;
- no implicit SemVer ranking;
- exact update approvals;
- side-by-side candidate bundle creation;
- atomic desktop-entry activation;
- previous-bundle retention;
- retention-marker reconstruction;
- update receipt reconstruction;
- catalog active/retained visibility;
- candidate installed-tree drift blocking;
- active launcher tamper blocking;
- update receipt persistence failure restoring the old state;
- independent rollback planning;
- exact rollback approvals;
- rollback launcher restoration;
- retained-state reversal after rollback;
- retention-marker tamper blocking;
- rollback receipt persistence failure restoring the updated state;
- update/rollback receipt digest-tamper rejection.

## Explicit non-capabilities

v0.40 does not:

- discover remote releases;
- rank version strings;
- download or build a candidate;
- install candidate artifacts;
- auto-approve update;
- auto-approve rollback;
- delete the previous bundle after update;
- garbage-collect retained versions;
- support arbitrary multi-version selection;
- treat a retention marker as launch authority;
- bypass v0.38 launch-time verification;
- bypass v0.39 catalog evidence rules.

## Planned next rung

v0.41 should add a **Retained Version Cleanup / Lifecycle Contract**.

That rung can govern:

- listing retained versions eligible for cleanup;
- proving a retained version is not active;
- proving no rollback plan currently depends on it;
- explicit cleanup approval;
- installed-artifact cleanup versus desktop-bundle cleanup;
- cleanup receipts;
- catalog transition from retained to removed.

That closes the lifecycle loop without turning rollback retention into permanent disk archaeology.
