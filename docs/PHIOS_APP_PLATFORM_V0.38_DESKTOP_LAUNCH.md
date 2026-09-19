# PhiOS App Platform v0.38 — Desktop App Launch Contract

## Status

Alpha contract.

Schemas:

- `phios.desktop_app_plan.v0.1`
- `phios.desktop_app_plan_review.v0.1`
- `phios.desktop_launch_grant.v0.1`
- `phios.desktop_launch_receipt.v0.1`
- `phios.desktop_revoke_receipt.v0.1`

## Purpose

v0.38 converts the governed static-web/browser chain into a persistent desktop application launcher.

The central rule is:

> A desktop entry is not authority.

A persistent launch grant is created only after explicit review and approval of the exact desktop plan and exact permission set.

The desktop entry merely points at that grant-bound bundle.

## Why v0.38 does not persist a v0.37 plan

v0.37 intentionally binds one exact Wayland socket identity: path, device, inode, ctime, owner UID, and owner GID.

That is correct for one visible session and unsuitable as the permanent identity for a desktop launcher because a compositor restart may replace the socket.

v0.38 therefore persists the stable application/runtime ancestry through v0.36 and authorizes a narrow display-selector policy.

At each click, PhiOS resolves the current user's display socket and derives a new exact v0.37 plan.

This preserves v0.37's session precision without making desktop launchers stale after normal desktop lifecycle events.

## Desktop plan inputs

Planning requires:

- one valid v0.36 browser-session plan;
- its exact v0.35 static-web plan;
- the exact v0.33 install receipt;
- the configured installed-app root.

Planning verifies:

- browser plan binds the supplied static plan;
- static/browser plans bind the supplied install receipt;
- full installed tree still matches the install receipt;
- installed manifest still matches;
- current recomputed v0.35 static plan is identical;
- current recomputed v0.36 browser plan is identical.

## Desktop metadata

v0.38 derives desktop identity from the verified installed manifest:

- app ID;
- version;
- application name;
- application description.

The desktop filename is deterministic:

```text
phios-APP_ID.desktop
```

The generic icon metadata is:

```text
phios-app
```

v0.38 does not yet install an icon-theme asset or infer app-specific icons.

## Desktop plan

The plan binds:

- app ID/version;
- desktop name/comment/icon metadata;
- manifest SHA-256;
- install-receipt SHA-256;
- installed-tree SHA-256;
- v0.35 static-plan SHA-256;
- v0.36 browser-plan SHA-256;
- exact loopback URL;
- browser tool;
- session duration;
- readiness timeout;
- display-selector policy;
- desktop entry filename;
- exact requested persistent desktop permissions.

Plan authority remains:

```text
persistent_launch_grant_authority = false
display_authority = false
```

## Permission model

The exact v0.38 permission set is:

```text
browser.display.wayland
browser.network.inherit
browser.page.execute
desktop.launch.persist
```

### desktop.launch.persist

This is a new durable authority.

Approval means the exact reviewed app/runtime ancestry may be launched later from the installed desktop entry while dynamically binding the current user's validated Wayland socket for each launch.

It does not mean:

- arbitrary applications may launch;
- arbitrary browser plans may launch;
- arbitrary displays may be mounted;
- the installed app may change;
- permissions may expand;
- browser network authority becomes filtered.

## Persistent grant

The installed grant binds:

- UUID/time;
- app identity;
- desktop-plan SHA-256;
- v0.36 browser-plan SHA-256;
- v0.35 static-plan SHA-256;
- install-receipt SHA-256;
- exact approved permission set;
- display selector;
- absolute bundle path;
- absolute desktop-entry path;
- desktop-entry SHA-256;
- `persistent_launch_grant_authority=true`;
- `status=enabled`;
- canonical grant SHA-256.

The grant has a strict reconstruction parser and rejects digest tampering.

## Desktop bundle

Registration stages and atomically promotes a bundle containing:

```text
desktop-plan.json
browser-plan.json
static-plan.json
install-receipt.json
grant.json
```

The final directory is content-addressed by the desktop-plan digest prefix:

```text
DESKTOP_ROOT/
  APP_ID/
    PLAN_SHA_PREFIX/
```

An existing destination is never overwritten.

## XDG desktop entry

The launcher is a standard XDG desktop file.

Its execution command is:

```text
phi-app launch-desktop-bundle "ABSOLUTE_BUNDLE_PATH"
```

It does not contain shell execution such as `sh -c`.

The complete desktop-entry text is SHA-256 bound into the grant.

At click-time launch, PhiOS requires that exact desktop entry to still exist and match its recorded digest.

