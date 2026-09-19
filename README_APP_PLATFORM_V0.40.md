# PhiOS App Platform v0.40

PhiOS App Platform v0.40 adds the **Governed App Update / Rollback Contract**.

v0.39 can discover and launch verified governed desktop apps. v0.40 adds a version-transition lifecycle without deleting the active version first or silently expanding authority.

## Core rule

```text
installed candidate
≠ approved update

approved update
≠ rollback authority

retained previous version
≠ active version
```

The XDG desktop entry remains the authoritative active-version switch.

## Update pipeline

```text
ACTIVE v1 BUNDLE + GRANT
        +
INSTALLED v2 CANDIDATE
        ↓
reverify both ancestries
        ↓
deterministic update plan
        ↓
explicit approval:
  update plan SHA
  active grant SHA
  candidate desktop-plan SHA
  desktop.update.switch
        ↓
prepare v2 desktop bundle beside v1
        ↓
ATOMIC desktop-entry replacement
        ↓
mark v1 retained/inactive
        ↓
persist update receipt
```

The old bundle is not mutated or deleted.

## Rollback pipeline

```text
v0.40 update receipt
        ↓
reverify current active v2
        ↓
reverify retained v1
        ↓
verify retention marker
        ↓
deterministic rollback plan
        ↓
explicit approval:
  rollback plan SHA
  current active grant SHA
  target retained grant SHA
  desktop.rollback.switch
        ↓
ATOMIC desktop-entry replacement
        ↓
v1 active
v2 retained/inactive
        ↓
persist rollback receipt
```

Update authority and rollback authority are intentionally separate.

## Permissions

Update requires exactly:

```text
desktop.update.switch
```

Rollback requires exactly:

```text
desktop.rollback.switch
```

A completed update receipt records:

```text
update_switch_authority = true
rollback_authority      = false
```

A completed rollback receipt records:

```text
rollback_switch_authority = true
update_authority          = false
```

## Version semantics

v0.40 treats version strings as opaque identity labels.

It requires the candidate version to differ from the active version, but it does **not** claim that `2.0.0` is newer than `1.0.0`, enforce SemVer, or rank arbitrary project version formats.

This keeps version-order policy separate from transition authority.

## Retention marker

After a successful update, PhiOS writes a deterministic retention marker beside the desktop bundles:

```text
.retained-PLAN_SHA_PREFIX.json
```

It binds:

- retained app/version/bundle/plan/grant;
- active app/version/bundle/plan/grant;
- transition kind;
- transition plan SHA;
- canonical marker SHA-256.

After rollback, the old marker is removed and a new marker records the formerly active version as retained.

## Catalog integration

v0.40 extends v0.39 catalog evidence.

A valid inactive retained version is reported as blocked with:

```text
retained_inactive
```

rather than being mislabeled as a generic launcher-digest failure.

An invalid retention marker is reported as a root issue:

```text
invalid_retention_marker
```

Only the version whose grant matches the current XDG desktop-entry bytes remains `ready` and therefore runnable through PhiLauncher.

## Failure recovery

Update and rollback are not declared complete merely because the desktop-entry switch occurred.

If update receipt persistence fails after switching:

- the old desktop entry is restored;
- the retention marker is removed;
- the candidate desktop bundle is removed.

If rollback receipt persistence fails after switching:

- the newer desktop entry is restored;
- the original retention marker is restored;
- the attempted post-rollback marker is removed.

This keeps receipted state and active state aligned as far as the local filesystem operations permit.

## CLI

Plan an update:

```bash
phi-app plan-desktop-update \
  ACTIVE_BUNDLE_PATH \
  candidate-browser-plan.json \
  candidate-static-plan.json \
  candidate-install-receipt.json \
  > desktop-update-plan.json
```

Review:

```bash
phi-app review-desktop-update desktop-update-plan.json
```

Execute:

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

Plan rollback from the resulting update receipt:

```bash
phi-app plan-desktop-rollback desktop-update-receipt.json > desktop-rollback-plan.json
```

Review:

```bash
phi-app review-desktop-rollback desktop-rollback-plan.json
```

Execute:

```bash
phi-app execute-desktop-rollback \
  desktop-rollback-plan.json \
  desktop-update-receipt.json \
  --approve-rollback-plan-sha EXACT_ROLLBACK_PLAN_SHA256 \
  --approve-active-grant-sha EXACT_CURRENT_GRANT_SHA256 \
  --approve-target-grant-sha EXACT_RETAINED_GRANT_SHA256 \
  --allow-rollback-permission desktop.rollback.switch
```

See `docs/PHIOS_APP_PLATFORM_V0.40_UPDATE_ROLLBACK.md`.
