# PhiOS App Platform v0.39

PhiOS App Platform v0.39 adds the **Desktop App Catalog Contract**.

v0.38 can install one persistent, revocable XDG desktop launcher. v0.39 turns those individual governed bundles into a deterministic application library and integrates only verified-ready apps into the existing PhiLauncher.

## Authority boundary

```text
catalog discovers app
≠ catalog grants launch authority

valid v0.38 grant exists
≠ catalog launches app

user selects app
→ existing v0.38 launch grant is consumed
```

Catalog snapshot, review, and receipt all record:

```text
catalog_launch_authority = false
catalog_revoke_authority = false
```

## Discovery

v0.39 scans the v0.38 desktop bundle layout:

```text
DESKTOP_ROOT/
  APP_ID/
    PLAN_SHA_PREFIX/
      desktop-plan.json
      browser-plan.json
      static-plan.json
      install-receipt.json
      grant.json
```

Discovery is bounded:

- maximum 512 app directories;
- maximum 1024 bundle candidates;
- maximum 2 MiB per metadata JSON file;
- no recursive arbitrary filesystem walk;
- symlinked app directories are not followed.

A missing desktop root produces a valid deterministic empty catalog rather than creating directories.

## Ready vs blocked

Every discovered bundle becomes a catalog item.

A **ready** item requires:

- exact five-file bundle layout;
- valid v0.38 desktop plan;
- valid v0.36 browser plan;
- valid v0.35 static plan;
- valid v0.33 install receipt;
- valid persistent v0.38 launch grant;
- exact cross-plan digest bindings;
- bundle path and plan digest-prefix binding;
- current XDG desktop entry present and under the configured applications root;
- desktop-entry SHA-256 still matching its grant;
- current installed app/runtime ancestry recomputing to the same desktop plan.

A malformed or stale bundle becomes **blocked** instead of crashing the whole catalog.

Blocked reason codes include:

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

## Deterministic snapshot

Catalog items are sorted by relative catalog key and canonicalized into:

```text
phios.desktop_catalog_snapshot.v0.1
```

The snapshot records:

- desktop, applications, and install roots;
- bounded root issues;
- all ready and blocked items;
- item/ready/blocked counts;
- explicit zero launch/revoke authority;
- canonical catalog SHA-256.

Repeated scans of unchanged state produce the same catalog SHA-256.

The observation receipt has its own UUID/time, so separate observations have different receipt identities while still binding the same unchanged catalog digest.

## PhiLauncher integration

The existing PhiLauncher now reads the governed catalog and appends only **ready** apps.

A ready app appears as:

```text
APP_NAME · APP_ID VERSION
```

and maps directly to one exact argv vector:

```text
phi-app
launch-desktop-bundle
EXACT_BUNDLE_PATH
```

Blocked apps never become runnable menu entries.

If catalog discovery itself fails, PhiLauncher degrades to its existing built-in Phi commands.

v0.39 also removes the old `selection.split()` execution path. Launcher choices now map to typed argv tuples, so a bundle path containing spaces remains one argument.

## CLI

Snapshot the current governed desktop library:

```bash
phi-app catalog-desktop-apps > desktop-catalog.json
```

Review either a raw snapshot or the result wrapper:

```bash
phi-app review-desktop-catalog desktop-catalog.json
```

Catalog inspection does not resolve Wayland, open a browser, launch an app, or revoke a grant.

See `docs/PHIOS_APP_PLATFORM_V0.39_DESKTOP_CATALOG.md`.
