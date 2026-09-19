# PhiOS App Platform v0.34 — Installed App Runtime Contract

## Status

Alpha contract.

Schemas:

- `phios.runtime_sandbox_policy.v0.1`
- `phios.installed_runtime_plan.v0.1`
- `phios.installed_runtime_plan_review.v0.1`
- `phios.runtime_launch_receipt.v0.1`

## Purpose

v0.34 introduces a separately governed transition from an inert v0.33 install to one foreground
application process.

The central rule is:

> Installation authority does not imply launch authority.

A runtime plan is also not launch authority. Execution requires approval of the exact canonical
runtime-plan SHA-256 and the exact permission set recorded by that plan.

## Installed-tree provenance

Planning starts from one valid v0.33 install receipt.

PhiOS verifies:

- configured install root is available and is not a symlink;
- receipted install path remains beneath that root;
- complete installed-tree SHA-256 matches the install receipt;
- payload SHA-256 matches;
- payload file count matches;
- payload total bytes match;
- installed `.phios/manifest.json` parses as the expected v0.25 app manifest;
- manifest SHA-256, app ID, and app version match the install receipt.

The same installed-tree and manifest checks are repeated immediately before launch.

A plan reviewed against one install state therefore cannot silently authorize a later modified
install tree.

## Direct runtime adapters

v0.34 currently supports only direct file-based Node and Python adapters.

### Node

Requirements:

- manifest runtime is `node`;
- target exists as a regular installed payload file;
- target suffix is `.js`, `.mjs`, or `.cjs`.

Reviewed argv:

```text
node /app/RELATIVE_TARGET
```

Adapter:

```text
node_direct_v034
```

### Python

Requirements:

- manifest runtime is `python`;
- target exists as a regular installed payload file;
- target suffix is `.py`.

Reviewed argv:

```text
python3 /app/RELATIVE_TARGET
```

Adapter:

```text
python_direct_v034
```

## Deliberately unsupported shapes

### Node package.json targets

A manifest target of `package.json` does not tell PhiOS which built artifact should execute.

v0.34 does not infer `dist/index.js`, a package script, or another output behind the operator's
back.

Status:

```text
unsupported_entrypoint
```

### Native

v0.33 artifact identity does not preserve executable mode bits.

v0.34 therefore does not claim that a copied native artifact is executable merely because its bytes
match.

Status:

```text
unsupported_runtime
```

### Static web

Static web requires a browser or serving adapter. Either introduces additional authority and
lifecycle semantics.

v0.34 does not silently invent either.

### local_http

A `local_http` manifest target is a loopback URL/service target, not an installed executable
artifact.

v0.34 records it as unsupported instead of converting a URL into process authority.

## Runtime permissions

Supported runtime permissions:

- `runtime.network.inherit`
- `runtime.data.persist`

Any other manifest permission causes an `unsupported_permissions` plan in v0.34.

### Network

Default:

```text
network_mode = deny
```

Bubblewrap receives:

```text
--unshare-net
```

If and only if the manifest contains `runtime.network.inherit`, the runtime plan requests:

```text
network_mode = inherit
```

Launch then requires exact operator approval of that permission.

Host-network inheritance is broad host-network access. It is not an allowlist and the receipt does
not label it as one.

### Persistent app data

Default:

```text
data_mode = ephemeral
```

No persistent writable application-data mount is exposed.

If and only if the manifest contains `runtime.data.persist`, the reviewed plan may expose:

```text
/phios/app-data
```

as a writable bind from the configured PhiOS app-data root.

That permission must also appear in the exact launch approval.

## Runtime sandbox

The production v0.34 runner is Linux Bubblewrap plus `prlimit`.

The application receives:

- installed payload read-only at `/app`;
- private `/home/phios`;
- private `/tmp`;
- private `/proc` and `/dev`;
- selected host system/runtime roots read-only;
- optional reviewed persistent `/phios/app-data`;
- a clean bounded environment;
- reviewed network mode;
- CPU limit;
- address-space limit;
- open-file limit;
- file-size limit;
- wall-clock timeout;
- parent-death behavior.

