# PhiOS App Platform v0.39 — Desktop App Catalog Contract

## Status

Alpha contract.

Schemas:

- `phios.desktop_catalog_snapshot.v0.1`
- `phios.desktop_catalog_review.v0.1`
- `phios.desktop_catalog_receipt.v0.1`

## Purpose

v0.39 provides deterministic, bounded discovery of v0.38 governed desktop bundles and integrates verified-ready apps into PhiOS's existing launcher surface.

The central rule is:

> Catalog presence is evidence, not authority.

A catalog item may report that a valid persistent v0.38 grant exists. The catalog itself does not create, expand, launch, revoke, or display anything.

## Authority model

Catalog snapshot, review, item, and receipt all preserve:

```text
catalog_launch_authority = false
catalog_revoke_authority = false
```

A ready catalog item means:

> Current observed bundle state still satisfies the v0.38 persistent-launch contract and its installed ancestry.

It does not mean:

- the catalog may launch it automatically;
- current Wayland display authority has been granted;
- browser execution has begun;
- the app is healthy after launch;
- the grant may be revoked without separate user intent.

## Discovery root

v0.39 scans the configured v0.38 desktop bundle root using exactly two structural levels:

```text
DESKTOP_ROOT/
  APP_DIRECTORY/
    BUNDLE_DIRECTORY/
```

It does not recursively walk arbitrary descendants.

Bounds:

```text
max app directories = 512
max bundle candidates = 1024
max metadata JSON bytes = 2 MiB per file
```

If the desktop root does not exist, v0.39 returns a valid empty deterministic snapshot and does not create the directory.

Existing roots must not be symlinks and must be directories.

## Root issues

Unexpected or unsafe entries outside otherwise inspectable bundles are recorded separately from item status.

Root issue codes:

```text
unsafe_app_directory
unexpected_root_entry
unexpected_app_entry
```

A symlinked app directory is reported and never followed.

Unexpected files do not silently disappear from the catalog evidence.

## Required v0.38 bundle layout

A candidate bundle is expected to contain exactly:

```text
desktop-plan.json
browser-plan.json
static-plan.json
install-receipt.json
grant.json
```

All five must be regular non-symlink files.

The bundle directory name must be the first 16 lowercase hexadecimal characters of the canonical desktop-plan SHA-256.

The parent app directory must equal the verified plan app ID.

## Item verification

v0.39 parses and verifies:

1. `DesktopAppPlan`;
2. `BrowserSessionPlan`;
3. `StaticWebAdapterPlan`;
4. `AppInstallReceipt`;
5. `DesktopLaunchGrant`.

It then verifies cross-bindings:

- grant app ID/version match desktop plan;
- grant bundle path equals actual bundle path;
- grant desktop-plan SHA equals parsed desktop plan;
- grant browser-plan SHA equals parsed browser plan;
- grant static-plan SHA equals parsed static plan;
- grant install-receipt SHA equals parsed install receipt;
- desktop plan binds the parsed browser/static/install payloads;
- browser plan binds the static plan;
- desktop plan installed-tree SHA matches the install receipt.

## Desktop-entry verification

The grant's XDG desktop entry must:

- exist;
- not be a symlink;
- be a regular file;
- resolve under the configured applications root;
- have the deterministic filename required by the desktop plan;
- match the SHA-256 recorded in the persistent grant.

v0.39 does not execute the entry while checking it.

## Installed ancestry revalidation

Catalog readiness is not based only on self-consistent persisted metadata.

v0.39 recomputes the v0.38 desktop plan using the current installed application state.

This reuses the existing chain that verifies:

- installed tree identity;
- installed manifest;
- current v0.35 static-web plan;
- current v0.36 browser plan.

If current state no longer reproduces the exact persisted desktop-plan SHA, the item becomes blocked with:

```text
installed_app_drift
```

## Item states

Catalog item status is exactly:

```text
ready
blocked
```

A ready item has no issues and requires:

- verified app identity;
- a valid persistent launch grant;
- enabled grant status;
- valid launcher entry;
- unchanged installed ancestry.

A blocked item contains one or more deterministic issue codes.

Current issue codes:

```text
unsafe_bundle
bundle_name_invalid
bundle_layout_invalid
desktop_plan_invalid
browser_plan_invalid
static_plan_invalid
install_receipt_invalid
grant_invalid
binding_mismatch
desktop_entry_missing
desktop_entry_unsafe
desktop_entry_outside_root
desktop_entry_digest_mismatch
installed_app_drift
duplicate_app_identity
```

Malformed individual bundles do not abort the whole catalog.

## Identity and metadata

Verified catalog metadata is derived only after the v0.38 desktop plan parses successfully.

A ready item exposes:

- app ID;
- app version;
- desktop name;
- desktop icon metadata;
- desktop-entry path;
- desktop-plan SHA-256;
- desktop-launch-grant SHA-256;
- grant status;
- exact bundle path.

