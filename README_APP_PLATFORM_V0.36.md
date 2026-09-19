# PhiOS App Platform v0.36

PhiOS App Platform v0.36 adds the **Browser Session Contract**.

v0.35 can map and serve a verified static build. v0.36 can now execute that served application in
a separately approved **headless Chromium session** while keeping browser authority distinct from
server authority.

The authority ladder remains explicit:

```text
serve reviewed bytes
≠ launch a browser
≠ execute page JavaScript
≠ grant display access
≠ persist a browser profile
```

## Coordinated session

v0.36 does not ask the operator to start a server in one terminal and then merely trust whatever
later answers on that port.

Instead PhiOS coordinates both sides:

```text
v0.35 static-web plan
        ↓
v0.36 browser-session plan
        ↓
review exact browser plan SHA
        ↓
approve exact v0.35 static plan SHA
        ↓
approve exact browser permissions
        ↓
reverify installed artifact binding
        ↓
confirm reviewed port is initially free
        ↓
start exact reviewed v0.35 server in Bubblewrap
        ↓
HEAD reviewed 127.0.0.1 URL → HTTP 200
        ↓
run headless Chromium in second Bubblewrap sandbox
        ↓
execute page JavaScript / dump resulting DOM
        ↓
terminate coordinated static server
        ↓
browser-session receipt
```

## Browser authority

v0.36 requires exactly:

```text
browser.network.inherit
browser.page.execute
```

Those permissions are reviewed and approved separately from the v0.35 static-server plan.

The browser inherits host networking because it must reach the host loopback listener. This is
**broad browser network authority**, not a network allowlist.

The Chromium flags reduce background browser networking, but they do not prevent application
JavaScript from reaching external network destinations.

## Isolation

v0.36 uses a second Bubblewrap runtime for Chromium.

The browser receives:

- private home;
- private tmp;
- an ephemeral profile at `/home/phios/browser-profile`;
- read-only system/runtime roots;
- broad host-network inheritance;
- no persistent app-data mount;
- no host user home/profile mount;
- no display socket;
- no GUI authority.

The browser's payload root is an empty read-only session root. Application content is reached over
the exact reviewed loopback URL rather than through a writable source mount.

## Headless execution

Current mode:

```text
headless_dump_dom
```

Current browser family:

```text
chromium
```

Accepted logical tools:

```text
chromium
chromium-browser
```

The fixed session includes:

```text
--headless=new
--dump-dom
--virtual-time-budget=5000
--user-data-dir=/home/phios/browser-profile
```

plus bounded flags that disable extensions, sync, crash reporting, component updates, proxy use,
GPU use, and several background browser services.

The DOM itself is not persisted in the PhiOS receipt. PhiOS records only stdout/stderr byte counts
and SHA-256 digests.

## Lifecycle binding

The v0.36 readiness window plus browser execution window must fit inside the already reviewed v0.35
static-server window.

```text
readiness_window + browser_window <= static_serve_window
```

A browser plan cannot silently extend the server authority it depends on.

## Commands

Plan:

```bash
phi-app plan-browser-session static-web-plan.json \
  --browser-tool chromium \
  --session-seconds 60 \
  --readiness-timeout-ms 3000 \
  > browser-session-plan.json
```

Review:

```bash
phi-app review-browser-session browser-session-plan.json
```

Run:

```bash
phi-app run-browser-session \
  browser-session-plan.json \
  static-web-plan.json \
  install-receipt.json \
  --approve-browser-session-plan-sha EXACT_BROWSER_PLAN_SHA256 \
  --approve-static-web-plan-sha EXACT_STATIC_WEB_PLAN_SHA256 \
  --allow-browser-permission browser.network.inherit \
  --allow-browser-permission browser.page.execute
```

See `docs/PHIOS_APP_PLATFORM_V0.36_BROWSER_SESSION.md`.