The application does not receive a writable installed payload.

### Current containment limitations

v0.34 does not claim:

- seccomp filtering;
- cgroup enforcement;
- process-count enforcement;
- network allowlisting;
- X11/Wayland access;
- DBus access;
- arbitrary host filesystem mounts.

## Bubblewrap verification model

The production runtime performs a real Bubblewrap namespace preflight before launching an
application.

The repository's portable CI tests, however, do not require GitHub's hosted runner to provide a
namespace-capable Bubblewrap environment. CI verifies:

- command construction;
- read-only payload mount;
- network-mode command shape;
- optional data mount shape;
- exact authority checks;
- fail-closed provenance;
- runtime receipt/control binding;
- service behavior through a fake sandbox runner.

This distinction is intentional. CI does not claim kernel isolation that the CI host did not
actually exercise.

## Runtime plan

The runtime plan binds:

- app ID/version;
- v0.33 install-receipt SHA-256;
- manifest SHA-256;
- complete installed-tree SHA-256;
- absolute install path;
- runtime kind;
- chosen adapter;
- manifest entrypoint target;
- sandbox entrypoint path when executable;
- executable tool;
- complete argv;
- requested runtime permissions;
- network mode;
- data mode;
- runtime sandbox policy;
- status;
- explanatory notes;
- `launch_authority=false`.

The plan receives its own canonical SHA-256.

Unsupported plans contain no executable argv.

## Launch approval

A launch request requires:

- a `ready_for_review` runtime plan;
- exact canonical runtime-plan SHA-256 approval;
- the exact v0.33 install receipt bound by the plan;
- exact approved runtime permissions equal to the reviewed permission set.

Missing permissions block launch.

Extra permissions also block launch.

Approval is therefore scoped to exactly the reviewed authority.

## Runtime execution

Immediately before process execution PhiOS again verifies:

- install receipt;
- complete installed tree;
- installed manifest;
- runtime kind;
- entrypoint target;
- entrypoint file containment and regular-file status.

Then the runtime runner:

1. performs Bubblewrap preflight;
2. records the selected runtime tool identity;
3. launches the reviewed argv without a shell;
4. captures stdout/stderr only as byte counts and SHA-256 digests;
5. applies the reviewed wall-clock timeout;
6. records sandbox control evidence;
7. emits a runtime receipt after exit or timeout.

v0.34 is a foreground execution contract. It does not create a persistent service manager.

## Runtime receipt

The receipt binds:

- UUID/time;
- app identity;
- runtime-plan SHA-256;
- install-receipt SHA-256;
- installed-tree SHA-256;
- manifest SHA-256;
- runtime kind and adapter;
- entrypoint target;
- exact approved runtime permissions;
- network mode;
- data mode;
- runtime sandbox policy;
- Bubblewrap backend identity;
- control evidence;
- runtime tool identity;
- exit code;
- timed-out state;
- duration;
- stdout byte count + SHA-256;
- stderr byte count + SHA-256;
- final status;
- bounded failure reason;
- its own canonical SHA-256.

The receipt has a strict reconstruction parser and rejects digest tampering.

## Explicit non-capabilities

v0.34 does not:

- infer a built runtime target from `package.json`;
- execute native apps;
- launch browsers;
- serve static web applications;
- launch `local_http` services;
- grant GUI, Wayland, X11, or DBus access;
- manage background daemons;
- preserve a permanent trust decision;
- provide network allowlists;
- provide arbitrary filesystem mounts;
- make the installed payload writable;
- silently expand manifest permissions;
- launch unsupported plans.

## Planned next rung

v0.35 should expand **Runtime Adapter Mapping** rather than weaken v0.34's direct-file rule.

A useful next target is an explicitly reviewed static-web / built-output adapter contract that can
bind:

- package/build artifact output;
- runtime entrypoint mapping;
- serving/browser role;
- loopback listener policy;
- port allocation;
- browser authority, if any;
- lifecycle/termination behavior;
- adapter-specific receipt.

That lets typical Vite-style public repositories become runnable without turning output inference
into invisible authority.
