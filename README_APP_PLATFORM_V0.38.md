# PhiOS App Platform v0.38

PhiOS App Platform v0.38 adds the **Desktop App Launch Contract**.

v0.37 can open a governed visible Wayland browser session, but it binds one exact compositor socket. That precision is correct for a single session and wrong for a permanent desktop launcher because the Wayland socket may be recreated after compositor restart or reboot.

v0.38 adds a persistent desktop-launch grant above the v0.35/v0.36 chain while preserving v0.37's exact per-launch display binding.

## Authority ladder

```text
installed app
≠ desktop app plan
≠ persistent desktop grant
≠ desktop entry exists
≠ current launch is valid
≠ current display authority
```

The `.desktop` file is not authority. The persistent launch grant is authority.

Every click still revalidates the grant, bundle, installed app, runtime ancestry, current-user Wayland environment, and a freshly minted exact v0.37 display plan.

## Pipeline

```text
v0.33 installed app
        ↓
v0.35 reviewed static plan
        ↓
v0.36 reviewed browser plan
        ↓
v0.38 desktop-app plan
        ↓
review exact plan + persistent permissions
        ↓
explicit install approval
        ↓
persistent launch grant
        ↓
bound XDG .desktop entry
        ↓
user clicks app
        ↓
reload + verify grant/bundle/entry
        ↓
reverify install + v0.35 + v0.36
        ↓
resolve current XDG_RUNTIME_DIR + WAYLAND_DISPLAY
        ↓
validate current-user Unix socket
        ↓
mint fresh v0.37 exact-socket plan
        ↓
visible app session
        ↓
desktop-launch receipt
```

## Persistent permissions

v0.38 requires exactly:

```text
browser.display.wayland
browser.network.inherit
browser.page.execute
desktop.launch.persist
```

`desktop.launch.persist` authorizes the exact reviewed application/runtime ancestry for later one-click launches until the grant is explicitly revoked.

## Current-user Wayland selector

The persistent desktop grant does not store one stale v0.37 socket identity.

Instead it authorizes:

```text
current_user_wayland_env
```

At click time PhiOS requires an absolute current-user-owned `XDG_RUNTIME_DIR`, a safe basename-only `WAYLAND_DISPLAY`, and a current-user-owned Unix socket at the resulting path. PhiOS then creates a fresh v0.37 plan that binds that exact socket identity.

A compositor restart therefore changes the v0.37 plan SHA without invalidating the persistent v0.38 desktop grant.

## XDG desktop entry

v0.38 installs a standard XDG desktop entry whose execution command is:

```text
phi-app launch-desktop-bundle "/absolute/bundle/path"
```

The complete desktop-entry contents are SHA-256 bound into the persistent grant. Changing the launcher file after grant creation blocks launch.

The generic `phios-app` icon name is metadata only in v0.38. This rung does not install a matching icon-theme asset.

## Bundle

The persistent bundle contains:

```text
desktop-plan.json
browser-plan.json
static-plan.json
install-receipt.json
grant.json
```

Launch parses and validates each file independently.

## Commands

Plan:

```bash
phi-app plan-desktop-app browser-session-plan.json static-web-plan.json install-receipt.json > desktop-app-plan.json
```

Review:

```bash
phi-app review-desktop-app desktop-app-plan.json
```

Install the persistent launcher grant:

```bash
phi-app install-desktop-app desktop-app-plan.json browser-session-plan.json static-web-plan.json install-receipt.json --approve-desktop-app-plan-sha EXACT_DESKTOP_PLAN_SHA256 --allow-desktop-permission browser.display.wayland --allow-desktop-permission browser.network.inherit --allow-desktop-permission browser.page.execute --allow-desktop-permission desktop.launch.persist
```

Normal desktop use invokes:

```bash
phi-app launch-desktop-bundle /ABSOLUTE/BUNDLE/PATH
```

Revoke the durable authority:

```bash
phi-app revoke-desktop-app /ABSOLUTE/BUNDLE/PATH --approve-desktop-launch-grant-sha EXACT_GRANT_SHA256
```

Revocation removes both the bound desktop entry and bundle.

See `docs/PHIOS_APP_PLATFORM_V0.38_DESKTOP_LAUNCH.md`.
