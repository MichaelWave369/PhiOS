# PhiVessel Native/Local Host Handshake v0.38

v0.38 adds an ephemeral transport handshake in front of the existing
PhiVessel ↔ PhiOS bridge.

The handshake does not create authority.

Core rule:

```text
HANDSHAKE != AUTHENTICATED HUMAN IDENTITY
HANDSHAKE != AUTHORIZATION
HANDSHAKE != ACTIONLEASE
HANDSHAKE != EXECUTION AUTHORITY
```

## Why a handshake exists

Before v0.38 the loopback bridge exposed:

```text
observe(...)
propose(...)
execute(leaseId)
```

directly on the local HTTP surface.

Loopback limits network reachability, but it does not identify which local
process is calling the bridge and it does not establish protocol freshness.

v0.38 therefore requires the default Ghost-Walk host to negotiate an ephemeral
session before those bridge operations are used.

## Handshake endpoint

```http
POST /api/v1/phivessel/handshake
```

Exact request shape:

```json
{
  "clientInstanceId": "super-phivessel:desktop:local",
  "clientNonce": "nonce_0123456789abcdef",
  "supportedBridgeVersions": ["PV-PHIOS-BRIDGE-0.1"],
  "requestedOperations": ["OBSERVE", "PROPOSE", "EXECUTE"]
}
```

The client identity is an assertion supplied by the local caller.

v0.38 deliberately reports:

```text
clientIdentityAuthenticated = false
```

because localhost is not proof that the caller is the human, the PhiVessel
binary, or any other particular process.

## Negotiation

PhiOS selects only the bridge version it actually supports.

Requested operations are intersected with operations currently available.

```text
OBSERVE   always available when bridge is mounted
PROPOSE   always available when bridge is mounted
EXECUTE   available only when trusted local execution is mounted
```

Example:

```text
requested:
OBSERVE, EXECUTE

trusted executor absent:
OBSERVE

result:
grantedOperations = [OBSERVE]
```

PhiOS does not pretend unavailable execution exists.

## Ephemeral session

A successful handshake returns:

```text
server identity
server instance identity
selected bridge version
echoed client instance identity
echoed client nonce
granted operations
session ID
256-bit random session bearer token
issue time
expiry
```

Default lifetime:

```text
300 seconds
```

Allowed server-side range:

```text
30-900 seconds
```

Sessions exist only in process memory.

They are not written to the Ledger, execution manifest, authority-event state,
or PhiShell persistence.

Restarting the Ghost-Walk host creates a new server instance identity and
destroys every previous session.

## Session headers

After handshake, bridge calls include:

```http
X-PhiVessel-Session-Id: pvs:...
X-PhiVessel-Session-Token: <64 lowercase hex characters>
```

The token is stored by PhiOS only as SHA-256.

Validation uses constant-time digest comparison.

Missing, expired, wrong-token, or operation-mismatched sessions fail closed.

## Observe

```http
GET /api/v1/phivessel/observe?kind=BRIDGE_STATUS
X-PhiVessel-Session-Id: ...
X-PhiVessel-Session-Token: ...
```

Requires negotiated:

```text
OBSERVE
```

## Propose

```http
POST /api/v1/phivessel/proposals
X-PhiVessel-Session-Id: ...
X-PhiVessel-Session-Token: ...
```

Requires negotiated:

```text
PROPOSE
```

Proposal semantics remain unchanged:

```text
proposal
!= AuthorityRequest
!= authorization
!= ActionLease
```

## Execute

```http
POST /api/v1/phivessel/execute
X-PhiVessel-Session-Id: ...
X-PhiVessel-Session-Token: ...
```

Exact body remains:

```json
{
  "leaseId": "<sha256>"
}
```

Requires negotiated:

```text
EXECUTE
```

But the session still cannot authorize the action.

Execution requires both:

```text
valid negotiated transport session
                +
exact existing ActionLease identity
                ↓
v0.35 governed leased execution handoff
```

The ActionLease remains the authority-bearing object.

## Reference local client

v0.38 adds:

```text
phios.phivessel_local_client.PhiVesselLocalClient
```

It is a reference integration for the native/local Vessie host.

It:

- connects only to IPv4 loopback;
- performs the handshake;
- keeps the session token in memory;
- attaches session headers to subsequent requests;
- exposes only `observe`, `propose`, and `execute(lease_id)`;
- cannot create AuthorityRequests;
- cannot authorize;
- cannot bind capability payloads;
- cannot mint ActionLeases;
- cannot mutate `phi-trust`.

The intended Super PhiVessel local-host implementation should mirror this
contract.

## Authority semantics

Handshake response:

```text
policyAuthority      = false
operationalAuthority = false
actionAuthority      = false
executionAuthority   = false
effectPerformed      = false
```

Session record:

```text
client_identity_authenticated = false
policy_authority               = false
operational_authority          = false
action_authority               = false
execution_authority            = false
effect_performed               = false
```

A valid session proves only:

```text
this caller completed the current local host's transport negotiation
and possesses the ephemeral session bearer token
```

It does not prove human approval or action authority.

## Resulting chain

```text
Super PhiVessel local host
        ↓
asserted client instance ID
client nonce
supported bridge versions
requested operations
        ↓
PhiOS v0.38 handshake
        ↓
ephemeral transport session
        ↓
OBSERVE / PROPOSE
        │
        └──────── no authority
        ↓
EXECUTE requested
        ↓
session permits EXECUTE transport operation?
        ↓ yes
exact ActionLease exists and verifies?
        ↓ yes
v0.35 governed execution
        ↓
post-action verification
        ↓
Reality Ledger
```

## Next rung

After v0.38 is merged, the remaining milestone is the controlled Windows
acceptance run.

That run should exercise:

```text
demonstration
→ observation
→ inference
→ human interpretation
→ accepted intent
→ policy admission
→ AuthorityRequest
→ human APPROVE
→ executable binding
→ current AuthorityEpoch
→ ActionLease
→ Vessie handshake
→ execute(leaseId)
→ real guarded Windows click
→ post-action verification
→ consumed lease
→ Ledger receipt
```

No new authority abstraction should be introduced unless that real acceptance
run reveals a concrete missing boundary.
