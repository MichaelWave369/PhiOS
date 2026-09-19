# PhiOS App Platform v0.30

PhiOS App Platform v0.30 adds the **Linux Build Sandbox / Containment Contract**.

v0.29 can execute an explicitly approved build plan in an isolated working copy. v0.30 adds a
Linux-first containment backend using Bubblewrap and emits a separate sandbox receipt describing
the controls that were actually enforced.

## Operator flow

```text
approved v0.28 build plan
       +
v0.27 acquisition receipt
       ↓
v0.29 execution authority checks
       ↓
v0.30 sandbox policy
       ↓
Bubblewrap backend preflight
       ↓
Linux namespaces + read-only system roots
       ↓
private /proc, /dev, /tmp, HOME
       ↓
writable /workspace only
       ↓
RLIMIT resource budgets
       ↓
reviewed argv, shell=False
       ↓
v0.29 execution receipt
       +
v0.30 sandbox receipt
```

## Command

```bash
phi-app execute-sandboxed-build build-plan.json acquisition-receipt.json \
  --approve-plan-sha EXACT_PLAN_SHA256 \
  --approve-source-sha EXACT_SOURCE_SNAPSHOT_SHA256 \
  --allow-build-permission build.network.dependencies \
  --allow-build-permission build.process.execute \
  --allow-build-permission build.workspace.write
```

The default sandbox network mode is `deny`.

For a reviewed build that genuinely requires dependency network access, the operator may explicitly
choose:

```bash
--sandbox-network inherit
```

That mode is recorded as host-network inheritance. It is **not** described as a network sandbox or
allowlist.

## Linux-first backend

v0.30 requires:

- Linux;
- Bubblewrap (`bwrap`);
- `prlimit`.

If the backend is unavailable or its namespace preflight fails, sandboxed execution blocks. PhiOS
does not silently fall back to the unsandboxed v0.29 runner.

## Evidence

The v0.30 sandbox receipt binds:

- the v0.29 execution receipt SHA-256;
- exact plan and source snapshot identities;
- canonical sandbox-policy SHA-256;
- Bubblewrap executable and version identity;
- platform identity;
- namespace controls;
- writable/read-only mount claims;
- network mode;
- resource-limit claims;
- explicitly unsupported controls.

See `docs/PHIOS_APP_PLATFORM_V0.30_BUILD_SANDBOX.md`.
