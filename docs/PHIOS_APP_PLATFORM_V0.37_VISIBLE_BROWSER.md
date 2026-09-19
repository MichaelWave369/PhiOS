# PhiOS App Platform v0.37 — Visible Browser / GUI Session Contract

## Status

Alpha contract.

Schemas:

- `phios.visible_browser_session_plan.v0.1`
- `phios.visible_browser_session_plan_review.v0.1`
- `phios.visible_browser_session_receipt.v0.1`

## Purpose

v0.37 adds a separately reviewed GUI/display authority above the v0.36 headless Chromium session.

The central rule is:

> Browser execution authority does not imply display authority.

The visible session therefore has its own plan, canonical digest, permission set, display binding, and
receipt.

## Input ancestry

Planning starts from one valid v0.36 browser-session plan.

The visible plan binds:

- v0.36 browser-session plan SHA-256;
- v0.35 static-web plan SHA-256;
- v0.33 install-receipt SHA-256;
- installed-tree SHA-256;
- static-root SHA-256;
- exact reviewed loopback URL;
- browser family/tool;
- session duration;
- readiness timeout.

At execution time PhiOS recomputes both the current v0.35 static plan and the current v0.36 browser
plan from the unchanged install state.

Any provenance drift blocks the visible session.

## Wayland-only first

v0.37 supports:

```text
display_transport = wayland
```

It does not support X11.

This is deliberate. X11 would introduce a different socket/authentication authority surface and
belongs in its own adapter rather than being silently bundled into the first GUI contract.

## Wayland socket identity

The operator supplies one exact absolute Wayland socket path.

Planning requires that path to:

- exist;
- not be a symlink;
- be a Unix-domain socket;
- be owned by the current effective user.

The plan records the exact socket identity tuple:

```text
resolved path
display/socket basename
filesystem device
inode
ctime_ns
owner UID
owner GID
```

### Why ctime_ns is included

A Unix socket can be removed and recreated at the same path, and filesystems can immediately reuse
the same inode.

v0.37 therefore does not treat path + inode as sufficient stale-authority protection.

The nanosecond change timestamp plus ownership metadata are also bound.

The identity is rechecked immediately before sandbox construction and again by the Wayland-aware
runtime runner.

A changed socket invalidates the reviewed plan.

This is a filesystem identity binding. v0.37 does not claim cryptographic identity for the compositor
process itself.

## Exact socket mount

The browser sandbox does **not** mount the host runtime directory.

It creates:

```text
/run/phios-wayland
```

inside the sandbox and bind-mounts only:

```text
HOST_EXACT_SOCKET
→ /run/phios-wayland/SOCKET_NAME
```

The bind is read-only at the filesystem mount layer.

The browser receives:

```text
WAYLAND_DISPLAY=/run/phios-wayland/SOCKET_NAME
XDG_SESSION_TYPE=wayland
```

The host `XDG_RUNTIME_DIR` is not exposed as a directory.

## Visible Chromium argv

The browser family remains Chromium.

Accepted logical tools:

- `chromium`;
- `chromium-browser`.

The visible argv removes the v0.36 headless/DOM-dump flags and adds:

```text
--ozone-platform=wayland
--app=EXACT_REVIEWED_LOOPBACK_URL
```

It retains bounded flags that disable:

- extensions;
- sync;
- component updates;
- crash reporting;
- proxy use;
- GPU use;
- several background browser services.

The browser continues to use:

```text
--user-data-dir=/home/phios/browser-profile
```

inside the private sandbox home.

## GPU authority

v0.37 does not mount host DRM/GPU devices.

Plan and receipt invariants:

```text
gpu_device_authority = false
```

Chromium is launched with GPU use disabled in this rung.

Visible rendering therefore does not imply direct device authority.

## Browser permissions

The visible permission set is fixed:

```text
browser.display.wayland
browser.network.inherit
browser.page.execute
```

Execution requires exact approval of this complete set.

Missing permissions fail closed.

Extra permissions also fail closed.

## Three plan approvals

Execution requires exact approval of:

1. the v0.37 visible-browser plan SHA-256;
2. the bound v0.36 browser-session plan SHA-256;
3. the bound v0.35 static-web plan SHA-256.

The visible plan already binds those ancestors, but explicit approval keeps the operator review chain
visible rather than collapsing three authority transitions into one checkbox.

## Reused coordinated lifecycle

v0.37 reuses the v0.36 coordinated server/browser lifecycle.

The common runner still:

