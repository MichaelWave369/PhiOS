# PhiShell v0.6 — Bounded Process Observation

Status: **candidate implementation**  
Target substrate: **Linux / procfs / Wayland path**  
Primary invariant: **CAPABILITY != AUTHORITY**

PhiShell v0.6 adds live current-user process awareness without adding process-control authority.

## Scope

v0.6 introduces:

- current-user-only process observation through Linux procfs;
- a hard maximum of 32 detailed process rows;
- process-state aggregates;
- resident-memory observation;
- thread-count observation;
- `phios.process-observation.v1`;
- `phios.process-transport.v1`;
- same-origin loopback delivery through the existing local transport;
- host-side validation before transport;
- browser-side validation before display;
- freshness checks;
- explicit fixture fallback;
- a Process Census panel in System Inspector;
- live Linux CI verification;
- source-level tests forbidding sensitive and mutating process surfaces.

## Native source

The observer reads only narrow procfs files:

```text
/proc/<pid>/status
/proc/<pid>/comm
```

It does not read:

```text
/proc/<pid>/cmdline
/proc/<pid>/environ
/proc/<pid>/cwd
/proc/<pid>/exe
```

The observer creates no subprocess.

## Current-user scope

PhiOS determines the current local UID and filters process observations to that UID.

Detailed rows for other users are never transported.

The contract is fixed to:

```text
scope = current-user
```

The detailed list is capped at:

```text
processLimit = 32
```

Rows are ordered by resident memory and then PID.

The cap bounds payload size and UI exposure.

## Process row

Each exposed row contains only:

```text
pid
ppid
comm
state
rssBytes
threads
```

No argument vector is exposed.

No environment is exposed.

No working directory is exposed.

No executable path is exposed.

No open-file list, socket list, credentials, namespaces, cgroups, or process memory is exposed.

## Aggregate state

v0.6 counts current-user processes by bounded state categories:

```text
running
sleeping
diskSleep
stopped
zombie
idle
other
```

The count is observational only.

It does not create scheduling or process-management authority.

## Observation contract

A live process observation carries:

```text
schemaVersion            = phios.process-observation.v1
source                   = procfs-current-user
scope                    = current-user
processLimit             = 32
readOnly                 = true
executionAuthority       = false
effectPerformed          = false
currentUid               = <local uid>
currentUserProcessCount  = <count>
```

Availability is explicit:

```text
available
unavailable
```

Bounded unavailable reasons are:

```text
non-linux-host
current-uid-unavailable
procfs-unavailable
```

Raw filesystem errors are not transported.

## Transport

The local v0.4 transport adds one read endpoint:

```text
GET /api/v1/process-observation
```

The envelope is:

```text
transportSchemaVersion = phios.process-transport.v1
transport              = loopback-http
transportIdentity      = phishell-local-observer
localOnly              = true
readOnly               = true
executionAuthority     = false
effectPerformed        = false
servedAt               = <timestamp>
snapshotAgeMs          = <bounded freshness>
observation            = phios.process-observation.v1
```

The host remains bound to:

```text
127.0.0.1
```

No CORS permission is added.

## Browser trust boundary

PhiShell accepts live process data only when:

- the transport schema matches;
- transport identity matches;
- local-only is true;
- read-only is true;
- execution authority is false;
- effect performed is false;
- freshness is within the existing five-second bound;
- observation schema matches;
- source is `procfs-current-user`;
- scope is `current-user`;
- process limit is exactly 32;
- row count is within the limit;
- every row contains only the bounded process fields;
- PIDs, parent PIDs, memory values, and thread counts are sane;
- process names remain bounded.

The browser explicitly rejects process rows that try to carry fields such as:

```text
cmdline
environ
cwd
exe
```

An invalid live payload falls back to the explicit fixture/unavailable state.

## Forbidden process-control surface

The native observer contains no:

```text
process.kill
SIGKILL
SIGTERM
renice
ptrace
child_process
exec
execFile
spawn
sudo
```

The HTTP transport contains no process-control endpoint.

There is no endpoint accepting a PID.

There is no endpoint accepting a signal.

There is no generic procfs path parameter.

## Capability plane

PhiShell now exposes:

```text
process.inspect = available
```

There is intentionally no:

```text
process.control
process.signal
process.kill
```

capability.

Therefore:

```text
can observe a process
    !=
can signal a process
    !=
can change process priority
    !=
can terminate a process
```

## System Inspector

The Process Census panel displays:

- current-user process count;
- state aggregates;
- up to 32 process rows;
- PID;
- process name;
- state;
- resident memory;
- thread count.

The only interactive control is:

```text
Refresh
```

There is no terminate, suspend, resume, reprioritize, trace, inspect arguments, or open-files action.

## CI proof

The PhiShell lane now performs:

```text
npm install
    ↓
browser contract tests
    ↓
native host/service/process tests
    ↓
live Linux host probe
    ↓
live systemd service probe
    ↓
live current-user procfs probe
    ↓
TypeScript/Vite build
    ↓
launch loopback host
    ↓
GET built PhiShell
    ↓
GET host observation
    ↓
GET service observation
    ↓
GET process observation
    ↓
verify scope=current-user
    ↓
verify process count <= 32 detailed rows
    ↓
verify executionAuthority=false
    ↓
verify effectPerformed=false
    ↓
POST observation endpoints
    ↓
405 Method Not Allowed
```

## Security properties

v0.6 does not add:

- command-line inspection;
- environment inspection;
- cwd inspection;
- executable-path inspection;
- cross-user process details;
- arbitrary PID lookup;
- process signalling;
- process termination;
- process priority changes;
- tracing;
- arbitrary procfs reads;
- remote binding.

## Next increment

A safe v0.7 candidate is **read-only package inventory** or **bounded device inventory**.

Package inventory should avoid invoking package-manager commands and should keep distro adapters replaceable.

Device inventory should avoid raw hardware-control APIs and expose only bounded identity/capability metadata.

A future process-control broker, if one is ever justified, must be a separate reviewed authority/effect subsystem.

The v0.6 process observer should remain permanently read-only.
