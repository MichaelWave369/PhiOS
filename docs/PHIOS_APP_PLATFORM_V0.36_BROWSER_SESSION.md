# PhiOS App Platform v0.36 — Browser Session Contract

## Status

Alpha contract.

Schemas:

- `phios.browser_session_plan.v0.1`
- `phios.browser_session_plan_review.v0.1`
- `phios.browser_session_receipt.v0.1`

## Purpose

v0.36 adds a separately governed browser-execution boundary above the v0.35 static-web adapter.

The central rule is:

> Serving reviewed application bytes does not grant a browser authority to execute them.

The browser session therefore requires its own reviewed plan, its own canonical digest, and its own
explicit permission approval.

## Why headless first

A visible browser window requires additional host interfaces such as Wayland or X11 sockets and
possibly GPU/device access.

Those are meaningful authority expansions.

v0.36 intentionally establishes the browser-execution contract **without** those interfaces:

```text
display_mode = headless
display_authority = false
```

This lets PhiOS execute the page's JavaScript, observe bounded process output, and receipt the
session before a later rung introduces GUI authority.

## Input binding

Browser planning starts from one valid:

```text
phios.static_web_adapter_plan.v0.1
```

with:

```text
status = ready_for_review
```

The browser plan binds:

- app ID/version;
- v0.35 static-web plan SHA-256;
- v0.33 install-receipt SHA-256;
- installed-tree SHA-256;
- static-root SHA-256;
- exact loopback URL;
- reviewed v0.35 static serve duration.

At execution time PhiOS recomputes the v0.35 plan from the unchanged install receipt and installed
tree. Any drift blocks the browser session.

## Separate approvals

Execution requires approval of:

1. the exact v0.36 browser-session plan SHA-256;
2. the exact v0.35 static-web plan SHA-256;
3. the exact browser permission set.

The v0.36 permission set is fixed:

```text
browser.network.inherit
browser.page.execute
```

Missing permissions block execution.

Extra permissions also block execution.

## Coordinated static server

v0.36 does not accept an arbitrary pre-existing process on the reviewed port as provenance for the
application.

The production runner:

1. verifies the reviewed loopback port is initially unoccupied;
2. preflights the v0.35 Bubblewrap server sandbox;
3. records the Python tool identity;
4. preflights the browser Bubblewrap sandbox;
5. records the Chromium tool identity;
6. starts the exact v0.35 reviewed Python server command;
7. performs bounded `HEAD /` readiness checks;
8. requires HTTP 200;
9. launches Chromium only after readiness succeeds;
10. terminates the coordinated static server when the browser session ends.

This substantially narrows the chance of accidentally browsing an unrelated localhost service.

The port-free check plus owned process lifecycle are strong local bindings, but v0.36 does not claim
a kernel-level exclusive provenance proof for the TCP port.

## Lifecycle authority

Browser planning records:

- v0.35 static serve seconds;
- browser session seconds;
- readiness timeout milliseconds.

The invariant is:

```text
browser_session_seconds
+ ceil(readiness_timeout_ms / 1000)
<= static_serve_seconds
```

A browser plan therefore cannot extend the reviewed lifetime of the static server it depends on.

## Browser family

v0.36 supports the Chromium family only.

Accepted logical executables:

- `chromium`;
- `chromium-browser`.

The actual resolved executable path and version are probed at runtime and stored in the receipt.

The executable must resolve beneath the runtime's existing read-only system roots.

v0.36 does not widen filesystem mounts merely to support distribution-specific packaging wrappers
such as Snap launch shims.

## Chromium argv contract

The argv is deterministic plan content.

Important fixed flags include:

```text
--headless=new
--dump-dom
--no-first-run
--no-default-browser-check
--disable-sync
--disable-background-networking
--disable-component-update
--disable-domain-reliability
--disable-breakpad
--disable-crash-reporter
--disable-extensions
--disable-dev-shm-usage
--disable-gpu
--no-proxy-server
--disable-features=Translate,OptimizationHints,MediaRouter
--virtual-time-budget=5000
--user-data-dir=/home/phios/browser-profile
EXACT_REVIEWED_LOOPBACK_URL
```

These flags reduce unrelated browser behavior.

They are **not** treated as a security boundary equivalent to network filtering.

## Browser profile

v0.36 profile mode is fixed:

```text
profile_mode = ephemeral
```

Bubblewrap creates a private home and the browser uses:

```text
/home/phios/browser-profile
```

The host user's browser profile is not mounted.

The session scratch directory is deleted after execution.

Plan and receipt invariants include:

```text
persistent_profile_authority = false
host_home_authority = false
```

## Network semantics

The server and browser both require host-network inheritance.

For the browser this authority is explicit:

```text
browser.network.inherit
```

The receipt records:

```text
browser_network_inherited = true
network_namespace_enforced = false
network_allowlist_enforced = false
```

