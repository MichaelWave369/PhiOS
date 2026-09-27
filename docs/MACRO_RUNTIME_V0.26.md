# Macro Runtime v0.26 — PhiShell Ghost-Walk Control Bridge

v0.26 binds the stable v0.25 Ghost-Walk control contract into the actual
PhiShell local runtime without exposing listener, UIA, baseline-service,
ActionLease, or desktop execution primitives to browser code.

## Architecture

```text
PhiShell React
    |
    | same-origin GET/POST
    v
PhiShell local transport :3969
    |
    | validated loopback proxy
    v
Ghost-Walk control sidecar :3973
    |
    | one process-lifetime object graph
    v
GhostWalkControlSurface v0.25
    |
    v
GhostWalkHostService v0.24
    |
    +-- Windows listener
    +-- baseline refresh service
    +-- transition coordinator
    +-- Reality Ledger
```

The sidecar owns one long-running Python host. HTTP requests do not create a new
host, listener, or baseline service. This preserves session state, run
generation, refresh cadence, and restart evidence across repeated UI polling.

## Operator surface

PhiShell System Inspector now renders:

- host status and run generation
- session identity
- listener liveness
- baseline ticker liveness
- baseline arm/freshness state and age
- recovery state
- last observed action digest
- recent learned transitions
- current OperatorLog revision linkage
- recent holds and failures
- START / STOP / ARM / DISARM only when projected by
  `available_actions`

The browser polls status once per second. If a later poll fails validation, the
UI keeps the last valid snapshot and marks the bridge unavailable. It does not
replace missing runtime evidence with a green fixture.

## Local endpoints

The Python sidecar binds IPv4 loopback only:

```text
127.0.0.1:3973
```

It exposes:

```http
GET  /api/v1/ghostwalk
POST /api/v1/ghostwalk/actions
```

The action body is bounded to 8 KiB and accepts only:

```json
{"action":"START","session_id":"ghostwalk-local"}
```

or:

```json
{"action":"STOP"}
{"action":"ARM"}
{"action":"DISARM"}
{"action":"STATUS"}
```

`session_id` is required only for START and rejected for every other action.

PhiShell's Node transport exposes the same paths on its existing same-origin
loopback server and independently validates the sidecar schema before returning
it to the browser.

## Authority boundary

Every sidecar and proxy envelope asserts:

```text
operationalAuthority = false
actionAuthority      = false
executionAuthority   = false
effectPerformed      = false
```

START / STOP / ARM / DISARM are control-plane lifecycle changes. They do not
grant desktop execution authority and do not expose an ActionLease.

```text
UI CONTROL != EXECUTION AUTHORITY
CONTROL-PLANE MUTATION != DESKTOP EFFECT
AVAILABLE ACTION != AUTHORITY GRANT
ARM != PERMISSION TO ACT
STATUS != REALITY PROOF BEYOND ITS RECEIPT
LOCALHOST != TRUST
```

Both the Node proxy and browser client reject malformed schemas or authority
flags rather than trusting local JSON by location alone.

## Running locally on Windows

From the repository root, start the long-running Ghost-Walk sidecar:

```powershell
python -m phios.macro_ghostwalk_control_server
```

Then start PhiShell's local transport from `phishell/` using the existing
workflow.

The sidecar port may be changed with `PHIOS_GHOSTWALK_PORT`; the Node proxy
uses the same environment variable.

## Failure behavior

- malformed browser control request: 400, no proxy call
- unavailable or invalid sidecar evidence: 503 at PhiShell transport
- invalid sidecar schema or non-zero authority flag: rejected
- sidecar restart: v0.24 recovery semantics apply
- UI polling failure: last valid snapshot retained and visibly marked stale
- sidecar process exit: owned host is stopped cleanly when possible

## Tests

v0.26 adds coverage for:

- loopback-only Python control service
- strict START/session validation
- zero-authority transport envelopes
- Node sidecar schema validation
- malformed-sidecar rejection
- bounded browser action payloads
- same-origin PhiShell proxy routing
- browser control client fail-closed behavior
- START request serialization

## Next rung

v0.27 should connect the same stable projection to PhiVessel so Vessie can
explain Ghost-Walk state, learned transitions, holds, and recovery evidence
without gaining lifecycle or execution authority by default.