The icon state in v0.39 is:

```text
metadata_only
```

because v0.38 does not install an icon-theme asset.

## Determinism

Catalog items are sorted by their root-relative catalog key.

Root issues are sorted by relative path then issue code.

Per-item issues are unique and sorted by code.

Each catalog item has its own canonical SHA-256.

The snapshot body includes all item digests and receives:

```text
desktop_catalog_sha256
```

Two scans of unchanged filesystem/install state produce the same snapshot digest.

## Snapshot contents

`phios.desktop_catalog_snapshot.v0.1` binds:

- absolute desktop root;
- absolute applications root;
- absolute installed-app root;
- bounded root issues;
- all catalog items;
- total item count;
- ready count;
- blocked count;
- launch authority false;
- revoke authority false;
- canonical snapshot SHA-256.

## Review surface

`review-desktop-catalog` reconstructs and validates the canonical snapshot before exposing:

- catalog SHA-256;
- item count;
- ready count;
- blocked count;
- root-issue count;
- sorted ready app IDs;
- launch authority false;
- revoke authority false.

Reviewing the catalog does not approve any app launch.

## Catalog receipt

Each catalog observation produces `phios.desktop_catalog_receipt.v0.1` containing:

- UUID/time;
- catalog SHA-256;
- three configured roots;
- item/ready/blocked counts;
- root issue count;
- launch authority false;
- revoke authority false;
- canonical receipt SHA-256.

Unlike the deterministic snapshot, two observations of unchanged state have different receipt identities because receipt UUID/time are observational metadata.

The receipt has a strict reconstruction parser and digest-tamper rejection.

## No display resolution during discovery

Catalog discovery deliberately does not read or require:

```text
XDG_RUNTIME_DIR
WAYLAND_DISPLAY
```

It does not resolve a Wayland socket.

Per-launch exact display authority remains a v0.38/v0.37 operation after explicit user selection.

## PhiLauncher integration

v0.39 integrates the existing `phios.desktop.launcher.PhiLauncher` with the catalog.

Built-in Phi actions remain available.

Only catalog items with:

```text
status = ready
```

are added as governed app actions.

Visible label format:

```text
DESKTOP_NAME · APP_ID VERSION
```

The action is bound to the exact argv vector:

```text
phi-app
launch-desktop-bundle
EXACT_BUNDLE_PATH
```

The launcher does not interpret catalog presence as authority. User selection is the explicit launch intent, and execution still enters the existing v0.38 grant validation path.

Blocked catalog items are not emitted as runnable menu choices.

If catalog discovery fails, PhiLauncher degrades to built-in Phi commands.

## Typed launcher actions

Prior PhiLauncher behavior executed selected menu text using:

```text
selection.split()
```

v0.39 replaces that with typed `LauncherAction` values:

```text
visible label
exact argv tuple
```

This means:

- labels are presentation only;
- executable arguments are never reconstructed from display text;
- paths containing spaces remain one argv element;
- no shell is introduced.

## CLI

Create a current catalog observation:

```bash
phi-app catalog-desktop-apps > desktop-catalog.json
```

The output contains:

```text
snapshot
receipt
```

Review the result wrapper directly:

```bash
phi-app review-desktop-catalog desktop-catalog.json
```

The review command also accepts a raw snapshot payload.

## CI verification model

v0.39 tests cover:

- deterministic empty catalog when roots are absent;
- healthy governed app readiness;
- stable snapshot digest across repeated scans;
- distinct observational receipts;
- non-authoritative review surface;
- launcher-entry digest tamper blocking;
- installed-app drift blocking;
- malformed grant isolation;
- exact five-file bundle layout;
- missing applications-root blocking;
- unexpected root/app entry evidence;
- symlinked app-directory refusal;
- catalog item digest tamper rejection;
- catalog receipt digest tamper rejection;
- plan-prefix/bundle-path binding;
- no Wayland resolution during discovery;
- PhiLauncher showing only ready apps;
- launcher degradation when catalog discovery fails;
- exact argv execution for bundle paths containing spaces.

## Explicit non-capabilities

v0.39 does not:

- launch an app during catalog discovery;
- revoke a grant during catalog discovery;
- resolve Wayland during catalog discovery;
- create a desktop grant;
- repair malformed bundles;
- repair stale launchers;
- auto-delete blocked bundles;
- silently ignore unexpected catalog-root entries;
- install icon-theme assets;
- infer runtime health from catalog readiness;
- bypass v0.38 launch-time validation.

## Planned next rung

v0.40 should add a **Governed App Update / Rollback Contract**.

That rung can preserve the now-complete install → desktop grant → catalog path while adding:

- new-version admission beside the active version;
- exact update-plan review;
- atomic desktop-entry/grant switch;
- previous-version retention;
- rollback approval;
- update/rollback receipts;
- catalog visibility of active vs retained versions.

That would give PhiOS a safe lifecycle after installation, not merely a safe first install.
