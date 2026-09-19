# PhiOS App Platform v0.35 — Static-Web Runtime Adapter Contract

## Status

Alpha contract.

Schemas:

- `phios.static_web_adapter_plan.v0.1`
- `phios.static_web_adapter_plan_review.v0.1`
- `phios.static_web_serve_receipt.v0.1`

## Purpose

v0.35 adds an explicit mapping from a successful installed build artifact set to a bounded
loopback static-file serving session.

The key boundary is:

> Built output mapping must be reviewable evidence, not hidden entrypoint inference.

v0.35 does not change the original app manifest or v0.34 direct-runtime plan.

## Provenance inputs

Static-web planning starts from one valid v0.33 install receipt.

PhiOS reuses v0.34 installed-tree verification and additionally parses the installed:

```text
.phios/package-plan.json
```

The installed package plan must match the install receipt on:

- package-plan SHA-256;
- app ID/version;
- manifest SHA-256;
- artifact-set SHA-256;
- build-plan SHA-256;
- build-execution receipt SHA-256;
- offline-build receipt SHA-256.

## Eligible manifest runtimes

v0.35 mapping currently considers:

- `node`;
- `static_web`.

Other manifest runtime kinds produce an inspectable `unsupported_manifest_runtime` plan.

A Node manifest targeting `package.json` may therefore become statically serveable **only because
the installed artifact evidence contains a recognized built static root**.

The package manifest is not used to invent an executable.

## Recognized output rules

Current deterministic rules:

```text
dist/index.html
    → root: dist/
    → mapping_rule: vite_dist_index

build/index.html
    → root: build/
    → mapping_rule: react_build_index
```

The index path must exist in the receipted artifact list.

The selected static root is then rehashed from the installed payload and bound into the adapter plan.

If no recognized output exists:

```text
status = unsupported_output
```

If more than one recognized output exists:

```text
status = ambiguous_output
```

Ambiguity never resolves itself by precedence.

## Static-root identity

A ready plan binds:

- static root relative path;
- static-root SHA-256;
- file count;
- total bytes;
- `index.html`;
- mapping rule.

The static root digest uses the same deterministic file-set identity used by the v0.33 installed-tree
snapshot.

Immediately before serving, PhiOS rechecks:

- complete install-tree identity;
- installed package-plan identity;
- static-root SHA-256;
- static-root file count;
- static-root total bytes;
- safe regular `index.html`.

## Server process

The trusted serving command is fixed:

```text
python3 -m http.server REVIEWED_PORT \
  --bind 127.0.0.1 \
  --directory /app
```

The selected static root is mounted read-only at:

```text
/app
```

No app source tree, dependency cache, or persistent app-data directory is mounted.

The Python server serves bytes only. It does not execute the application's JavaScript.

## Network semantics

The server must be reachable from the host browser, so this adapter uses:

```text
RuntimeSandboxPolicy(network_mode="inherit")
```

The receipt requires:

```text
host_network_inherited = true
network_namespace_enforced = false
```

The listener argv is fixed to:

```text
127.0.0.1
```

This is a reviewed loopback bind.

It is **not** a kernel network allowlist.

The trusted Python server process technically inherits host networking, and the receipt says so.

## Browser authority

v0.35 deliberately does not open a browser.

Plan and receipt invariants:

```text
browser_launch_authority = false
application_code_executed_by_server = false
```

Browser execution of the served page would be a distinct authority boundary.

Manifest permissions are recorded as:

```text
deferred_manifest_permissions
```

They are not granted to the trusted static server.

## Loopback port

The loopback port is part of the canonical reviewed plan.

Bounds:

```text
1024..65535
```

Default:

```text
8787
```

Changing the port changes the plan SHA-256 and therefore requires new approval.

## Serve window

v0.35 is a bounded foreground serving contract.

Default:

```text
300 seconds
```

Maximum:

```text
3600 seconds
```

When the reviewed wall-clock window expires, the sandbox runner terminates the server and the
operation records:

```text
status = serve_window_complete
```

That timeout is the planned lifecycle boundary, not a failure.

v0.35 does not create a daemon/service manager.

## Static-web plan

The plan binds:

- app ID/version;
- install-receipt SHA-256;
- manifest SHA-256;
- complete installed-tree SHA-256;
- package-plan SHA-256;
- install path;
- manifest runtime/target;
- deferred manifest permissions;
- selected static root;
- static-root SHA-256;
- static file count;
- static total bytes;
- index path;
- mapping rule;
- loopback host;
- loopback port;
- serve seconds;
- fixed server tool/argv;
- sandbox policy;
- plan status;
- explanatory notes;
- browser launch authority false;
- application-code-executed-by-server false;
- launch authority false.

The plan receives its own canonical SHA-256.

## Approval

Serve requires:

- `ready_for_review` plan status;
- exact static-web plan SHA-256 approval;
- the exact v0.33 install receipt bound by the plan.

No plan approval is inferred from earlier install/runtime approval.

## Static-web receipt

The receipt binds:

- UUID/time;
- app identity;
- static-web plan SHA-256;
- install-receipt SHA-256;
- installed-tree SHA-256;
- package-plan SHA-256;
- static-root SHA-256;
- mapping rule;
- loopback URL;
- serve window;
- sandbox policy;
- Bubblewrap backend identity;
- sandbox control evidence;
- Python tool identity;
- exit code;
- timeout state;
- duration;
- stdout byte count + SHA-256;
- stderr byte count + SHA-256;
- final serve status;
- bounded failure reason;
- browser launch authority false;
- application-code-executed-by-server false;
- canonical receipt SHA-256.

The receipt has a strict reconstruction parser and rejects digest tampering.

## Sandbox verification model

The production server uses the same v0.34 Bubblewrap runtime backend and performs a real
Bubblewrap preflight.

Portable CI verifies command/governance behavior with fake runners rather than claiming kernel
isolation that GitHub-hosted CI did not actually exercise.

## Explicit non-capabilities

v0.35 does not:

- open a browser;
- execute application JavaScript in the server;
- grant deferred manifest runtime permissions;
- provide a browser sandbox;
- provide a browser network policy;
- support arbitrary output-root inference;
- pick between multiple static roots;
- bind non-loopback interfaces;
- allocate an unreviewed port;
- run as a background daemon;
- claim host-network inheritance is an allowlist;
- modify installed app content.

## Planned next rung

v0.36 should introduce a **Browser Session Contract** above the v0.35 server.

That contract can separately govern:

- browser executable identity;
- exact served loopback URL;
- temporary vs persistent browser profile;
- browser filesystem access;
- browser network policy;
- browser launch authority;
- page lifecycle;
- termination;
- browser/session receipt.

That would let PhiOS actually display a static web app while preserving the distinction between
serving application bytes and granting a browser authority to execute them.
