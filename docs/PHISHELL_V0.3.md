# PhiShell v0.3 — Read-Only Linux Observation

Status: **candidate implementation**  
Target substrate: **Linux / Wayland path**  
Primary invariant: **CAPABILITY != AUTHORITY**

PhiShell v0.3 adds the first real Linux substrate observation code while preserving a hard separation between observation, authority, and effects.

## Scope

v0.3 introduces:

- a native Node.js Linux host probe;
- a versioned host-observation wire contract;
- typed PhiShell observation models;
- host and session identity observation;
- CPU/load observation;
- memory observation;
- root-filesystem storage observation;
- network-interface observation with IP and MAC data intentionally omitted;
- power-supply discovery through Linux sysfs;
- init-system observation;
- an explicit unbound state for specific service-status transport;
- a PhiShell System Inspector that renders the same observation shape;
- explicit source labeling so fixture data cannot masquerade as live host data;
- CI execution of the real read-only Linux probe.

## Architecture

v0.3 deliberately separates the Linux-native probe from the browser-rendered shell:

```text
Linux host
    ↓
read-only Node probe
    ↓
phios.host-observation.v1
    ↓
future reviewed local transport
    ↓
PhiShell observation provider
    ↓
System Inspector
```

The future transport is not implemented in this increment.

The current browser shell therefore renders an explicitly labeled deterministic fixture:

```text
source = fixture
native_bridge = unbound
```

The native probe is real and exercised on the Linux GitHub Actions runner, but PhiShell does not falsely claim that fixture values are live host readings.

## Observation envelope

Every snapshot carries the following hard fields:

```text
schemaVersion       = phios.host-observation.v1
readOnly            = true
executionAuthority  = false
effectPerformed     = false
```

Observation does not require or manufacture execution authority.

## Native Linux probe

The native probe lives at:

```text
phishell/host/linuxProbe.mjs
```

It uses only Node.js operating-system and filesystem read interfaces.

It does **not** import or invoke:

- `child_process`;
- `exec`;
- `execFile`;
- `spawn`;
- `sudo`.

A dedicated test scans the source for those execution surfaces.

The probe can be exercised manually on Linux:

```bash
cd phishell
npm run probe:linux -- --json
```

CI uses:

```bash
npm run probe:linux -- --check
```

which collects and validates the snapshot without printing host details into the workflow log.

## Host identity

The probe observes:

- hostname;
- Linux platform;
- kernel release;
- architecture.

These values remain local unless a future reviewed transport explicitly carries them to the local PhiShell process.

## Session identity

The probe observes:

- local username;
- numeric UID when available;
- shell when available;
- `XDG_SESSION_TYPE` when available.

No authentication tokens, environment dumps, secrets, or credentials are collected.

## Resource observation

v0.3 observes:

- logical CPU count;
- CPU model;
- load averages;
- total/free memory;
- memory utilization;
- root-filesystem total/free storage;
- root-filesystem utilization.

The probe performs no tuning, scheduling, allocation, mounting, or storage mutation.

## Network observation

Network observation is intentionally metadata-minimized.

The v0.3 contract includes only:

- interface name;
- observed address families;
- whether all records for the interface are internal.

The contract deliberately omits:

- IP addresses;
- MAC addresses.

This is enforced by tests on both the native probe result and the browser fixture.

## Power observation

On Linux systems exposing `/sys/class/power_supply`, v0.3 may observe:

- supply name;
- type;
- status;
- capacity percentage when present.

The probe reads sysfs only.

It contains no power-control operation.

## Init and service boundary

v0.3 may observe whether the conventional systemd runtime directory exists.

Specific service status is **not** bound in this increment:

```text
serviceStatusBound = false
```

This avoids quietly introducing D-Bus calls or `systemctl` process execution before a dedicated service-observation transport is reviewed.

Service mutation remains blocked by the v0.2 zero-privilege effect adapter.

## Capability plane

Read capabilities exposed by the shell model now include:

```text
system.inspect
session.inspect
resource.inspect
network.inspect
power.inspect
init.inspect
```

Specific service status remains unavailable:

```text
service.inspect = unavailable
```

Mutating capabilities remain unavailable:

```text
system.power       = unavailable
network.configure  = unavailable
package.manage     = unavailable
service.control    = unavailable
```

## Privacy boundary

The probe is designed for local-machine observability.

It does not collect:

- network addresses;
- MAC addresses;
- environment-variable dumps;
- process command lines;
- file contents outside the narrow OS/sysfs fields required by the contract;
- authentication material.

CI's `--check` mode does not print the collected host snapshot.

## Tests

The v0.3 PhiShell lane now verifies:

1. the typed fixture remains read-only;
2. fixture observation never gains execution authority;
3. fixture network records cannot contain addresses or MAC fields;
4. service-status transport remains unbound;
5. the real Linux probe executes successfully on Linux;
6. the probe returns `executionAuthority=false`;
7. the probe returns `effectPerformed=false`;
8. network results expose only the minimized metadata contract;
9. the probe source contains no process-execution APIs;
10. the TypeScript shell still type-checks and builds.

CI sequence:

```text
npm install
    ↓
npm test
    ↓
npm run probe:linux -- --check
    ↓
npm run build
```

## Authority boundary

v0.3 does not weaken the v0.2 authority contract.

The effect adapter remains:

```text
operationalAuthority = false
actionAuthority      = false
executionAuthority   = false
```

The observation plane additionally guarantees:

```text
readOnly           = true
executionAuthority = false
effectPerformed    = false
```

Therefore:

```text
can observe
    !=
can request mutation
    !=
is authorized to mutate
    !=
can perform mutation
```

## Next increment

A safe v0.4 candidate is the **local observation transport**.

That rung can connect the native read-only probe to PhiShell through a narrow local IPC boundary while preserving:

- schema validation;
- local-only binding;
- source identity;
- freshness timestamps;
- bounded fields;
- no generic command execution;
- no mutation methods;
- explicit failure states;
- deterministic observation receipts.

Specific service-status observation can then be considered as its own bounded read interface, without bundling service control into the same transport.