This is broad host-network access.

The exact starting page is loopback-only, but page JavaScript may initiate additional external
requests.

v0.36 does not claim DNS filtering, destination allowlisting, proxy enforcement, or egress
containment.

## Page execution semantics

Approval of:

```text
browser.page.execute
```

authorizes Chromium to execute the served page.

The plan itself records:

```text
page_execution_authority = false
```

The receipt records the authority actually granted for that session:

```text
page_execution_authority = true
```

This field describes granted authority, not an assertion that the application behaved correctly.

A zero browser exit code establishes only that the reviewed browser process completed according to
the v0.36 process contract.

It does not establish application health, semantic correctness, UI correctness, or absence of
console/runtime errors.

## DOM output

Headless Chromium uses `--dump-dom`.

PhiOS streams process output and does not persist the DOM text in the browser-session receipt.

The receipt stores only:

- browser stdout byte count;
- browser stdout SHA-256;
- browser stderr byte count;
- browser stderr SHA-256.

That gives the session a content identity without turning arbitrary page output into permanent
trusted evidence.

## Sandbox model

Both the trusted static server and Chromium use the v0.34 Bubblewrap runtime substrate.

### Static server sandbox

The selected static root is mounted read-only at `/app`.

The coordinated runner terminates the server when the browser ends. Because this server is launched
as a background coordinated process rather than through the normal blocking runtime call, its
generic runtime control evidence records:

```text
wall_clock_timeout_enforced = false
```

The browser-session lifecycle controller provides the actual bounded termination.

### Browser sandbox

The browser receives:

- private home;
- private tmp;
- private proc/dev;
- read-only system/runtime roots;
- empty read-only `/app` session root;
- no persistent app-data mount;
- broad host-network inheritance;
- process resource limits;
- wall-clock timeout;
- parent-death behavior.

Current containment does not claim:

- seccomp filtering;
- cgroup enforcement;
- process-count enforcement;
- network allowlisting;
- GUI socket isolation because no GUI socket is mounted;
- a browser-specific kernel policy beyond the Bubblewrap/runtime substrate and Chromium's own
  enabled sandbox behavior.

v0.36 does not pass Chromium a flag that disables its browser sandbox.

## Browser-session receipt

The receipt binds:

- UUID/time;
- app ID/version;
- browser-session plan SHA-256;
- static-web plan SHA-256;
- install-receipt SHA-256;
- installed-tree SHA-256;
- static-root SHA-256;
- reviewed loopback URL;
- exact approved browser permissions;
- browser family/tool/mode;
- ephemeral profile mode;
- headless display mode;
- browser sandbox policy;
- static-server Bubblewrap identity;
- Python tool identity;
- browser Bubblewrap identity;
- Chromium tool identity;
- static-server control evidence;
- browser control evidence;
- readiness status/attempts/elapsed time;
- whether the reviewed port was free before spawn;
- coordinated server termination state;
- server process result hashes/counts;
- browser process result hashes/counts;
- browser completion status;
- bounded failure reason;
- page execution authority;
- broad browser-network inheritance;
- display authority false;
- persistent-profile authority false;
- host-home authority false;
- canonical receipt SHA-256.

The receipt has a strict reconstruction parser and rejects digest tampering.

## Portable CI boundary

GitHub-hosted CI does not need Chromium or a working user-namespace Bubblewrap host.

Portable tests verify:

- deterministic plan construction;
- exact static-plan binding;
- exact browser-plan approval;
- exact browser permission approval;
- lifecycle-window containment;
- ephemeral/headless authority invariants;
- install drift rejection;
- coordinated server termination semantics;
- loopback readiness evidence;
- DOM output hashing;
- timeout receipt behavior;
- strict receipt reconstruction;
- receipt digest-tamper rejection.

Production execution still performs real Bubblewrap preflight and executable identity probes.

## Explicit non-capabilities

v0.36 does not:

- open a visible window;
- mount Wayland;
- mount X11;
- mount the user's browser profile;
- persist browser state;
- grant host-home access;
- grant arbitrary host filesystem mounts;
- enforce browser egress allowlists;
- claim that reduced-background-network Chromium flags are network isolation;
- grant camera, microphone, clipboard, USB, serial, Bluetooth, or notification authority;
- keep the static server alive after the coordinated session;
- claim a successful browser process means the application is healthy.

## Planned next rung

v0.37 should add a **Graphical Browser Window Contract**.

That contract can separately govern:

- Wayland versus X11 display authority;
- exact display socket binding;
- optional read-only font/theme resources;
- GPU authority, if any;
- visible Chromium argv;
- window lifecycle;
- session termination;
- graphical-session receipt.

That is the rung where a receipted public web repository can become an actual visible PhiOS desktop
application without smuggling desktop authority into the headless browser contract.
