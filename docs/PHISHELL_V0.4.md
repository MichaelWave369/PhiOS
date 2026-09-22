# PhiShell v0.4 — Local Observation Transport

Status: **candidate implementation**  
Target substrate: **Linux / Wayland path**  
Primary invariant: **CAPABILITY != AUTHORITY**

PhiShell v0.4 connects the real read-only Linux observation probe to the built PhiShell through a narrow same-origin loopback transport.

The transport remains observation-only.

## Scope

v0.4 introduces:

- a loopback-only HTTP host bound to `127.0.0.1`;
- same-origin serving of the built PhiShell and host-observation API;
- `phios.host-transport.v1`;
- runtime validation of native snapshots before transport;
- browser validation of transport identity and snapshot invariants before display;
- freshness validation;
- explicit fixture fallback if the live transport is absent, stale, malformed, or unsafe;
- a manual refresh control in System Inspector;
- end-to-end CI proof that the built shell and live observation endpoint share the same local origin;
- rejection of all non-GET requests;
- no CORS permission surface;
- no generic process execution;
- no generic filesystem API;
- no mutation endpoint.

## Architecture

```text
Linux kernel / proc / sysfs / Node os APIs
                ↓
      linux-readonly-node-probe
                ↓
     bounded snapshot validator
                ↓
       127.0.0.1 local host
                ↓
        same-origin HTTP GET
                ↓
     transport-envelope validator
                ↓
           PhiShell UI
```

The local host serves both:

```text
/
    built PhiShell

/api/v1/host-observation
    live phios.host-observation.v1 snapshot

/api/v1/health
    transport readiness only
```

No other API capability is introduced.

## Loopback boundary

The transport host is hard-coded to:

```text
127.0.0.1
```

The implementation does not expose a configuration option for:

```text
0.0.0.0
::
LAN addresses
public interfaces
```

Tests verify the actual listening address.

The port defaults to:

```text
3969
```

A local operator may override the port with:

```text
PHISHELL_OBSERVATION_PORT
```

The CLI only accepts ports from 1024 through 65535.

Changing the port does not change the bind address.

## Same-origin design

PhiShell is served by the same local host that serves the observation endpoint.

This avoids a broad CORS policy.

The transport does not return:

```text
Access-Control-Allow-Origin
```

As a result, unrelated browser origins are not granted permission to read the local observation JSON through normal cross-origin browser requests.

The built shell requests:

```text
/api/v1/host-observation
```

from its own origin.

## Transport envelope

A successful live response uses:

```text
transportSchemaVersion = phios.host-transport.v1
transport              = loopback-http
transportIdentity      = phishell-local-observer
localOnly              = true
readOnly               = true
executionAuthority     = false
effectPerformed        = false
servedAt               = <timestamp>
snapshotAgeMs          = <bounded freshness>
snapshot               = phios.host-observation.v1
```

The declarative schema is stored at:

```text
phishell/contracts/host-transport.schema.json
```

## Freshness

The native probe captures a snapshot immediately before the transport response is created.

The transport computes:

```text
snapshotAgeMs = servedAt - capturedAt
```

The browser provider accepts live data only when:

```text
snapshotAgeMs <= 5000
```

A stale response is not shown as live data.

It falls back to the deterministic fixture.

## Browser trust boundary

The browser does not trust any JSON merely because it arrived from the local endpoint.

Before displaying the snapshot, PhiShell checks:

- transport schema version;
- transport kind;
- transport identity;
- local-only assertion;
- read-only assertion;
- execution-authority assertion;
- effect-performed assertion;
- served timestamp;
- snapshot freshness;
- observation schema version;
- native probe source identity;
- observation-level authority invariants;
- bounded network and power arrays;
- absence of address and MAC fields in network records.

If validation fails:

```text
live response
    ↓
INVALID
    ↓
fixture fallback
```

The shell therefore does not turn malformed local data into trusted system state.

## HTTP method boundary

The host accepts only:

```text
GET
```

A request using:

```text
POST
PUT
PATCH
DELETE
```

or any other method receives:

```text
405 Method Not Allowed
Allow: GET
```

The rejection receipt still states:

```text
executionAuthority = false
effectPerformed    = false
```

## Static file boundary

The local host may serve:

```text
/index.html
/assets/*
```

from the built PhiShell distribution.

It is not a generic filesystem server.

Static paths are normalized and constrained to the PhiShell build directory.

Other paths return 404.

## Execution boundary

The local transport contains no:

```text
child_process
exec
execFile
spawn
sudo
shell command endpoint
generic RPC method
command string parameter
```

The transport does not grant mutation authority.

The existing effect adapter remains:

```text
operationalAuthority = false
actionAuthority      = false
executionAuthority   = false
```

The observation transport additionally preserves:

```text
localOnly          = true
readOnly           = true
executionAuthority = false
effectPerformed    = false
```

Therefore:

```text
can read local observation
    !=
can invoke arbitrary host capability
    !=
can mutate Linux
```

## System Inspector behavior

When PhiShell is launched through the local host:

```text
npm run local
```

the System Inspector can display a validated live snapshot.

The source badge becomes:

```text
LINUX-READONLY-NODE-PROBE
LIVE LOOPBACK
```

When the local transport is unavailable, malformed, stale, or rejected, PhiShell displays:

```text
FIXTURE
FIXTURE FALLBACK
```

The fallback is explicit and never presented as live host state.

## CI proof

The v0.4 PhiShell workflow verifies:

```text
npm install
    ↓
TypeScript + reducer/provider tests
    ↓
native Linux probe tests
    ↓
live Linux probe check
    ↓
TypeScript/Vite production build
    ↓
launch loopback host on ephemeral port
    ↓
fetch built PhiShell from /
    ↓
fetch live observation from same origin
    ↓
verify executionAuthority=false
    ↓
verify effectPerformed=false
    ↓
POST observation endpoint
    ↓
405 Method Not Allowed
```

This validates the complete local observation path without introducing a privileged effect path.

## Security properties

v0.4 intentionally does not provide:

- remote binding;
- wildcard binding;
- CORS opt-in;
- authentication tokens;
- mutation methods;
- command execution;
- service control;
- package control;
- network configuration;
- power control;
- arbitrary file reads.

The absence of an authentication token is intentional at this rung because the service is loopback-only, same-origin, read-only, metadata-minimized, and exposes no mutation surface.

Future increases in sensitivity or authority must not silently reuse this assumption.

## Next increment

A safe v0.5 candidate can add **bounded service-status observation** as a separately modeled read interface.

That work should preserve:

- explicit service allowlists;
- read-only status fields;
- no `systemctl` command execution;
- no service start/stop/restart methods;
- source provenance;
- freshness;
- deterministic failure receipts.

A later privileged broker, if one is ever introduced, must remain a separate reviewed subsystem rather than an extension of this observation transport.
