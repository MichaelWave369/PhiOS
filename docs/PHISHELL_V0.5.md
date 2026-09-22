# PhiShell v0.5 — Bounded Service Observation

Status: **candidate implementation**  
Target substrate: **Linux / systemd / Wayland path**  
Primary invariant: **CAPABILITY != AUTHORITY**

PhiShell v0.5 adds live systemd service-status awareness without adding service-control authority.

## Scope

v0.5 introduces:

- systemd service observation over the system D-Bus;
- a fixed service allowlist;
- one read-only `ListUnits()` call;
- no arbitrary unit-name query;
- `phios.service-observation.v1`;
- `phios.service-transport.v1`;
- same-origin loopback delivery through the existing PhiShell local transport;
- host-side validation before transport;
- browser-side validation before display;
- freshness checks;
- explicit fixture fallback;
- a Service Status panel inside System Inspector;
- live CI verification on the Ubuntu runner;
- source-level tests forbidding mutating systemd method names.

## Why D-Bus

systemd exposes runtime unit state through its D-Bus Manager interface.

v0.5 uses the read-only unit listing surface rather than invoking `systemctl`.

The observer calls:

```text
org.freedesktop.systemd1.Manager.ListUnits()
```

and nothing else.

No subprocess is created.

## Fixed allowlist

The adapter projects only these service identities:

```text
dbus
journald
resolved
network-manager
networkd
ssh
docker
ollama
bluetooth
```

The associated unit candidates are frozen in source.

Examples:

```text
dbus.service
systemd-journald.service
systemd-resolved.service
NetworkManager.service
systemd-networkd.service
ssh.service / sshd.service
docker.service
ollama.service
bluetooth.service
```

The browser does not supply a unit name.

The HTTP API does not accept a unit name.

The D-Bus adapter does not expose an arbitrary lookup method.

## Projection boundary

`ListUnits()` returns the systemd runtime unit table.

PhiShell immediately reduces that table to the fixed allowlist.

For each allowed service, v0.5 retains only:

```text
id
label
unit
found
description
loadState
activeState
subState
```

PhiShell does not transport:

- D-Bus object paths;
- job identifiers;
- job types;
- job object paths;
- dependency graphs;
- arbitrary non-allowlisted units.

An allowlisted service that is not loaded is represented as:

```text
found       = false
description = null
loadState   = null
activeState = null
subState    = null
```

PhiShell does not invent an inactive state when systemd did not actually report the unit.

## Observation contract

Every native service observation carries:

```text
schemaVersion       = phios.service-observation.v1
source              = systemd-dbus-list-units
allowlistOnly       = true
readOnly            = true
executionAuthority  = false
effectPerformed     = false
```

Availability is explicit:

```text
available
unavailable
```

Bounded unavailable reasons are:

```text
non-linux-host
systemd-runtime-not-present
system-bus-unavailable
```

Raw D-Bus errors are not transported to the browser.

## Transport

The existing v0.4 loopback host adds exactly one read endpoint:

```text
GET /api/v1/service-observation
```

The response envelope carries:

```text
transportSchemaVersion = phios.service-transport.v1
transport              = loopback-http
transportIdentity      = phishell-local-observer
localOnly              = true
readOnly               = true
executionAuthority     = false
effectPerformed        = false
servedAt               = <timestamp>
snapshotAgeMs          = <bounded freshness>
observation            = phios.service-observation.v1
```

The host remains bound to:

```text
127.0.0.1
```

No CORS permission is added.

## Browser trust boundary

PhiShell accepts a live service observation only when all of the following hold:

- the transport schema is correct;
- transport identity is correct;
- the transport is marked local-only;
- the transport is marked read-only;
- execution authority is false;
- effect performed is false;
- the snapshot is fresh;
- observation schema is correct;
- source is `systemd-dbus-list-units`;
- allowlist-only is true;
- the service array has exactly the frozen number of entries;
- each service identity matches its expected allowlist slot;
- each unit name belongs to that identity's frozen unit candidates;
- not-loaded services carry no synthetic runtime state.

Otherwise the UI falls back to an explicit fixture/unavailable projection.

## Dependency boundary

The Node host uses:

```text
@jellybrick/dbus-next 0.11.3
```

only inside the Linux host-side service observer.

The React/browser bundle does not receive D-Bus access.

The dependency is replaceable behind:

```text
collectSystemdServiceObservation()
```

PhiOS owns the observation contract and allowlist.

The D-Bus package does not own PhiOS policy.

## Forbidden control surface

The service observer source is tested to contain no use of:

```text
StartUnit
StopUnit
RestartUnit
ReloadUnit
EnableUnitFiles
DisableUnitFiles
MaskUnitFiles
SetUnitProperties
KillUnit
ResetFailed
LoadUnit
```

The adapter also contains no:

```text
systemctl
child_process
exec
execFile
spawn
sudo
```

The only systemd Manager method invoked by the observer is:

```text
ListUnits
```

## Capability plane

The shell capability model now exposes:

```text
service.inspect = available
```

while preserving:

```text
service.control = unavailable
```

That distinction is intentional.

```text
can observe service state
    !=
can start a service
    !=
can stop a service
    !=
can restart a service
    !=
can enable or disable a service
```

## System Inspector

The Service Status panel displays:

- service label;
- canonical observed unit;
- load state;
- active state;
- substate;
- explicit NOT LOADED when no allowlisted candidate is present.

The panel offers only:

```text
Refresh
```

There are no service-control buttons.

## CI proof

The PhiShell workflow now performs:

```text
npm install
    ↓
browser contract tests
    ↓
native host/service adapter tests
    ↓
live Linux host probe
    ↓
live systemd D-Bus service probe
    ↓
TypeScript/Vite build
    ↓
launch loopback host
    ↓
GET built PhiShell
    ↓
GET live host observation
    ↓
GET live service observation
    ↓
verify allowlist_only=true
    ↓
verify execution_authority=false
    ↓
verify effect_performed=false
    ↓
POST observation endpoints
    ↓
405 Method Not Allowed
```

The live service-probe CI step requires the Ubuntu runner to expose a working systemd system bus. If it does not, the lane fails instead of pretending live service observation succeeded.

## Security properties

v0.5 does not add:

- arbitrary service lookup;
- arbitrary D-Bus method forwarding;
- D-Bus object-path forwarding;
- service start;
- service stop;
- service restart;
- service reload;
- service enable/disable;
- service masking;
- process signalling;
- package management;
- network configuration;
- power control;
- remote binding.

## Next increment

A safe v0.6 candidate is **bounded process/session observation** or **read-only package inventory**, but either should remain independent from execution.

A future service-control broker must not be implemented by expanding this observer.

If PhiOS eventually gains service mutation, it should be a separately reviewed authority/effect subsystem with:

- explicit operator grant;
- fixed capability identifiers;
- scope;
- necessity;
- consequence display;
- expiry;
- deterministic receipts;
- denial semantics;
- no generic command execution.

The v0.5 service observer should remain permanently read-only.
