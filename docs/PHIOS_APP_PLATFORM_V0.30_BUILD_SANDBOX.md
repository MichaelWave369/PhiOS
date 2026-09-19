# PhiOS App Platform v0.30 — Linux Build Sandbox / Containment Contract

## Status

Alpha contract.

Schemas:

- `phios.build_sandbox_policy.v0.1`
- `phios.build_sandbox_receipt.v0.1`

## Purpose

v0.30 adds enforceable Linux containment around v0.29 governed build execution.

The central rule is:

> A sandbox receipt may claim only controls implemented by the selected backend and exercised by
> backend preflight.

v0.30 does not rename an isolated directory into a security boundary.

## Backend

The initial backend is Bubblewrap.

Sandboxed execution requires:

- Linux;
- an absolute Bubblewrap executable;
- `prlimit` for bounded POSIX resource limits;
- a successful Bubblewrap namespace preflight.

Backend absence or failed namespace creation blocks execution.

There is no automatic fallback to the v0.29 direct subprocess runner.

## Namespace contract

The Bubblewrap command requests:

- mount namespace isolation;
- user namespace isolation;
- PID namespace isolation;
- IPC namespace isolation;
- UTS namespace isolation;
- cgroup namespace isolation where supported by Bubblewrap's `--unshare-all`;
- parent-death behavior;
- a new session.

The receipt describes the cgroup namespace as **requested**, not as a cgroup resource controller.

## Filesystem contract

The build receives:

- the execution source bound read/write at `/workspace`;
- selected operating-system tool/library roots read-only;
- selected `/etc` runtime/CA/DNS files read-only;
- private `/proc`;
- private `/dev`;
- tmpfs `/tmp`;
- private empty `/home/phios`.

The host user's home directory is not mounted.

The sandbox starts with a cleared process environment. PhiOS sets only the bounded environment
needed for the sandboxed build, including a sanitized `PATH`.

v0.30 therefore claims **workspace-only writable mount visibility**, not that the build sees zero
host files. System executables and libraries remain visible read-only.

## Network contract

### deny

Default:

```text
network_mode = deny
```

Bubblewrap keeps the newly unshared network namespace created by `--unshare-all`.

The receipt records:

```text
network_namespace_enforced = true
host_network_inherited = false
network_allowlist_enforced = false
```

### inherit

Explicit operator choice:

```text
network_mode = inherit
```

Bubblewrap receives `--share-net`.

This mode is allowed only when the v0.29 execution request already contains the reviewed
`build.network.dependencies` permission.

The receipt records:

```text
network_namespace_enforced = false
host_network_inherited = true
network_allowlist_enforced = false
```

**inherit is not a network allowlist.**

v0.30 does not implement domain-, host-, or port-level egress filtering.

## Resource policy

The canonical sandbox policy contains bounded values for:

- per-step wall-clock seconds;
- CPU seconds;
- virtual address-space bytes;
- maximum open files;
- maximum output-file size.

Wall-clock enforcement remains the v0.29 subprocess timeout.

The other limits are applied using `prlimit` inside the sandbox before the reviewed tool process.

v0.30 does **not** claim:

- physical-memory/cgroup memory accounting;
- process-count limits;
- I/O bandwidth limits;
- CPU quota/percentage scheduling.

The receipt says `process_count_limit_enforced = false`.

## Command construction

The reviewed v0.28 argv remains the inner command identity.

The Bubblewrap wrapper is deterministic from:

- sandbox policy;
- execution source path;
- build working directory;
- resolved system tool path.

The inner process is still launched without an interactive shell.

Representative structure:

```text
bwrap
  --die-with-parent
  --new-session
  --unshare-all
  [--share-net only for explicit inherit mode]
  ...
  --bind HOST_EXECUTION_SOURCE /workspace
  --chdir /workspace
  --clearenv
  ...
  prlimit RESOURCE_LIMITS --
  EXACT_REVIEWED_TOOL EXACT_REVIEWED_ARGS...
```

## Tool boundary

The executable for a reviewed build step must resolve beneath one of the backend's read-only system
roots.

The initial roots include conventional Linux system/tool locations such as:

- `/usr`;
- `/bin`;
- `/sbin`;
- `/lib`;
- `/lib64`;
- `/opt`;
- `/nix/store`.

A tool resolved from an arbitrary user-home path is rejected instead of causing the host home to be
mounted into the sandbox.

Repository-local helper binaries may still be reached indirectly by reviewed package-manager
commands from within the writable `/workspace`; PhiOS does not add host-home visibility for them.

## Preflight

Before v0.29 copies or executes the reviewed source, the Bubblewrap backend:

1. verifies Linux;
2. resolves Bubblewrap and `prlimit`;
3. obtains bounded Bubblewrap version output;
4. runs a minimal namespaced `true` command using the same sandbox construction family.

If namespace creation or required mounts are unavailable, execution blocks.

## Dual receipts

v0.30 preserves the v0.29 execution receipt and adds a separate sandbox receipt.

The sandbox receipt binds:

- sandbox receipt UUID/time;
- v0.29 execution ID;
- v0.29 execution receipt SHA-256;
- app/commit identity;
- plan SHA-256;
- source snapshot SHA-256;
- complete canonical sandbox policy;
- policy SHA-256;
- backend identity;
- control evidence;
- containment-level label;
- build status.

The sandbox receipt receives its own canonical SHA-256.

## Explicitly unsupported controls

v0.30 records, rather than hides, these current gaps:

```text
seccomp_enforced = false
network_allowlist_enforced = false
process_count_limit_enforced = false
```

It also does not claim:

- a pinned container image/root filesystem;
- kernel-level eBPF policy;
- SELinux/AppArmor profile enforcement;
- cgroup CPU/memory accounting;
- domain-specific dependency mediation.

## Receipt persistence

The v0.29 execution receipt is written first.

v0.30 then writes the sandbox receipt atomically.

If sandbox-receipt persistence fails after execution, the combined CLI result reports
`sandbox_receipt_persisted = false` and exits nonzero rather than claiming a fully receipted
sandboxed success.

The already-created v0.29 execution receipt remains evidence that execution occurred.

## Planned next rung

v0.31 should add a **Dependency Staging / Network Broker Contract**.

The goal is to stop making ordinary package builds choose between:

1. a strong network-denied sandbox that cannot fetch dependencies; or
2. inheriting the host network.

A dependency broker can resolve and stage approved dependency artifacts outside the build sandbox,
hash them, emit a dependency receipt, then let the actual build run with `network_mode=deny`.

That provides a path toward network-denied reproducible builds before packaging and installation.