1. checks the reviewed loopback port is initially free;
2. preflights the static-server Bubblewrap sandbox;
3. records Python identity;
4. preflights the browser Bubblewrap sandbox;
5. records Chromium identity;
6. starts the exact v0.35 static server;
7. performs bounded HTTP readiness checks;
8. requires HTTP 200;
9. launches Chromium only after readiness;
10. terminates the owned static server when the browser session ends.

v0.37 changes only the browser sandbox/display authority and Chromium argv.

## Lifecycle bound

The visible session inherits the duration and readiness timeout from the v0.36 parent plan.

It does not extend them.

The existing invariant remains:

```text
browser_session_seconds
+ ceil(readiness_timeout_ms / 1000)
<= static_serve_seconds
```

## Sandbox authority

The browser continues to receive:

- private home;
- private tmp;
- private proc/dev;
- read-only system/runtime roots;
- ephemeral browser profile;
- broad host-network inheritance;
- no persistent app-data mount;
- no host home mount.

v0.37 additionally grants exactly one reviewed Wayland socket.

It does not grant:

- X11;
- arbitrary host runtime-directory access;
- GPU/DRM devices;
- host browser profile;
- persistent browser profile;
- DBus;
- PulseAudio/PipeWire sockets;
- arbitrary filesystem mounts.

## Network semantics

The browser still requires broad host-network inheritance so it can reach the host loopback static
server.

The starting URL is reviewed loopback, but application JavaScript can make external network
requests.

v0.37 does not claim:

- destination allowlisting;
- DNS filtering;
- proxy enforcement;
- egress containment.

Display authority and network authority remain separate permissions even though both are required for
this browser session.

## Display authority semantics

The plan records:

```text
display_authority = false
```

because a plan is not execution authority.

A successful/attempted execution receipt records:

```text
display_authority = true
```

because the reviewed Wayland socket was granted to that browser process.

This does not assert that:

- the window was visible to the human;
- the compositor displayed it correctly;
- the application UI rendered correctly;
- user input occurred;
- the page was semantically healthy.

Those are separate observations.

## Visible-browser receipt

The receipt binds:

- UUID/time;
- app ID/version;
- visible-browser plan SHA-256;
- v0.36 parent browser-plan SHA-256;
- v0.35 static-plan SHA-256;
- install-receipt SHA-256;
- installed-tree SHA-256;
- static-root SHA-256;
- exact loopback URL;
- approved visible-browser permissions;
- browser tool/mode/profile mode;
- Wayland display transport;
- exact Wayland display evidence;
- browser sandbox policy;
- server/browser backend identities;
- Python/Chromium tool identities;
- server/browser control evidence;
- readiness result;
- owned-server termination;
- server/browser exit metadata and output digests;
- session status/failure reason;
- page-execution authority;
- browser network authority;
- display authority;
- persistent-profile authority false;
- host-home authority false;
- GPU-device authority false;
- X11 authority false;
- canonical receipt SHA-256.

The receipt has a strict reconstruction parser and rejects digest tampering.

## CI verification model

Portable CI creates real Unix-domain socket fixtures and verifies:

- socket type validation;
- socket ownership binding;
- device/inode/ctime/UID/GID identity;
- stale socket replacement rejection;
- exact socket mount command shape;
- no host runtime-directory mount;
- Wayland environment injection;
- fixed visible Chromium argv;
- exact three-plan approval;
- exact permission approval;
- visible-session authority receipt;
- timeout behavior;
- receipt reconstruction/tamper rejection.

Portable CI does not require a real host compositor or assert that GitHub's runner displayed a
visible browser window.

The production runner performs Bubblewrap preflight and attempts the reviewed Wayland connection on
the target Linux desktop.

## Explicit non-capabilities

v0.37 does not:

- support X11;
- mount an entire host runtime directory;
- grant GPU/DRM authority;
- grant audio sockets;
- grant camera/microphone devices;
- grant DBus;
- persist browser profile state;
- mount the host user's browser profile;
- prove the window was visually correct;
- prove user interaction;
- create a long-lived desktop service;
- auto-discover a Wayland socket behind the operator's back.

## Planned next rung

v0.38 should move from a raw governed GUI session to a **Desktop App Launch Contract**.

That rung can bind:

- installed app identity;
- selected runtime adapter chain;
- app icon/name metadata;
- launcher entry;
- exact v0.37 GUI-session plan;
- desktop launch approval;
- one-click lifecycle;
- launcher/session receipt.

That is the point where the governed application path can become a normal PhiOS desktop app instead
of a sequence of operator CLI commands.
