# PhiOS App Platform v0.37

PhiOS App Platform v0.37 adds the **Visible Browser / GUI Session Contract**.

v0.36 can execute a verified web app in a separately approved headless Chromium session. v0.37 adds
a separately reviewed **Wayland display authority** so that same governed application can appear as
a visible browser app window.

The authority ladder stays explicit:

```text
serve app bytes
≠ execute page JavaScript
≠ grant display access
≠ grant GPU access
≠ grant host-home access
≠ persist browser state
```

## Current display scope

v0.37 intentionally supports only:

```text
display_transport = wayland
browser_mode      = visible_app_window
profile_mode      = ephemeral
```

It does **not** support X11 in this rung.

It does **not** grant direct GPU/device access.

## Wayland authority

Planning requires one explicit absolute Wayland Unix-socket path.

PhiOS records:

- exact resolved socket path;
- display/socket name;
- filesystem device;
- inode;
- nanosecond change timestamp;
- owner UID;
- owner GID.

The socket must:

- be a Unix socket;
- not be a symlink;
- be owned by the current user.

The identity is checked again immediately before launch.

A replaced compositor socket therefore invalidates the reviewed plan even when the filesystem reuses
the same filename or inode.

## Sandbox mapping

Only the exact reviewed socket is mounted:

```text
HOST_SOCKET
    ↓
/run/phios-wayland/WAYLAND_NAME
```

The host runtime directory is **not** mounted.

The browser receives:

```text
WAYLAND_DISPLAY=/run/phios-wayland/WAYLAND_NAME
XDG_SESSION_TYPE=wayland
```

and Chromium runs with:

```text
--ozone-platform=wayland
--app=EXACT_REVIEWED_LOOPBACK_URL
```

## Permissions

v0.37 requires exactly:

```text
browser.display.wayland
browser.network.inherit
browser.page.execute
```

Those permissions are separately approved for the visible session.

## Still denied

v0.37 keeps these authorities false:

```text
persistent_profile_authority = false
host_home_authority          = false
gpu_device_authority         = false
x11_authority                = false
```

The browser still uses the private ephemeral profile created inside the Bubblewrap session.

## Coordinated lifecycle

v0.37 reuses the v0.36 coordinated lifecycle rather than creating a new server implementation:

```text
reviewed v0.35 static plan
        ↓
owned static server
        ↓
HTTP 200 readiness
        ↓
visible Wayland Chromium
        ↓
bounded foreground session
        ↓
owned static server termination
        ↓
visible-browser receipt
```

## Commands

Plan:

```bash
phi-app plan-visible-browser \
  browser-session-plan.json \
  --wayland-socket /run/user/1000/wayland-0 \
  > visible-browser-plan.json
```

Review:

```bash
phi-app review-visible-browser visible-browser-plan.json
```

Run:

```bash
phi-app run-visible-browser \
  visible-browser-plan.json \
  browser-session-plan.json \
  static-web-plan.json \
  install-receipt.json \
  --approve-visible-browser-plan-sha EXACT_VISIBLE_PLAN_SHA256 \
  --approve-browser-session-plan-sha EXACT_BROWSER_PLAN_SHA256 \
  --approve-static-web-plan-sha EXACT_STATIC_PLAN_SHA256 \
  --allow-browser-permission browser.display.wayland \
  --allow-browser-permission browser.network.inherit \
  --allow-browser-permission browser.page.execute
```

See `docs/PHIOS_APP_PLATFORM_V0.37_VISIBLE_BROWSER.md`.
