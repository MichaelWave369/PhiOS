# PhiVessel ↔ PhiOS Bridge v0.1

Bridge v0.1 is the narrow transport boundary between Super PhiVessel and PhiOS.

It deliberately exposes only three operations:

```text
observe(...)
propose(workId, packetRefs, proposalType)
execute(leaseId)
```

The bridge is not a lease broker, authority service, provider router, or workflow
engine.

## Core rule

```text
VESSEL MAY REFERENCE AUTHORITY.
VESSEL MAY NOT CREATE AUTHORITY.
```

Vessie may never mint, expand, renew, infer, rebind, replace, or transfer an
ActionLease.

## observe(...)

Observation is read-only and carries:

```text
policy_authority      = false
operational_authority = false
action_authority      = false
execution_authority   = false
effect_performed      = false
```

Bridge v0.1 supports bounded observation kinds:

- `BRIDGE_STATUS`
- `GHOSTWALK_CONTROL`
- `LEASE_STATUS`

`LEASE_STATUS` accepts one ActionLease SHA-256 and returns only PhiOS-owned
custody/consumption/execution evidence.

## propose(...)

A proposal is an append-only documentary packet:

```text
workId
packetRefs[]
proposalType
```

Proposal types are bounded:

```text
OBSERVE
BUILD
PATCH
RUN
MOVE
WRITE
DEPLOY
```

There is intentionally no free-form action field.

A proposal:

- does not create an AuthorityRequest;
- does not grant authorization;
- does not create an ActionLease;
- does not select an executor;
- does not execute a capability;
- does not perform a desktop effect.

Recording the proposal is a local Ledger mutation only.

Proposal custody is stored in:

```text
phivessel-proposals.jsonl
```

## execute(leaseId)

The external execution body is exactly:

```json
{"leaseId":"<64-hex ActionLease SHA-256>"}
```

Any additional field, including `payload`, `action`, `target`, `scope`,
or `permission`, is rejected.

The bridge delegates the lease identity to Macro Runtime v0.35
`GhostWalkLeaseExecutionHandoff`.

The actual deed is recovered by PhiOS from trusted custody.

```text
leaseId
   ↓
v0.34 ActionLease custody
   ↓
v0.33 exact executable binding
   ↓
current policy / enforcement / AuthorityEpoch
   ↓
v0.35 single-use execution handoff
   ↓
PhiOS Spine
```

## Local transport

The HTTP transport remains IPv4 loopback only.

Bridge routes:

```text
GET  /api/v1/phivessel/observe
POST /api/v1/phivessel/proposals
POST /api/v1/phivessel/execute
```

The server does not add permissive browser CORS.

A publicly hosted Vessie page therefore does not automatically gain access to a
local PhiOS effect service. Public/browser deployments should use a trusted
local/native host bridge rather than weakening PhiOS loopback boundaries.

The default Ghost-Walk CLI mounts observation and proposal support. Execution
remains unavailable unless a trusted v0.35 lease executor is explicitly mounted
into the bridge service.

That is intentional fail-closed behavior.

## Vessie-side transport order

The companion Super PhiVessel client should prefer:

1. a trusted native/desktop bridge injected by the local host;
2. direct loopback only in a local runtime explicitly configured to permit it;
3. otherwise fail closed as `TRUSTED_LOCAL_HOST_REQUIRED`.

The public web UI must not silently downgrade this rule.

## Authority separation

```text
WorkObject         context only
PromotionPacket    provenance/evidence only
ProposalPacket     documentary intent only
AuthorityRequest   PhiOS authority request
ActionLease        PhiOS bounded action authority
ExecutionReceipt   observed execution outcome
```

These objects must remain distinct.

A well-dressed ProposalPacket is still not a lease.