Changing the visible launcher text, command, or metadata after grant creation therefore blocks launch.

## Current-user Wayland selector

The only v0.38 display selector is:

```text
current_user_wayland_env
```

At launch PhiOS reads:

```text
XDG_RUNTIME_DIR
WAYLAND_DISPLAY
```

Validation requires:

- `XDG_RUNTIME_DIR` is absolute;
- it is not a symlink;
- it exists as a directory;
- it is owned by the current effective UID;
- `WAYLAND_DISPLAY` is a safe basename, not a path;
- the resulting display path is a Unix socket;
- the socket is owned by the current user.

The resulting socket is then passed into the v0.37 planner.

v0.37 records the exact socket filesystem identity and checks it again at execution.

## Click-time reconstruction

A one-click launch does not trust persisted JSON merely because it lives in a PhiOS directory.

It:

1. parses the desktop plan;
2. parses the browser plan;
3. parses the static plan;
4. parses the install receipt;
5. parses the persistent grant;
6. verifies the grant binds all supplied payloads;
7. verifies the launch bundle path;
8. verifies the XDG desktop entry still matches its grant digest;
9. recomputes the desktop plan from the current installed tree;
10. resolves the current-user Wayland socket;
11. creates a fresh v0.37 exact-socket plan;
12. constructs the v0.37 launch request using the grant's reviewed browser authorities;
13. runs the visible-browser service;
14. emits both the v0.37 session receipt and the v0.38 desktop-launch receipt.

## Wayland restart behavior

The persistent grant does not bind one Wayland inode.

If the compositor replaces its socket, the next click resolves the new current-user socket and produces a new v0.37 plan SHA.

The v0.38 desktop grant remains valid only because its reviewed policy explicitly authorizes the current-user Wayland selector.

The new exact socket identity is captured in the new v0.37 plan and desktop launch receipt.

## Launch receipt

The v0.38 receipt binds:

- UUID/time;
- app identity;
- persistent grant SHA-256;
- desktop-plan SHA-256;
- v0.36 browser-plan SHA-256;
- v0.35 static-plan SHA-256;
- install-receipt SHA-256;
- actual per-launch v0.37 visible-plan SHA-256;
- actual v0.37 visible-session receipt SHA-256;
- actual Wayland socket identity;
- approved persistent permission set;
- final session status;
- `persistent_launch_grant_authority=true`;
- `display_authority=true`;
- canonical receipt SHA-256.

The receipt has strict reconstruction and digest-tamper rejection.

## Revocation

A durable launcher must have a durable revocation path.

Revocation requires explicit approval of the exact canonical desktop-launch grant SHA-256.

PhiOS then verifies:

- bundle remains under the configured desktop root;
- grant is valid;
- grant bundle path matches the selected bundle;
- desktop entry remains under the configured applications root;
- desktop entry SHA-256 still matches the grant.

Only then does it remove the XDG desktop entry and persistent bundle.

A revoke receipt records the retired grant and removed paths.

## Failure boundaries

v0.38 blocks launch when:

- bundle is a symlink;
- payload JSON is malformed or oversized;
- any canonical digest is wrong;
- launcher entry is missing or changed;
- installed app changed;
- static plan changed;
- browser plan changed;
- XDG runtime directory is invalid;
- Wayland display name attempts path traversal;
- current display is not a Unix socket;
- current display is not owned by the user;
- v0.37 validation or execution fails.

## Existing PhiLauncher relationship

v0.38 installs standard XDG desktop entries.

It does not rewrite the older Phi command-menu behavior in `phios.desktop.launcher.PhiLauncher`.

Desktop environments and XDG-aware launchers can discover the installed `.desktop` entry normally.

A later catalog/UI rung can integrate governed apps directly into PhiOS's custom launcher surface.

## Explicit non-capabilities

v0.38 does not:

- auto-approve a desktop grant;
- expand permissions after grant installation;
- persist a stale exact Wayland socket;
- trust an edited desktop entry;
- trust an edited bundle;
- launch a changed installed app;
- install an icon-theme asset;
- infer an application-specific icon;
- modify the existing Phi command-menu UI;
- add X11;
- add GPU/device authority;
- add audio/camera/microphone authority;
- filter browser network egress.

## Planned next rung

v0.39 should add a **Desktop App Catalog Contract**.

That rung can provide:

- discovery of installed governed desktop bundles;
- app name/version/icon-state presentation;
- grant state;
- launch/revoke actions;
- launcher integration;
- deterministic catalog snapshot;
- catalog receipt.

That turns individual governed desktop entries into a coherent PhiOS application library.
